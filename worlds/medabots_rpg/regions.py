"""Regions: one per story area, chained in story order, plus the event locations that open the next area."""
from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from BaseClasses import ItemClassification, Region
from rule_builder.rules import Has, HasGroup

from .constants import GROUP_MEDALS, GROUP_PARTS
from .data_loader import LocationDef
from .items import MedabotsItem
from .locations import MedabotsLocation, progress_type
from .rules import compile_rule

if TYPE_CHECKING:
    from . import MedabotsRPGWorld


def create_regions(
    world: MedabotsRPGWorld, locations: list[LocationDef], gate_thresholds: Mapping[str, int]
) -> None:
    """Build the region graph, the check locations and the story events, and set the completion condition."""
    multiworld, player, data = world.multiworld, world.player, world.data

    menu = Region("Menu", player, multiworld)
    regions = {area.name: Region(area.name, player, multiworld) for area in data.areas}
    multiworld.regions.extend([menu, *regions.values()])

    # Areas are entered in story order. Leaving an area requires its "cleared" event, and entering a later one may
    # additionally require a share of the medaparts (battle logic).
    world.create_entrance(menu, regions[data.areas[0].name], name="Start Game")
    for area in data.areas[1:]:
        parent = data.area_by_name[area.parent]
        rule = Has(parent.clear_event)
        if area.name in gate_thresholds:
            rule = rule & HasGroup(GROUP_PARTS, count=gate_thresholds[area.name])
        world.create_entrance(regions[parent.name], regions[area.name], rule, name=f"Travel to {area.name}")

    for definition in locations:
        location = MedabotsLocation(player, definition.name, definition.id, regions[definition.area])
        location.progress_type = progress_type(definition, world.options)
        world.set_rule(location, compile_rule(definition.requires))
        regions[definition.area].locations.append(location)

    for area in data.areas:
        event = MedabotsLocation(player, f"Clear {area.name}", None, regions[area.name])
        event.place_locked_item(MedabotsItem(area.clear_event, ItemClassification.progression, None, player))
        regions[area.name].locations.append(event)

    world.set_completion_rule(_completion_rule(world))


def _completion_rule(world: MedabotsRPGWorld):
    goal = world.options.goal
    if goal.value == goal.option_collect_medals:
        return HasGroup(GROUP_MEDALS, count=world.pool.goal_medal_count)
    if goal.value == goal.option_collect_medaparts:
        return HasGroup(GROUP_PARTS, count=world.pool.goal_part_count)
    return Has(world.data.goal_event)
