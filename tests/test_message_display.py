import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).parents[1]
HOOK = PLUGIN_ROOT / "hooks" / "message-display.py"


def _bash_executable() -> str:
    """Use Git Bash on Windows instead of the WSL compatibility launcher."""
    if os.name == "nt":
        git_path = shutil.which("git")
        if git_path:
            git_bash = Path(git_path).parents[1] / "bin" / "bash.exe"
            if git_bash.is_file():
                return str(git_bash)
    return "bash"


BASH = _bash_executable()


class MessageDisplayHookTests(unittest.TestCase):
    def test_display_only_uses_native_rendering_path(self):
        with tempfile.TemporaryDirectory() as data_dir:
            output = self._run_hook(
                {
                    "hook_event_name": "MessageDisplay",
                    "message_id": "display-only",
                    "index": 0,
                    "final": True,
                    "delta": (
                        "$$\n\\begin{aligned}\na\\,x &= b "
                        + "\\" * 2
                        + "\nc\\;x &= d\n\\end{aligned}\n$$\n"
                    ),
                },
                data_dir,
            )

            self.assertIsNone(output)
            self.assertFalse(list(Path(data_dir).glob("message-display-*.json")))

    def test_protects_display_math_when_an_inline_span_requires_replacement(self):
        with tempfile.TemporaryDirectory() as data_dir:
            output = self._run_hook(
                {
                    "hook_event_name": "MessageDisplay",
                    "message_id": "test-message",
                    "index": 0,
                    "final": True,
                    "delta": (
                        "Inline $c\\,d$\n$$\na\\,x &= b "
                        + "\\" * 2
                        + "\nb\\;y\n$$\n"
                    ),
                },
                data_dir,
            )

            self.assertEqual(
                output["hookSpecificOutput"]["displayContent"],
                "Inline $c\\\\,d$\n$$\na\\\\,x &= b "
                + "\\" * 4
                + "\nb\\\\;y\n$$\n",
            )
            self.assertFalse(list(Path(data_dir).glob("message-display-*.json")))

    def test_tracks_a_replaced_display_block_across_batches(self):
        with tempfile.TemporaryDirectory() as data_dir:
            first = self._run_hook(
                {
                    "hook_event_name": "MessageDisplay",
                    "message_id": "split-message",
                    "index": 0,
                    "final": False,
                    "delta": "Inline $c\\,d$\n$$\na\\,x\n",
                },
                data_dir,
            )
            second = self._run_hook(
                {
                    "hook_event_name": "MessageDisplay",
                    "message_id": "split-message",
                    "index": 1,
                    "final": True,
                    "delta": "b\\;y\n$$\n",
                },
                data_dir,
            )

            self.assertEqual(
                first["hookSpecificOutput"]["displayContent"],
                "Inline $c\\\\,d$\n$$\na\\\\,x\n",
            )
            self.assertEqual(
                second["hookSpecificOutput"]["displayContent"],
                "b\\\\;y\n$$\n",
            )
            self.assertFalse(list(Path(data_dir).glob("message-display-*.json")))

    def test_protects_display_started_after_a_replaced_inline_batch(self):
        with tempfile.TemporaryDirectory() as data_dir:
            first = self._run_hook(
                {
                    "hook_event_name": "MessageDisplay",
                    "message_id": "later-display",
                    "index": 0,
                    "final": False,
                    "delta": "Inline $c\\,d$\n\nDisplay:\n",
                },
                data_dir,
            )
            second = self._run_hook(
                {
                    "hook_event_name": "MessageDisplay",
                    "message_id": "later-display",
                    "index": 1,
                    "final": True,
                    "delta": "$$\na\\,x &= b " + "\\" * 2 + "\nc\\;x &= d\n$$\n",
                },
                data_dir,
            )

            self.assertEqual(
                first["hookSpecificOutput"]["displayContent"],
                "Inline $c\\\\,d$\n\nDisplay:\n",
            )
            self.assertEqual(
                second["hookSpecificOutput"]["displayContent"],
                "$$\na\\\\,x &= b " + "\\" * 4 + "\nc\\\\;x &= d\n$$\n",
            )
            self.assertFalse(list(Path(data_dir).glob("message-display-*.json")))

    def test_interleaved_messages_keep_separate_streaming_state(self):
        with tempfile.TemporaryDirectory() as data_dir:
            first = self._run_hook(
                {
                    "hook_event_name": "MessageDisplay",
                    "message_id": "message-a",
                    "index": 0,
                    "final": False,
                    "delta": "Inline $a\\,b$\n$$\nc\\;x\n",
                },
                data_dir,
            )
            other = self._run_hook(
                {
                    "hook_event_name": "MessageDisplay",
                    "message_id": "message-b",
                    "index": 0,
                    "final": True,
                    "delta": "Ordinary **Markdown**.\n",
                },
                data_dir,
            )
            final = self._run_hook(
                {
                    "hook_event_name": "MessageDisplay",
                    "message_id": "message-a",
                    "index": 1,
                    "final": True,
                    "delta": "d\\!y\n$$\n",
                },
                data_dir,
            )

            self.assertEqual(
                first["hookSpecificOutput"]["displayContent"],
                "Inline $a\\\\,b$\n$$\nc\\\\;x\n",
            )
            self.assertIsNone(other)
            self.assertEqual(
                final["hookSpecificOutput"]["displayContent"],
                "d\\\\!y\n$$\n",
            )
            self.assertFalse(list(Path(data_dir).glob("message-display-*.json")))

    def test_ordinary_text_returns_no_replacement(self):
        with tempfile.TemporaryDirectory() as data_dir:
            output = self._run_hook(
                {
                    "hook_event_name": "MessageDisplay",
                    "message_id": "ordinary-message",
                    "index": 0,
                    "final": True,
                    "delta": "Normal **Markdown** remains native.\n",
                },
                data_dir,
            )

            self.assertIsNone(output)
            self.assertFalse(list(Path(data_dir).glob("message-display-*.json")))

    def test_empty_final_batch_cleans_up_state(self):
        with tempfile.TemporaryDirectory() as data_dir:
            first = self._run_hook(
                {
                    "hook_event_name": "MessageDisplay",
                    "message_id": "empty-final",
                    "index": 0,
                    "final": False,
                    "delta": "$$\na\\,x\n",
                },
                data_dir,
            )
            final = self._run_hook(
                {
                    "hook_event_name": "MessageDisplay",
                    "message_id": "empty-final",
                    "index": 1,
                    "final": True,
                    "delta": "",
                },
                data_dir,
            )

            self.assertIsNone(first)
            self.assertIsNone(final)
            self.assertFalse(list(Path(data_dir).glob("message-display-*.json")))

    def test_ignores_invalid_persisted_state(self):
        with tempfile.TemporaryDirectory() as data_dir:
            digest = hashlib.sha256(b"invalid-state").hexdigest()
            state_path = Path(data_dir) / f"message-display-{digest}.json"
            state_path.write_text("[]", encoding="utf-8")

            output = self._run_hook(
                {
                    "hook_event_name": "MessageDisplay",
                    "message_id": "invalid-state",
                    "index": 1,
                    "final": True,
                    "delta": "Normal text.\n",
                },
                data_dir,
            )

            self.assertIsNone(output)
            self.assertFalse(state_path.exists())

    def test_sanitizes_invalid_persisted_state_fields(self):
        with tempfile.TemporaryDirectory() as data_dir:
            digest = hashlib.sha256(b"invalid-fields").hexdigest()
            state_path = Path(data_dir) / f"message-display-{digest}.json"
            state_path.write_text(
                json.dumps(
                    {
                        "code_fence": "../../../tmp",
                        "inline_code_ticks": True,
                        "pending_backslash": "false",
                    }
                ),
                encoding="utf-8",
            )

            output = self._run_hook(
                {
                    "hook_event_name": "MessageDisplay",
                    "message_id": "invalid-fields",
                    "index": 1,
                    "final": True,
                    "delta": "Normal text.\n",
                },
                data_dir,
            )

            self.assertIsNone(output)
            self.assertFalse(state_path.exists())

    def test_ignores_malformed_input(self):
        result = subprocess.run(
            [BASH, "hooks/run-python.sh", str(HOOK)],
            input="not json",
            capture_output=True,
            check=True,
            cwd=PLUGIN_ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
        )

        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_ignores_non_message_display_payload(self):
        with tempfile.TemporaryDirectory() as data_dir:
            output = self._run_hook(
                {
                    "hook_event_name": "PostToolUse",
                    "message_id": "wrong-event",
                    "index": 0,
                    "final": True,
                    "delta": "$a\\,b$",
                },
                data_dir,
            )

            self.assertIsNone(output)
            self.assertFalse(list(Path(data_dir).glob("message-display-*.json")))

    def _run_hook(self, payload, data_dir):
        environment = {
            **os.environ,
            "CLAUDE_PLUGIN_DATA": data_dir,
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        try:
            result = subprocess.run(
                [BASH, "hooks/run-python.sh", str(HOOK)],
                input=json.dumps(payload),
                capture_output=True,
                check=True,
                cwd=PLUGIN_ROOT,
                env=environment,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            self.fail(
                "Hook command failed.\n"
                f"stdout:\n{error.stdout}\n"
                f"stderr:\n{error.stderr}"
            )
        return json.loads(result.stdout) if result.stdout else None
