"""Game-state logic of the client, free of BizHawk and the network so that it can be tested on its own.

The client reads one consistent *snapshot* of the game's memory, asks this module what to do, and applies the answer
with guarded writes. Nothing here touches memory directly: every change is computed on a private copy and returned as
a list of writes plus the bytes each write expects to find (its guard). If the game changed in between, the guard
fails, nothing is written and the same step is simply planned again, which is what makes delivery safe (invariant G8).

Medaparts and medals are *state based*: they are ensured to be owned, so repeating a step or loading an older save is
harmless. Money and traps are *counted*: a persistent index records how many received items were already processed.

The game keeps medals as full records (a medal case), not as bits. A received medal is written as the exact record the
game's own "give medal" routine would build, from the medal's 16-byte entry in the ROM's medal table (which the client
reads once and passes in as ``medal_table``).
"""
from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from .constants import (
    EVENT_FLAG_BITS,
    EVENT_VALUE_SHIFTS,
    KIND_CONSUMABLE,
    KIND_MEDAL,
    KIND_PART,
    KIND_TRAP,
    MEDAL_TABLE_ENTRY_SIZE,
    PART_SLOTS,
)
from .data_loader import ItemDef, MemoryMap, TableRef, WorldData

_NUMERIC_KINDS = ("u8", "u16", "u32")
MAX_DELIVERIES_PER_TICK = 4
TRAP_TIMEOUT_SECONDS = 300
"""A trap's effect is always lifted after this long, even if the game never reports the end of a battle."""

# What each memory-poking trap writes to undo itself. ``None`` means the game clears the flag on its own.
_TRAP_REVERT_VALUE = {"rusty_armor": 100, "medal_nap": 0, "ambush": None}
_TRAP_TABLE = {
    "rusty_armor": "optional_tables.battle_armor_scale",
    "medal_nap": "optional_tables.battle_medal_disable",
    "ambush": "optional_tables.force_encounter",
}


# ---------------------------------------------------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------------------------------------------------
def readable_tables(memory_map: MemoryMap) -> list[tuple[str, TableRef]]:
    """Every table and state flag of the memory map that is known, with its dotted path.

    A state flag made of several conditions contributes one entry per condition (``state.name``, ``state.name+1``…).
    """
    found: list[tuple[str, TableRef]] = []
    for section in ("tables", "state", "optional_tables"):
        for name, ref in getattr(memory_map, section).items():
            if ref is not None:
                found.append((f"{section}.{name}", ref))
                found += [(f"{section}.{name}+{i}", extra) for i, extra in enumerate(ref.also, 1)]
    return found


class Snapshot:
    """One consistent read of every known table, keyed by dotted memory-map path."""

    def __init__(self, memory_map: MemoryMap, raw: Mapping[str, bytes]):
        self.memory_map = memory_map
        self.raw = dict(raw)

    def flag_is_set(self, table: str, bit: int) -> bool:
        raw = self.raw.get(f"tables.{table}")
        return raw is not None and (bit >> 3) < len(raw) and bool(raw[bit >> 3] & (1 << (bit & 7)))

    def event_value(self, flag: int) -> int | None:
        """The 3-bit value the game stores next to event ``flag`` (``None`` when the flag table is unknown)."""
        raw = self.raw.get("tables.game_flags")
        if raw is None or (flag >> 1) >= len(raw):
            return None
        return (raw[flag >> 1] >> EVENT_VALUE_SHIFTS[flag & 1]) & 7

    def detected(self, detect: Mapping | None) -> bool:
        """Whether a ``detect`` entry of locations.json / regions.json is satisfied."""
        kind = detect.get("type") if detect else None
        if kind == "flag":
            return self.flag_is_set(detect["table"], detect["bit"])
        if kind == "event":
            return self.flag_is_set("game_flags", event_flag_bit(detect["flag"]))
        if kind == "event_value":
            value = self.event_value(detect["flag"])
            return value is not None and value >= detect["value"]
        return False

    def state_is_set(self, name: str) -> bool | None:
        """Whether a state flag is on (every one of its conditions), or ``None`` when its address is not known."""
        ref = self.memory_map.state.get(name)
        if ref is None:
            return None
        result = True
        for i, condition in enumerate((ref, *ref.also)):
            raw = self.raw.get(f"state.{name}" + (f"+{i}" if i else ""))
            if not raw:
                return None
            result = result and (raw[0] in condition.values if condition.values else bool(raw[0]))
        return result


