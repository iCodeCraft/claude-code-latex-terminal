#!/usr/bin/env bash
# Find Python across macOS, Linux, and Git Bash on Windows. In particular,
# skip the non-functional Microsoft Store aliases before trying the Windows
# py launcher. Version compatibility is checked by the Python entry point.
set -euo pipefail

is_usable() {
    local executable_path
    executable_path="$(command -v "$1" 2>/dev/null)" || return 1
    [[ "$executable_path" != *WindowsApps* ]]
}

for executable in python3 python; do
    if is_usable "$executable"; then
        exec "$executable" "$@"
    fi
done

if is_usable py; then
    exec py -3 "$@"
fi

echo "latex-terminal: Python 3.8 or newer was not found." >&2
exit 1
