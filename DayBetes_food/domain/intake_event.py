"""Domain dataclasses for intake_event (conventions/code_conventions.md §3.6).

This module imports no psycopg, routes or components. The conversion from a
SQL row to these dataclasses lives in DayBetes_food/database/mappers.py, not here.
"""

from dataclasses import dataclass
from datetime import datetime

from DayBetes_food.domain.constants import (
    AmountInputUnit,
    InjectionZone,
    MASS_SANITY_MAX_G,
    IntakeEventState,
    MealType,
)


# Maximum length of intake_event.name, equal to the column's VARCHAR(255)
# (database/schema.py). §7.3 requires declaring the maximum length per field
# and rejecting the excess at the boundary instead of truncating it (decision 2026-09-09).
INTAKE_EVENT_NAME_MAX_LENGTH = 255

# Maximum length of intake_event.notes. The column is TEXT (no physical
# limit), so the limit is a domain one: §7.3 requires declaring a maximum
# length per field and rejecting the excess at the boundary with 422, without
# truncating. 500 characters cover a context note for the meal ("ate out,
# estimated portion") without turning the field into unlimited free text
# (decision 2026-09-10, finding 44 of audit/audit_intake_event.md).
INTAKE_EVENT_NOTES_MAX_LENGTH = 500

# Sanity upper bound for ingested_amount (and, although it is not a column,
# for the total_amount computed live and the fraction derived from it, §6.9.1):
# 100000 g = 100 kg, far above any real human meal. It is not a clinical or
# nutritional limit, it only prevents storing a corrupt or tampered value as
# if it were plausible. Equal to the CHECK ck_intake_event_ingested_amount in
# database/schema.py (measurement_conventions.md §6.9.2, decision
# 2026-09-10). It is the mass bound shared with portion_detail, declared once
# in domain/constants.py (§4.7).
INTAKE_EVENT_INGESTED_AMOUNT_MAX_G = MASS_SANITY_MAX_G

# Units accepted for the ingested amount sent when confirming an event:
# absolute grams of the served plate or a percentage of that plate. They are
# the two members of AmountInputUnit (domain/constants.py), the central units
# enum of measurement_conventions.md §11; this only declares which of them
# this particular boundary accepts, without duplicating their codes.
# Any other value is rejected with 422 (§7.7: no silent fallback), because
# interpreting it as grams writes a false and irreversible clinical amount
# (finding 47 of audit/audit_intake_event.md).
INTAKE_EVENT_INGESTED_UNITS = (AmountInputUnit.GRAMS, AmountInputUnit.PERCENT)


@dataclass(frozen=True)
class IntakeEventRead:
    """Full read model of a meal event.

    meal_time, created_at, updated_at and deleted_at are aware datetimes in UTC
    (TIMESTAMPTZ columns). timezone_at_event stores the zone in which the user
    entered meal_time, as in insulin_injections.
    A non-NULL deleted_at means an archived event (§11.3); it can only happen
    in the 'consumed' state (decision 2026-09-08).
    ingested_amount is the event's only snapshot of total amount: it is
    computed once in confirm_intake_event and equals the sum of
    portion_detail.amount after scaling them by the fraction actually
    consumed. There is no total_amount column: it is computed live with
    SUM(amount) when needed (decision 2026-09-10,
    measurement_conventions.md §4.4/§6.9.1).
    """
    id: int
    user_id: int
    state: IntakeEventState
    meal_type: MealType | None
    name: str | None
    meal_time: datetime | None
    timezone_at_event: str
    eating_out: bool
    insulin_dose: bool
    injection_zone: InjectionZone | None
    ingested_amount: float | None
    amount_confidence: float | None
    quality_confidence: float | None
    carbs_uncertainty: float | None
    sugars_uncertainty: float | None
    fats_uncertainty: float | None
    saturated_uncertainty: float | None
    proteins_uncertainty: float | None
    fiber_uncertainty: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class IntakeEventCreate:
    """Payload to create an event. The user_id comes from the authenticated context."""
    user_id: int
    state: IntakeEventState = IntakeEventState.PLANNED
    meal_type: MealType | None = None
    name: str | None = None
    meal_time: datetime | None = None


@dataclass(frozen=True)
class IntakeEventUpdate:
    """Payload to update an active event (§3.1). Editable fields only.

    All of them are optional: a field set to None means "leave untouched", like
    the `dict` it replaces (behaviour of `_build_update_query`). It cannot set
    `name` to NULL explicitly; `update_intake_event_name` still exists for
    that.
    """
    meal_type: MealType | None = None
    name: str | None = None
    meal_time: datetime | None = None
    timezone_at_event: str | None = None
    eating_out: bool | None = None
    insulin_dose: bool | None = None
    injection_zone: InjectionZone | None = None
    ingested_amount: float | None = None
    amount_confidence: float | None = None
    quality_confidence: float | None = None
    carbs_uncertainty: float | None = None
    sugars_uncertainty: float | None = None
    fats_uncertainty: float | None = None
    saturated_uncertainty: float | None = None
    proteins_uncertainty: float | None = None
    fiber_uncertainty: float | None = None
    notes: str | None = None
