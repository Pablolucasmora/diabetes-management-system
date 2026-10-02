#!/usr/bin/env bash
# PreToolUse hook (Write|Edit) for the audit-tabla and propose agents:
# they can only write inside audit/ or conventions/, never in the
# project's real code.
set -euo pipefail

input="$(cat)"
file_path="$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("tool_input", {}).get("file_path", ""))
except Exception:
    print("")
')"

if [[ -z "$file_path" ]]; then
    exit 0
fi

case "$file_path" in
    */audit/*|audit/*|*/conventions/*|conventions/*)
        exit 0
        ;;
    *)
        echo "Blocked: this agent can only write inside audit/ or conventions/. Write attempted on: $file_path" >&2
        exit 2
        ;;
esac