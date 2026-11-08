"""Dataclasses and pure rules of `tags` and `linked_tags` (code_conventions.md §11.2.8).

A tag is either a system tag (`SystemTag`, no owner, the same for every user)
or a personal tag of one user. A link says that one user put one tag on one
food, dish or recipe they can see: links are private, so tagging a food of the
general library changes nothing for anyone else.

This module imports no psycopg, routes or components. The SQL-row-to-dataclass
conversion lives in DayBetes_food/database/mappers.py.
"""

import re
from dataclasses import dataclass

from DayBetes_food.domain.constants import MealType, SystemTag
from DayBetes_food.errors import ValidationError

# Short on purpose: a tag is a pill on a phone screen. The column is VARCHAR(100).
TAG_NAME_MAX_LENGTH = 40

# What the color picker gives (#RRGGBB) or what tag_color_from_name builds.
# Validated because the value ends inside a `style` attribute (§7.3).
TAG_COLOR_PATTERN = r"^(#[0-9A-Fa-f]{6}|hsl\([0-9]{1,3} [0-9]{1,3}% [0-9]{1,3}%\))$"
_TAG_COLOR_RE = re.compile(TAG_COLOR_PATTERN)

# The meal type of each system tag: the tab of the quick log pop-up selects it
# and offers the foods with the tag (frontend_conventions.md §9.6).
SYSTEM_TAG_MEAL_TYPE = {
    SystemTag.RESCUE: MealType.RESCUE,
    SystemTag.EXERCISE: MealType.EXERCISE,
}

# Name and color of each system tag. The name is what the interface shows; the
# tag is identified by its key, so the name is never compared.
SYSTEM_TAG_DEFAULTS = {
    SystemTag.RESCUE: ("Rescue", "#FF0000"),
    SystemTag.EXERCISE: ("Exercise", "#2563EB"),
}


@dataclass(frozen=True)
class TagRead:
    id: int
    user_id: int | None  # None: system tag
    system_key: SystemTag | None
    name: str
    color: str

    @property
    def is_system(self) -> bool:
        return self.system_key is not None


@dataclass(frozen=True)
class TagCreate:
    user_id: int
    name: str
    color: str


@dataclass(frozen=True)
class TagUpdate:
    name: str
    color: str


def _normalize_text(raw) -> str:
    """strip + collapse any whitespace run into one space (§7.3)."""
    return " ".join(str(raw or "").split())


def parse_tag_name(raw) -> str:
    name = _normalize_text(raw)
    if not name:
        raise ValidationError("Give the tag a name.", fields={"name": "required"})
    if len(name) > TAG_NAME_MAX_LENGTH:
        raise ValidationError(
            f"The name must be {TAG_NAME_MAX_LENGTH} characters or fewer.", fields={"name": "too_long"}
        )
    return name


def parse_tag_color(raw) -> str:
    color = str(raw or "").strip()
    if not _TAG_COLOR_RE.match(color):
        raise ValidationError("Choose a valid color.", fields={"color": "invalid"})
    return color.upper() if color.startswith("#") else color


def tag_color_from_name(name: str) -> str:
    """Default color of a new tag: a pastel hue derived from its name."""
    hue = 0
    for ch in _normalize_text(name).lower():
        hue = (hue * 31 + ord(ch)) % 360
    return f"hsl({hue} 80% 90%)"
