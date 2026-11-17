"""Shared builders for the tests of domain/ (code_conventions.md, preamble):
pure logic only, no database and no network."""

from types import SimpleNamespace

import pytest

from DayBetes_food.domain.constants import PortionOrigin


@pytest.fixture
def portion():
    """A portion as the metrics read it: amount, method, origin and its food."""

    def build(amount, amount_method=None, *, carbs=10.0, macros_source=None, plate_id=1, cooked=False, factor=None, name="Rice"):
        source = SimpleNamespace(
            name=name,
            carbs_100g=carbs,
            sugars_100g=None,
            fats_100g=1.0,
            saturated_100g=None,
            proteins_100g=2.0,
            fiber_100g=None,
            macros_source=macros_source,
            cooking_factor=factor,
        )
        return SimpleNamespace(
            id=1,
            amount=amount,
            amount_method=amount_method,
            origin=PortionOrigin.CATALOG,
            is_cooked_weight=cooked,
            plate_id=plate_id,
            source=source,
        )

    return build
