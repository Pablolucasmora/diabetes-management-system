"""Smart macros and nutrient parsing (measurement_conventions.md §5). The cases
of the smart macros are shared with the JavaScript parser of the forms."""

import json
from pathlib import Path

import pytest

from DayBetes_food.domain.nutrition import SMART_MACRO_FIELDS, parse_smart_macros
from DayBetes_food.errors import ValidationError

CASES = json.loads(
    (Path(__file__).resolve().parent.parent / "DayBetes_food/static/data/smart_macros_cases.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", CASES, ids=[str(i) for i in range(len(CASES))])
def test_smart_macros_match_the_shared_cases(case):
    text = case.get("text") or ""
    if case.get("error"):
        with pytest.raises(ValidationError) as error:
            parse_smart_macros(text)
        assert str(error.value) == case["error"]
        return
    result = parse_smart_macros(text)
    for field in SMART_MACRO_FIELDS:
        expected = case["expected"].get(field)
        if expected is None:
            assert result.get(field) is None, field
        else:
            assert result.get(field) == pytest.approx(expected), field
