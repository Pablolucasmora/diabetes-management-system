"""Database query operations.

Un módulo por tabla (`users.py`, `catalog.py`, `manual_intake.py`,
`recipe.py`, `tags.py`, `linked_tags.py`, `user_favorites.py`,
`food_brands.py`, `intake_event.py`, `insulin_injections.py`,
`portion_detail.py`, `auth_sessions.py`, `auth_rate_limits.py`), más
`entries.py` para lecturas cross-entity sin tabla dueña y `crud.py` con los
helpers genéricos compartidos (privados, no se re-exportan aquí).

Este paquete re-exporta toda la API pública para que el resto de la app
importe siempre `from DayBetes_food.database.queries import <nombre>`, sin
conocer en qué archivo vive cada query (code_conventions.md §1.3.1).
"""

from DayBetes_food.database.queries.users import (
    get_users_by_email,
    get_all_users,
    update_password_hash,
)
from DayBetes_food.database.queries.food_brands import (
    clean_brand_label,
    brand_code,
    create_food_brand,
    get_food_brand_id_by_label,
    get_food_brand_suggestions,
)
from DayBetes_food.database.queries.catalog import (
    add_catalog_item,
    get_catalog_item,
    get_catalog_item_by_barcode,
    get_all_catalog,
    catalog_name_brand_exists,
    update_catalog_item,
    delete_catalog_item,
)
from DayBetes_food.database.queries.manual_intake import (
    get_manual_origin_suggestions,
    add_manual_intake,
    get_manual_intake,
    get_all_manual_intakes,
    manual_intake_name_origin_exists,
    update_manual_intake,
    delete_manual_intake,
)
from DayBetes_food.database.queries.recipe import (
    add_recipe,
    get_recipe,
    get_all_recipes,
    update_recipe,
    delete_recipe,
)
from DayBetes_food.database.queries.tags import (
    get_tag_suggestions,
    ensure_tag,
    get_all_tags,
    update_tag,
)
from DayBetes_food.database.queries.linked_tags import (
    get_entry_tags,
    set_entry_tags,
)
from DayBetes_food.database.queries.user_favorites import (
    toggle_user_favorite,
    set_user_favorite,
)
from DayBetes_food.database.queries.entries import (
    get_subtype_suggestions,
    get_category_suggestions,
    get_rescue_entries_suggestions,
    get_consumed_food_usage_rankings,
)
from DayBetes_food.database.queries.intake_event import (
    create_intake_event,
    get_intake_event,
    list_planned_intake_events,
    list_consumed_intake_events_for_day,
    list_consumed_intake_events,
    update_intake_event,
    delete_intake_event,
    update_intake_event_name,
    set_injection_zone,
    create_injection_for_event,
    confirm_intake_event,
    archive_intake_event,
    restore_intake_event,
    get_planned_intake_event,
)
from DayBetes_food.database.queries.portion_detail import (
    add_portion_detail,
    get_portion_detail_by_event,
    get_event_portion_rows_by_origin,
    delete_event_portion_group,
    consolidate_event_portion_group_amount,
    scale_event_portion_amounts,
    update_event_portion_group_field,
    get_portion_detail_by_events,
    get_portion_detail_by_recipe,
    get_portion_detail,
    update_portion_detail_amount,
    update_portion_detail_fields,
    delete_portion_detail,
    get_recipe_portion_by_origin,
    get_recipe_portions_by_origin,
)
from DayBetes_food.database.queries.insulin_injections import (
    create_insulin_injection,
    list_insulin_injections,
    get_insulin_injection,
    get_injection_shot_time_at_offset,
    update_insulin_injection,
    delete_insulin_injection,
)
from DayBetes_food.database.queries.auth_sessions import (
    create_auth_session,
    get_auth_session_with_user,
    refresh_auth_session,
    revoke_auth_session,
    purge_auth_sessions,
)
from DayBetes_food.database.queries.auth_rate_limits import (
    get_auth_rate_limit,
    upsert_auth_rate_limit,
    delete_auth_rate_limit,
)

__all__ = [
    "get_users_by_email",
    "get_all_users",
    "update_password_hash",
    "clean_brand_label",
    "brand_code",
    "create_food_brand",
    "get_food_brand_id_by_label",
    "get_food_brand_suggestions",
    "add_catalog_item",
    "get_catalog_item",
    "get_catalog_item_by_barcode",
    "get_all_catalog",
    "catalog_name_brand_exists",
    "update_catalog_item",
    "delete_catalog_item",
    "get_manual_origin_suggestions",
    "add_manual_intake",
    "get_manual_intake",
    "get_all_manual_intakes",
    "manual_intake_name_origin_exists",
    "update_manual_intake",
    "delete_manual_intake",
    "add_recipe",
    "get_recipe",
    "get_all_recipes",
    "update_recipe",
    "delete_recipe",
    "get_tag_suggestions",
    "ensure_tag",
    "get_all_tags",
    "update_tag",
    "get_entry_tags",
    "set_entry_tags",
    "toggle_user_favorite",
    "set_user_favorite",
    "get_subtype_suggestions",
    "get_category_suggestions",
    "get_rescue_entries_suggestions",
    "get_consumed_food_usage_rankings",
    "create_intake_event",
    "get_intake_event",
    "list_planned_intake_events",
    "list_consumed_intake_events_for_day",
    "list_consumed_intake_events",
    "update_intake_event",
    "delete_intake_event",
    "update_intake_event_name",
    "set_injection_zone",
    "create_injection_for_event",
    "confirm_intake_event",
    "archive_intake_event",
    "restore_intake_event",
    "get_planned_intake_event",
    "add_portion_detail",
    "get_portion_detail_by_event",
    "get_event_portion_rows_by_origin",
    "delete_event_portion_group",
    "consolidate_event_portion_group_amount",
    "scale_event_portion_amounts",
    "update_event_portion_group_field",
    "get_portion_detail_by_events",
    "get_portion_detail_by_recipe",
    "get_portion_detail",
    "update_portion_detail_amount",
    "update_portion_detail_fields",
    "delete_portion_detail",
    "get_recipe_portion_by_origin",
    "get_recipe_portions_by_origin",
    "create_insulin_injection",
    "list_insulin_injections",
    "get_insulin_injection",
    "get_injection_shot_time_at_offset",
    "update_insulin_injection",
    "delete_insulin_injection",
    "create_auth_session",
    "get_auth_session_with_user",
    "refresh_auth_session",
    "revoke_auth_session",
    "purge_auth_sessions",
    "get_auth_rate_limit",
    "upsert_auth_rate_limit",
    "delete_auth_rate_limit",
]
