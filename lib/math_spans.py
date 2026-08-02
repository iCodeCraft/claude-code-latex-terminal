"""Streaming-safe detection of dollar-delimited LaTeX math."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal


MathDelimiter = Literal["inline", "display"]

# ASCII punctuation that Markdown can consume after a backslash. Letters are
# deliberately excluded so commands such as ``\frac`` remain unchanged.
_MARKDOWN_PUNCTUATION = frozenset(r'!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~')
_FENCE_START = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


@dataclass
class DisplayState:
    """Parser state carried across MessageDisplay batches for one message."""

    math_delimiter: MathDelimiter | None = None
    code_fence: str | None = None
    inline_code_ticks: int = 0
    pending_backslash: bool = False
    message_has_replacement: bool = False
    protect_display_math: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DisplayState:
        delimiter = data.get("math_delimiter")
        if delimiter not in (None, "inline", "display"):
            delimiter = None
        fence = data.get("code_fence")
        if not isinstance(fence, str) or not re.fullmatch(r"`{3,}|~{3,}", fence):
            fence = None
        ticks = data.get("inline_code_ticks", 0)
        if not isinstance(ticks, int) or isinstance(ticks, bool) or ticks < 0:
            ticks = 0
        return cls(
            math_delimiter=delimiter,
            code_fence=fence,
            inline_code_ticks=ticks,
            pending_backslash=data.get("pending_backslash") is True,
            message_has_replacement=data.get("message_has_replacement") is True,
            protect_display_math=data.get("protect_display_math") is True,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TransformResult:
    content: str
    changed: bool
    state: DisplayState


def transform_delta(
    delta: str, state: DisplayState | None = None, *, final: bool = False
) -> TransformResult:
    """Protect LaTeX escapes in one MessageDisplay batch.

    The hook receives whole lines in interactive mode, but display math can
    still span batches. ``DisplayState`` prevents a ``$$`` block opened in one
    batch from being mistaken for inline math in a later batch. Claude Code
    already preserves escapes in display math when the hook leaves a batch
    alone. If an inline span requires ``displayContent``, however, that
    replacement goes through Markdown escaping for the *entire* batch. In
    that case the second pass also protects display math in the same batch.
    """
    initial_state = _clone_state(state)
    inline_result = _transform_delta(delta, initial_state, final=final)

    # A MessageDisplay response is delivered in several batches. An inline
    # span in an early batch can force ``displayContent`` for a later display
    # block, so retain that decision for the rest of the same message.
    needs_protected_display = (
        initial_state.message_has_replacement or inline_result.changed
    )
    if not needs_protected_display:
        return inline_result

    result = _transform_delta(
        delta,
        _clone_state(state),
        final=final,
        protect_display_math=True,
    )
    if result.state.math_delimiter == "display":
        result.state.protect_display_math = True
    result.state.message_has_replacement = True
    return result


def _transform_delta(
    delta: str,
    state: DisplayState,
    *,
    final: bool,
    protect_display_math: bool = False,
) -> TransformResult:
    output: list[str] = []
    changed = False
    index = 0
    line_start = True

    if state.pending_backslash:
        changed = True
        if delta and state.math_delimiter and delta[0] in _MARKDOWN_PUNCTUATION:
            output.append("\\\\" + delta[0])
            index = 1
        else:
            output.append("\\")
        state.pending_backslash = False

    while index < len(delta):
        character = delta[index]

        if state.inline_code_ticks:
            if character == "`":
                run = _count_run(delta, index, "`")
                output.append("`" * run)
                index += run
                if run == state.inline_code_ticks:
                    state.inline_code_ticks = 0
                line_start = False
                continue
            output.append(character)
            line_start = character == "\n"
            index += 1
            continue

        if line_start and state.math_delimiter is None:
            fence_match = _FENCE_START.match(delta[index:])
            if fence_match:
                matched_text = fence_match.group(0)
                fence = fence_match.group(1)
                marker = fence[0]
                run = len(fence)
                if state.code_fence is None:
                    state.code_fence = marker * run
                elif marker == state.code_fence[0] and run >= len(state.code_fence):
                    state.code_fence = None
                output.append(matched_text)
                index += len(matched_text)
                line_start = False
                continue

        if state.code_fence:
            output.append(character)
            line_start = character == "\n"
            index += 1
            continue

        if character == "`" and state.math_delimiter is None:
            run = _count_run(delta, index, "`")
            output.append("`" * run)
            state.inline_code_ticks = run
            index += run
            line_start = False
            continue

        if character == "$" and not _is_escaped(delta, index):
            run = _count_run(delta, index, "$")
            if state.math_delimiter == "display" and run >= 2:
                output.append("$$")
                state.math_delimiter = None
                state.protect_display_math = False
                index += 2
                line_start = False
                continue
            if state.math_delimiter == "inline":
                output.append("$")
                state.math_delimiter = None
                index += 1
                line_start = False
                continue
            if state.math_delimiter is None and run >= 2:
                output.append("$$")
                state.math_delimiter = "display"
                index += 2
                line_start = False
                continue
            if state.math_delimiter is None and _has_inline_closer(delta, index):
                output.append("$")
                state.math_delimiter = "inline"
                index += 1
                line_start = False
                continue

        protect_escapes = state.math_delimiter == "inline" or (
            state.math_delimiter == "display"
            and (protect_display_math or state.protect_display_math)
        )
        if character == "\\" and protect_escapes:
            run = _count_run(delta, index, "\\")
            if run > 1:
                output.append("\\" * (run * 2))
                changed = True
                index += run
                line_start = False
                continue
            if index + 1 == len(delta) and not final:
                state.pending_backslash = True
                changed = True
                index += 1
                continue
            if index + 1 < len(delta) and delta[index + 1] in _MARKDOWN_PUNCTUATION:
                output.append("\\\\" + delta[index + 1])
                changed = True
                index += 2
                line_start = False
                continue

        output.append(character)
        line_start = character == "\n"
        index += 1

    if final and state.pending_backslash:
        output.append("\\")
        state.pending_backslash = False

    return TransformResult(content="".join(output), changed=changed, state=state)


def _clone_state(state: DisplayState | None) -> DisplayState:
    if state is None:
        return DisplayState()
    return DisplayState.from_dict(state.to_dict())


def _count_run(text: str, start: int, character: str) -> int:
    end = start
    while end < len(text) and text[end] == character:
        end += 1
    return end - start


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _has_inline_closer(text: str, opening: int) -> bool:
    """Avoid treating currency such as ``$5`` as an unterminated math span."""
    if opening + 1 >= len(text) or text[opening + 1].isspace():
        return False
    cursor = opening + 1
    while cursor < len(text):
        if text[cursor] == "\n":
            return False
        if text[cursor] == "$" and not _is_escaped(text, cursor):
            return True
        cursor += 1
    return False