def event_flag_bit(flag: int) -> int:
    """Bit index (from the start of the game_flags table) of event ``flag``'s done flag: two events share a byte."""
    return (flag >> 1) * 8 + EVENT_FLAG_BITS[flag & 1]


class _Workspace:
    """A mutable copy of a snapshot used to compute writes."""

    def __init__(self, snapshot: Snapshot, medal_table: bytes | None = None):
        self.memory_map = snapshot.memory_map
        self.original = snapshot.raw
        self.buffers = {path: bytearray(raw) for path, raw in snapshot.raw.items()}
        self.medal_table = medal_table

    def ref(self, path: str) -> TableRef | None:
        return self.memory_map.resolve(path) if path in self.buffers else None

    def changes(self) -> tuple[list[tuple[int, bytes]], list[tuple[int, bytes]]]:
        """(writes, guards) for every changed table, and the bytes each write expects to replace.

        Bitfields and byte arrays write only the span that differs. Numbers (money, trap values) are always written
        and guarded as a whole, so a half-updated value can never be produced.
        """
        writes, guards = [], []
        for path, new in self.buffers.items():
            old = self.original[path]
            changed = [i for i, (a, b) in enumerate(zip(old, new, strict=True)) if a != b]
            if not changed:
                continue
            ref = self.memory_map.resolve(path)
            first, last = (0, len(new)) if ref.kind in _NUMERIC_KINDS else (changed[0], changed[-1] + 1)
            address = ref.address + first
            writes.append((address, bytes(new[first:last])))
            guards.append((address, bytes(old[first:last])))
        return writes, guards

    # -- primitive operations ----------------------------------------------------------------------------------------
    def set_ownership(self, path: str, index: int) -> bool:
        """Make sure entry ``index`` of an ownership table is set. ``False`` if the table is unknown or too small."""
        ref, buffer = self.ref(path), self.buffers.get(path)
        if ref is None or buffer is None:
            return False
        if ref.kind == "bitfield":
            if (index >> 3) >= len(buffer):
                return False
            buffer[index >> 3] |= 1 << (index & 7)
        else:
            position = index * ref.stride
            if position >= len(buffer):
                return False
            buffer[position] = max(buffer[position], 1)
        return True

    def ensure_medal_record(self, path: str, medal_id: int, name: str) -> bool:
        """Make sure the medal case holds ``medal_id``, adding a record built like the game does when it does not.

        ``False`` if the table, the ROM medal table or a free slot is missing.
        """
        ref, buffer = self.ref(path), self.buffers.get(path)
        if ref is None or buffer is None or self.medal_table is None:
            return False
        size = ref.record_size
        records = [buffer[i:i + size] for i in range(0, len(buffer), size)]
        if any(rec[0] & 0x80 and rec[1] == medal_id for rec in records):
            return True
        free = next((i for i, rec in enumerate(records) if not rec[0] & 0x80), None)
        entry = self.medal_table[medal_id * MEDAL_TABLE_ENTRY_SIZE:(medal_id + 1) * MEDAL_TABLE_ENTRY_SIZE]
        if free is None or len(entry) != MEDAL_TABLE_ENTRY_SIZE:
            return False
        levels = [rec[5] if rec[0] & 0x80 else 0 for rec in records]
        buffer[free * size:(free + 1) * size] = new_medal_record(medal_id, entry, levels, records[free][0], name, size)
        return True

    def number(self, path: str) -> int | None:
        buffer = self.buffers.get(path)
        return None if buffer is None else int.from_bytes(buffer, "little")

    def set_number(self, path: str, value: int) -> None:
        ref, buffer = self.memory_map.resolve(path), self.buffers[path]
        value = max(0, min(value, ref.maximum if ref.maximum is not None else (1 << (8 * len(buffer))) - 1))
        buffer[:] = value.to_bytes(len(buffer), "little")


