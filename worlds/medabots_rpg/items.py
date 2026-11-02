"""Items: classification, item groups and construction of the item pool."""
from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from BaseClasses import Item, ItemClassification

from .constants import GAME_NAME, KIND_CONSUMABLE, KIND_MEDAL, KIND_PART, KIND_TRAP
from .data_loader import ItemDef, WorldData

if TYPE_CHECKING:
    from .options import MedabotsOptions


class MedabotsItem(Item):
    game = GAME_NAME


def item_name_groups(data: WorldData) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    for item in data.items:
        for group in item.groups:
            groups.setdefault(group, set()).add(item.name)
    return groups


def item_classification(item: ItemDef, options: MedabotsOptions) -> ItemClassification:
    """Parts and medals only count as progression when the logic or the goal actually looks at them."""
    if item.kind == KIND_PART:
        needed = options.battle_logic.value != options.battle_logic.option_off
        needed = needed or options.goal.value == options.goal.option_collect_medaparts
        return ItemClassification.progression if needed else ItemClassification.useful
    if item.kind == KIND_MEDAL:
        needed = options.goal.value == options.goal.option_collect_medals
        return ItemClassification.progression if needed else ItemClassification.useful
    if item.kind == KIND_TRAP:
        return ItemClassification.trap
    return ItemClassification.filler


def eligible_parts_and_medals(data: WorldData, options: MedabotsOptions) -> tuple[list[ItemDef], list[ItemDef]]:
    """Medaparts and medals that may appear in the item pool."""
    allow_exclusive = bool(options.include_version_exclusives)
    excluded_medals = set(data.pool_exclusions["medals"])
    excluded_bots = set(data.pool_exclusions["bots"])

    def allowed(item: ItemDef) -> bool:
        return allow_exclusive or item.version_exclusive is None

    parts = [i for i in data.items if i.kind == KIND_PART and allowed(i) and i.data["bot"] not in excluded_bots]
    medals = [i for i in data.items if i.kind == KIND_MEDAL and allowed(i)
              and data.tables.medals[i.data["medal_id"]] not in excluded_medals]
    return parts, medals


def supported_traps(data: WorldData) -> list[ItemDef]:
    """Traps the client can actually apply.

    A verified memory map must contain every entry a trap needs, otherwise that trap is dropped. An unverified build
    keeps all traps so that the generator can still be exercised.
    """
    traps = [i for i in data.items if i.kind == KIND_TRAP]
    if not data.memory_map.verified:
        return traps
    return [t for t in traps if data.memory_map.has(*t.data["requires"])]


def allocate(total: int, weights: Mapping[str, int], caps: Mapping[str, int]) -> dict[str, int]:
    """Split ``total`` between the keys in proportion to ``weights`` without exceeding any cap.

    Keys missing from ``caps`` are uncapped. Uses largest-remainder rounding and re-distributes whatever a capped key
    cannot take. Anything that still cannot be placed (every active key capped) is simply left out of the result for
    the caller to handle.
    """
    result = dict.fromkeys(weights, 0)
    active = {key: weight for key, weight in weights.items() if weight > 0}
    remaining = total
    while remaining > 0 and active:
        weight_sum = sum(active.values())
        shares = {key: remaining * weight / weight_sum for key, weight in active.items()}
        amounts = {key: int(share) for key, share in shares.items()}
        leftover = remaining - sum(amounts.values())
        for key in sorted(active, key=lambda k: shares[k] - amounts[k], reverse=True)[:leftover]:
            amounts[key] += 1
        for key in list(active):
            room = amounts[key] if key not in caps else max(0, caps[key] - result[key])
            take = min(amounts[key], room)
            result[key] += take
            remaining -= take
            if take < amounts[key]:
                del active[key]  # capped: its share goes to the others on the next round
    return result


@dataclass
class PoolPlan:
    """The outcome of item pool construction."""

    item_names: list[str]
    goal_medal_count: int
    goal_part_count: int
    notes: list[str] = field(default_factory=list)

    def count(self, data: WorldData, kind: str) -> int:
        return sum(1 for name in self.item_names if data.item_by_name[name].kind == kind)


def build_item_pool(
    data: WorldData, options: MedabotsOptions, slots: int, filler_only_slots: int, rng: random.Random
) -> PoolPlan:
    """Choose exactly ``slots`` items.

    ``filler_only_slots`` locations (excluded ones) can only take filler, so at least that many money pouches or traps
    are always created. Items needed by a collection goal are placed first.
    """
    parts, medals = eligible_parts_and_medals(data, options)
    notes: list[str] = []
    free_slots = slots - filler_only_slots

    goal_medals = goal_parts = 0
    asked_medals = options.goal_medal_count.value
    asked_parts = options.goal_part_count.value
    if options.goal.value == options.goal.option_collect_medals:
        goal_medals = min(asked_medals, len(medals), free_slots)
        if goal_medals < asked_medals:
            notes.append(f"Goal medal count lowered from {asked_medals} to {goal_medals} to fit the pool.")
    elif options.goal.value == options.goal.option_collect_medaparts:
        goal_parts = min(asked_parts, len(parts), free_slots)
        if goal_parts < asked_parts:
            notes.append(f"Goal medapart count lowered from {asked_parts} to {goal_parts} to fit the pool.")
    free_slots -= goal_medals + goal_parts

    counts = allocate(
        free_slots,
        {"part": options.part_weight.value, "medal": options.medal_weight.value, "money": options.money_weight.value},
        {"part": len(parts) - goal_parts, "medal": len(medals) - goal_medals},
    )
    money = free_slots - counts["part"] - counts["medal"] + filler_only_slots

    chosen_parts = rng.sample(parts, goal_parts + counts["part"])
    chosen_medals = rng.sample(medals, goal_medals + counts["medal"])
    names = [i.name for i in chosen_parts] + [i.name for i in chosen_medals]
    names += _money_and_traps(data, options, money, rng, notes)

    assert len(names) == slots, f"item pool has {len(names)} items for {slots} slots"
    return PoolPlan(names, goal_medals, goal_parts, notes)


def _money_and_traps(
    data: WorldData, options: MedabotsOptions, count: int, rng: random.Random, notes: list[str]
) -> list[str]:
    """``count`` filler items: money pouches, of which ``trap_percentage`` percent are replaced by traps."""
    pouches = [i for i in data.items if i.kind == KIND_CONSUMABLE]
    names = [p.name for p in rng.choices(pouches, weights=[p.data["weight"] for p in pouches], k=count)]

    trap_count = round(count * options.trap_percentage.value / 100)
    requested = [t for t in data.items if t.kind == KIND_TRAP and options.trap_weights.get(t.name, 0) > 0]
    usable = [t for t in supported_traps(data) if t in requested]
    if trap_count and requested and not usable:
        notes.append("Traps were requested, but the client cannot apply any of them yet, so none were added.")
    elif trap_count and usable:
        weights = [options.trap_weights[t.name] for t in usable]
        for index, trap in enumerate(rng.choices(usable, weights=weights, k=trap_count)):
            names[index] = trap.name
    return names


def pouch_name_for_filler(data: WorldData, rng: random.Random) -> str:
    pouches = [i for i in data.items if i.kind == KIND_CONSUMABLE]
    return rng.choices(pouches, weights=[p.data["weight"] for p in pouches])[0].name
