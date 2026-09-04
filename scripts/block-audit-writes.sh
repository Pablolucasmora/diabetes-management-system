#!/usr/bin/env bash
# PreToolUse hook (Write|Edit) para build: build implementa código real
# y no debe tocar audit/ (esos archivos son el plan ya aprobado, de
# solo lectura para este agente).
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
        echo "Bloqueado: build no puede escribir dentro de audit/ (es el plan aprobado, de solo lectura). Intento de escritura en: $file_path" >&2
        exit 2
        ;;
    *)
        exit 0
        ;;
esac
