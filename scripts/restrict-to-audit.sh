#!/usr/bin/env bash
# PreToolUse hook (Write) para audit-tabla / propose / review:
# estos agentes solo pueden escribir dentro de audit/, nunca en el
# código real del proyecto.
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
    */audit/*|audit/*)
        exit 0
        ;;
    *)
        echo "Bloqueado: este agente solo puede escribir dentro de audit/. Intento de escritura en: $file_path" >&2
        exit 2
        ;;
esac
