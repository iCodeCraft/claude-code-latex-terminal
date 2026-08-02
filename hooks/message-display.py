#!/usr/bin/env python3
"""MessageDisplay hook that preserves LaTeX escapes in terminal output."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

if sys.version_info < (3, 8):
    print("latex-terminal: Python 3.8 or newer is required.", file=sys.stderr)
    raise SystemExit(1)

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from math_spans import DisplayState, transform_delta


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0
    if payload.get("hook_event_name") != "MessageDisplay":
        return 0

    message_id = payload.get("message_id")
    if not isinstance(message_id, str):
        return 0

    index = payload.get("index")
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        return 0

    final = payload.get("final")
    if not isinstance(final, bool):
        return 0

    delta = payload.get("delta")
    if not isinstance(delta, str):
        return 0

    state_path = _state_path(message_id)
    state = _load_state(state_path)
    result = transform_delta(delta, state, final=final)

    if final:
        state_path.unlink(missing_ok=True)
    elif result.state == DisplayState():
        state_path.unlink(missing_ok=True)
    else:
        _save_state(state_path, result.state)

    if result.changed:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "MessageDisplay",
                        "displayContent": result.content,
                    }
                }
            )
        )
    return 0


def _state_path(message_id: str) -> Path:
    """Keep streamed messages isolated without using input as a file name."""
    safe_id = hashlib.sha256(message_id.encode("utf-8")).hexdigest()
    root = Path(os.environ.get("CLAUDE_PLUGIN_DATA", tempfile.gettempdir()))
    return root / f"message-display-{safe_id}.json"


def _load_state(path: Path) -> DisplayState:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return DisplayState()
    if not isinstance(data, dict):
        return DisplayState()
    return DisplayState.from_dict(data)


def _save_state(path: Path, state: DisplayState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
