#!/usr/bin/env bash
# PreToolUse hook (Bash) para review: solo puede ejecutar comandos de
# solo lectura (consultar código, git o la base de datos), nunca
# modificar nada. Es una lista de patrones heurística, no un análisis
# real del comando — si en algún momento review necesita un comando
# legítimo que esta lista bloquea por error, ajusta la lista aquí en
# vez de sortear el hook.
set -euo pipefail

input="$(cat)"
command_str="$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("tool_input", {}).get("command", ""))
except Exception:
    print("")
')"

lower_cmd="$(printf '%s' "$command_str" | tr "[:upper:]" "[:lower:]")"

deny_patterns=(
    "insert into" "update " "delete from" "drop " "alter " "truncate"
    "git commit" "git push" "git reset" "git rebase" "git merge" "git add "
    "git checkout" "rm -" "rm " "mv " "sed -i" "chmod " "chown "
    "pip install" "npm install" "createdb" "dropdb" " > " " >> "
)

for pattern in "${deny_patterns[@]}"; do
    if [[ "$lower_cmd" == *"$pattern"* ]]; then
        echo "Bloqueado: review solo puede ejecutar comandos de solo lectura. Comando rechazado (contiene '$pattern'): $command_str" >&2
        exit 2
    fi
done

exit 0