def new_medal_record(medal_id: int, entry: bytes, levels: Sequence[int], slot_byte: int, name: str, size: int) -> bytes:
    """The record the game's own "give medal" routine (0x08041D70 in Metabee USA) writes for a new medal.

    ``entry`` is the medal's 16-byte line of the ROM medal table, ``levels`` the levels in every slot of the medal case
    (0 for empty slots) and ``slot_byte`` the first byte of the free slot, whose low bits the game keeps. The name is
    normally typed by the player on a naming screen; the medal's own name is the game's default there.
    """
    ranked = sorted(levels, reverse=True) + [0] * 4
    level = (ranked[0] - ranked[3]) // 2 + ranked[3]  # half way between the best and the fourth best medal
    record = bytearray(size)
    record[0] = 0x80 | (slot_byte & 0x7F)
    record[1] = medal_id
    record[2:4] = ((level + 1) * 100).to_bytes(2, "little")
    record[4], record[5], record[6], record[7] = entry[1], level, entry[2], entry[7]
    record[8] = next((rank for rank in (4, 3, 2, 1) if entry[2 + rank] and level >= entry[2 + rank]), 0)
    letters = bytes(ord(c) - 0x40 for c in name.upper() if "A" <= c <= "Z")[:10]
    record[0x0A:0x18] = letters.ljust(14, b"\xFE")
    for i in range(8):
        record[0x20 + i] = min(100, (level // 10 + 1) * entry[8 + i])
    return bytes(record)


def part_index(ref: TableRef, data: WorldData, model: int, slot: int) -> int:
    if ref.layout == "slot_major":
        return slot * len(data.tables.bots) + model
    return model * len(PART_SLOTS) + slot


# ---------------------------------------------------------------------------------------------------------------------
# Locations and goal
# ---------------------------------------------------------------------------------------------------------------------
def detect_checked_locations(data: WorldData, snapshot: Snapshot, wanted: Iterable[int]) -> set[int]:
    """IDs among ``wanted`` whose check is visible in the snapshot."""
    wanted = set(wanted)
    return {location.id for location in data.locations
            if location.id in wanted and snapshot.detected(location.detect)}


def story_complete(data: WorldData, snapshot: Snapshot) -> bool:
    return snapshot.detected(data.goal_detect)


def collection_goal_reached(data: WorldData, received: Sequence[str], goal: str, medals: int, parts: int) -> bool:
    if goal == "collect_medals":
        kind, needed = KIND_MEDAL, medals
    elif goal == "collect_medaparts":
        kind, needed = KIND_PART, parts
    else:
        return False
    unique = {name for name in received if (item := data.item_by_name.get(name)) and item.kind == kind}
    return len(unique) >= needed > 0


# ---------------------------------------------------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Received:
    name: str
    sender: str
    advancement: bool


@dataclass
class ActiveTrap:
    key: str
    battles_left: int
    started_at: float


@dataclass
class ClientState:
    applied_index: int = 0
    """How many of the received items have been fully processed (persisted on the server)."""
    traps: list[ActiveTrap] = field(default_factory=list)
    was_in_battle: bool = False


@dataclass
class StepResult:
    writes: list[tuple[int, bytes]]
    guards: list[tuple[int, bytes]]
    announcements: list[str]
    state: ClientState
    """The state to adopt once the writes have been applied."""


def _grant(data: WorldData, ws: _Workspace, item: ItemDef) -> bool:
    if item.kind == KIND_PART:
        ref = data.memory_map.tables.get("parts_owned")
        return ref is not None and ws.set_ownership(
            "tables.parts_owned", part_index(ref, data, item.data["model"], item.data["slot"]))
    ref = data.memory_map.tables.get("medals_owned")
    if ref is not None and ref.kind == "records":
        medal_id = item.data["medal_id"]
        return ws.ensure_medal_record("tables.medals_owned", medal_id, data.tables.medals[medal_id])
    return ref is not None and ws.set_ownership("tables.medals_owned", item.data["medal_id"])


def _add_money(ws: _Workspace, amount: int) -> bool:
    current = ws.number("tables.money")
    if current is None:
        return False
    ws.set_number("tables.money", current + amount)
    return True


def _start_trap(data: WorldData, ws: _Workspace, state: ClientState, key: str, strength: str, now: float) -> None:
    """Begin a trap's effect. Traps whose memory entries are unknown fizzle out instead of guessing."""
    levels = data.rules["trap_strength"][key]
    if key == "money_drain":
        current = ws.number("tables.money")
        if current is not None:
            ws.set_number("tables.money", current - current * levels[strength] // 100)
        return
    path = _TRAP_TABLE[key]
    if path not in ws.buffers:
        return
    value = levels[strength] if key == "rusty_armor" else 1
    ws.buffers[path][:] = value.to_bytes(len(ws.buffers[path]), "little")
    battles = 1 if key == "rusty_armor" else levels[strength]
    state.traps = [t for t in state.traps if t.key != key] + [ActiveTrap(key, battles, now)]


def _update_traps(ws: _Workspace, state: ClientState, in_battle: bool | None, now: float) -> None:
    """Lift traps whose battles are over or that have run for too long."""
    battle_ended = state.was_in_battle and in_battle is False
    still_active: list[ActiveTrap] = []
    for trap in state.traps:
        if battle_ended:
            trap.battles_left -= 1
        expired = trap.battles_left <= 0 or now - trap.started_at > TRAP_TIMEOUT_SECONDS
        path = _TRAP_TABLE[trap.key]
        if expired:
            revert = _TRAP_REVERT_VALUE[trap.key]
            if revert is not None and path in ws.buffers:
                ws.buffers[path][:] = revert.to_bytes(len(ws.buffers[path]), "little")
            continue
        if battle_ended and trap.key == "ambush" and path in ws.buffers:
            ws.buffers[path][:] = (1).to_bytes(len(ws.buffers[path]), "little")  # the next ambush of the series
        still_active.append(trap)
    state.traps = still_active
    if in_battle is not None:
        state.was_in_battle = in_battle


def _announcement(received: Received, own_name: str, mode: str) -> str | None:
    if mode == "none" or (mode == "progression_only" and not received.advancement):
        return None
    if received.sender == own_name:
        return f"Found {received.name}"
    return f"Received {received.name} from {received.sender}"


def plan_step(
    data: WorldData,
    snapshot: Snapshot,
    received: Sequence[Received],
    state: ClientState,
    *,
    own_name: str,
    strength: str,
    message_mode: str,
    now: float,
    repair: bool,
    medal_table: bytes | None = None,
) -> StepResult:
    """Decide what to write for one client tick.

    ``repair`` additionally re-asserts ownership of every received part and medal (silently), which fixes the game
    after an older save was loaded. Nothing is delivered unless the game is known to be in a safe state and not known
    to be in a battle. ``medal_table`` is the ROM's medal table, needed when the medal case holds records.
    """
    ws, new_state = _Workspace(snapshot, medal_table), copy.deepcopy(state)
    announcements: list[str] = []

    in_battle = snapshot.state_is_set("in_battle")
    _update_traps(ws, new_state, in_battle, now)

    if snapshot.state_is_set("safe_to_deliver") and not in_battle:
        if repair:
            for entry in received:
                item = data.item_by_name.get(entry.name)
                if item and item.kind in (KIND_PART, KIND_MEDAL):
                    _grant(data, ws, item)

        delivered = 0
        while new_state.applied_index < len(received) and delivered < MAX_DELIVERIES_PER_TICK:
            entry = received[new_state.applied_index]
            item = data.item_by_name.get(entry.name)
            if item is not None and not _deliver(data, ws, new_state, item, strength, now):
                break  # cannot be delivered right now; try again on a later tick
            if item is not None and (text := _announcement(entry, own_name, message_mode)):
                announcements.append(text)
            new_state.applied_index += 1
            delivered += 1

    writes, guards = ws.changes()
    return StepResult(writes, guards, announcements, new_state)


def _deliver(data: WorldData, ws: _Workspace, state: ClientState, item: ItemDef, strength: str, now: float) -> bool:
    if item.kind in (KIND_PART, KIND_MEDAL):
        return _grant(data, ws, item)
    if item.kind == KIND_CONSUMABLE:
        effect = item.data["effect"]
        return effect["type"] == "money" and _add_money(ws, effect["amount"])
    if item.kind == KIND_TRAP:
        _start_trap(data, ws, state, item.data["trap"], strength, now)
        return True
    return True
