"""Logic: JSON rule expressions compiled to Archipelago's rule builder, and the battle-logic gate thresholds."""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from rule_builder.rules import And, Has, HasGroup, Or, Rule, True_

from .data_loader import DataError, WorldData


def compile_rule(expr: Any) -> Rule[Any]:
    """Turn a JSON rule expression (see ``data_loader.rule_problems`` for the grammar) into a rule builder rule."""
    if expr is None:
        return True_()
    if isinstance(expr, str):
        return Has(expr)
    if isinstance(expr, dict):
        count = expr.get("count", 1)
        if "all" in expr:
            return And(*(compile_rule(child) for child in expr["all"]))
        if "any" in expr:
            return Or(*(compile_rule(child) for child in expr["any"]))
        if "has" in expr:
            return Has(expr["has"], count=count)
        if "group" in expr:
            return HasGroup(expr["group"], count=count)
    raise DataError(f"Unknown rule expression: {expr!r}")


def part_gate_thresholds(
    data: WorldData, mode: str, parts_in_pool: int, locations_per_area: Mapping[str, int]
) -> dict[str, int]:
    """How many medaparts the player must hold to enter each area.

    The requirement grows linearly from nothing in the first area to ``final_parts_fraction`` of all medaparts in the
    pool in the last one. It is capped by a share of the locations in the *earlier* areas, which guarantees that enough
    parts can physically be found before the gate, so the gate can never make a seed unbeatable.
    """
    profile = data.rules["battle_logic"].get(mode)
    if profile is None or parts_in_pool <= 0:
        return {}
    cap_share = data.rules["max_gate_share_of_prior_locations"]
    last_index = max(len(data.areas) - 1, 1)

    thresholds: dict[str, int] = {}
    earlier_locations = 0
    for area in data.areas:
        wanted = math.ceil(profile["final_parts_fraction"] * parts_in_pool * area.index / last_index)
        capped = min(wanted, parts_in_pool, math.floor(earlier_locations * cap_share))
        if capped > 0:
            thresholds[area.name] = capped
        earlier_locations += locations_per_area.get(area.name, 0)
    return thresholds
