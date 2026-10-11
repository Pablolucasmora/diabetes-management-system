"""Use cases of `intake_event` shared by more than one endpoint (code_conventions.md §1.2)."""

import math

from DayBetes_food.database.queries import (
    confirm_intake_event,
    create_injection_for_event,
    list_portions_by_event,
    scale_event_portion_amounts,
    update_intake_event,
)
from DayBetes_food.domain.constants import AmountInputUnit
from DayBetes_food.domain.intake_event import INTAKE_EVENT_INGESTED_AMOUNT_MAX_G, IntakeEventUpdate
from DayBetes_food.domain.portion_detail import calculate_macro_summary_metrics, portion_intake_amount
from DayBetes_food.errors import ConflictError, ValidationError


def confirm_planned_event(
    connection,
    user_id: int,
    event_id: int,
    *,
    ingested_value: float | None = None,
    ingested_unit: AmountInputUnit = AmountInputUnit.GRAMS,
) -> None:
    """Move a planned event to consumed (measurement_conventions.md §6.9.1).

    The single confirm path, used by the cart and by the rescue pop-up
    (frontend_conventions.md §9.6). It runs inside the caller's transaction
    and never commits: the caller opens `connection.transaction()`, which is
    what makes reading the portions and scaling them a single unit (finding
    46 of audit/audit_intake_event.md).

    `ingested_value` is how much of the served plate was eaten, already
    parsed as a finite number >= 0: `None` means all of it, `PERCENT` is a
    percentage and `GRAMS` a mass against the live total. The fraction must
    end up in (0, 1] (decision 2026-09-22).

    Raises:
        ConflictError("intake_event_without_portions"): nothing to confirm.
        ConflictError: the event is no longer planned.
        NotFoundError: the event does not exist or is not the user's.
        ValidationError: total or fraction out of range.
    """
    portions = list_portions_by_event(connection, user_id, event_id)
    if not portions:
        # Rule that depends on the database state (§7.10): an event
        # without portions cannot be confirmed; a disallowed state
        # transition → conflict (error_conventions.md §3.6). Finding 34
        # of audit/audit_intake_event.md, decision 2026-09-10.
        raise ConflictError("intake_event_without_portions")
    total_amount = sum(portion_intake_amount(p) for p in portions)
    if not math.isfinite(total_amount) or total_amount > INTAKE_EVENT_INGESTED_AMOUNT_MAX_G:
        # Defense in depth: total_amount is computed live from
        # portion_detail (outside this table's scope), but an
        # ingested_amount derived from it must still respect this
        # table's sanity limit (§6.9.2, finding 32/35).
        raise ValidationError("total_amount_out_of_range")

    if ingested_value is None:
        fraction = 1.0
    elif ingested_unit is AmountInputUnit.PERCENT:
        fraction = ingested_value / 100.0
    else:
        # Only remaining branch: grams, already validated by the caller.
        if total_amount <= 0:
            # There is nothing to consume: grams > 0 cannot be interpreted.
            raise ValidationError("total_amount_not_positive")
        fraction = ingested_value / total_amount
    # (0, 1] since decision 2026-09-22: eating nothing is not a
    # confirm; an event nobody ate is deleted, not confirmed.
    if not (0.0 < fraction <= 1.0):
        raise ValidationError("fraction_out_of_range")

    # amount_confidence is a proportion: a uniform scale of every portion
    # does not change it, so it is computed on the served portions, before
    # scaling them (§6.9.1). quality_confidence and *_uncertainty are not
    # stored: they are computed live (§6.9.4).
    metrics = calculate_macro_summary_metrics(portions)
    update_payload = IntakeEventUpdate(
        ingested_amount=total_amount * fraction,
        amount_confidence=metrics["amount_confidence"],
    )

    # Ownership + idempotency in a single statement (§6.6).
    confirm_intake_event(connection, user_id=user_id, event_id=event_id, commit=False)
    # amount = amount * fraction for every portion of the event, in a
    # single SQL statement (§6.9.1).
    scale_event_portion_amounts(connection, user_id, event_id, fraction, commit=False)
    update_intake_event(connection, user_id=user_id, event_id=event_id, data=update_payload, commit=False)
    # Automatic injection: returns an id or None (event without insulin).
    create_injection_for_event(connection, user_id=user_id, intake_event_id=event_id, commit=False)
