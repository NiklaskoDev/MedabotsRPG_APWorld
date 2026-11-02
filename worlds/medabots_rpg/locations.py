"""Locations: which checks exist for a given set of options."""
from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Location, LocationProgressType

from .constants import GAME_NAME
from .data_loader import LocationDef, WorldData

if TYPE_CHECKING:
    from .options import MedabotsOptions

CATEGORY_OPTIONS = {
    "medal": "shuffle_medal_pickups",
    "chest": "shuffle_chests_and_pickups",
    "npc_gift": "shuffle_npc_gifts",
    "boss": "shuffle_boss_rewards",
    "minigame": "shuffle_minigame_prizes",
    "shop": "shopsanity",
    "battle": "trainer_robattles",
}
"""Location category (from locations.json) -> the YAML option that switches it on."""


class MedabotsLocation(Location):
    game = GAME_NAME


def select_locations(data: WorldData, options: MedabotsOptions) -> list[LocationDef]:
    """The checks that exist for these options, in data order."""
    return [loc for loc in data.locations if getattr(options, CATEGORY_OPTIONS[loc.category])]


def progress_type(location: LocationDef, options: MedabotsOptions) -> LocationProgressType:
    """Missable locations may only hold filler unless the player opted in to losing items."""
    if location.missable and not options.include_missable_locations:
        return LocationProgressType.EXCLUDED
    return LocationProgressType.DEFAULT


def location_name_groups(data: WorldData) -> dict[str, set[str]]:
    """Locations grouped by area and by category, for hints and ``exclude_locations``."""
    groups: dict[str, set[str]] = {}
    for loc in data.locations:
        groups.setdefault(loc.area, set()).add(loc.name)
        groups.setdefault(data.location_categories[loc.category], set()).add(loc.name)
    return groups
