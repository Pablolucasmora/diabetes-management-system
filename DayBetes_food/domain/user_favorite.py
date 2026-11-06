"""Dataclass of `user_favorites` (conventions/code_conventions.md §11.2.5)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class UserFavoriteAccess:
    """What a viewer has on a food they can see."""

    is_favorite: bool
    # The favorite is all that keeps the food visible: removing it loses access.
    is_only_access: bool
