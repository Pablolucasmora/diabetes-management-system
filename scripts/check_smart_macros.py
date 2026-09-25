"""Check `parse_smart_macros` against the JS/Python shared cases.

No test suite exists in this project (prelude of code_conventions.md): this is
the manual check of F7 for smart macros. It reads
DayBetes_food/static/data/smart_macros_cases.json, runs the Python parser and
exits with code 1 if any case does not match. A case has either `expected`
(the seven values) or `error` (the exact ValidationError message). In the browser the same cases are
run by `dbSmartMacrosSelfCheck()`.

Usage: python scripts/check_smart_macros.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from DayBetes_food.domain.nutrition import SMART_MACRO_FIELDS, parse_smart_macros  # noqa: E402
from DayBetes_food.errors import ValidationError  # noqa: E402

CASES_PATH = ROOT / "DayBetes_food" / "static" / "data" / "smart_macros_cases.json"


def main() -> int:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    mismatches = []
    for index, case in enumerate(cases):
        text = case.get("text") or ""
        expected_error = case.get("error")
        try:
            actual = parse_smart_macros(text)
            actual_error = None
        except ValidationError as error:
            actual, actual_error = {}, str(error)
        if expected_error != actual_error:
            mismatches.append(
                f"case {index} {text!r}: error expected {expected_error!r}, got {actual_error!r}"
            )
        if expected_error is not None:
            continue
        expected = case.get("expected") or {}
        for field in SMART_MACRO_FIELDS:
            expected_value = expected.get(field)
            actual_value = actual.get(field)
            if expected_value != actual_value:
                mismatches.append(
                    f"case {index} {text!r}: {field} expected {expected_value!r}, got {actual_value!r}"
                )
    if mismatches:
        for line in mismatches:
            print(line)
        return 1
    print(f"OK: {len(cases)} smart-macros cases match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
