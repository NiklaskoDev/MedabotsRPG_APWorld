"""Test helpers: synthetic verified data sets, a synthetic ROM and a fake BizHawk memory.

The shipped data points at real GBA addresses, so everything that reads or writes memory, such as delivering items or
patching, is tested against data built here. ``verified_data`` uses an invented, simple layout (bitfields only);
``shaped_data`` uses the shapes calibration found in the real game (nibble event flags, two-byte part counts and the
medal case of 64-byte records), relocated into the fake RAM window. ``unverified_data`` is the shipped data with one
part of it unconfirmed, for the refusals.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from ..data_loader import DATA_FILES, DictDataSource, PackageDataSource, WorldData, load_world_data

SYSTEM_BUS = "System Bus"
RAM_BASE = 0x02000000
SCRIPT_START = 0x100000
SCRIPT_BANK = SCRIPT_START - 0x8000
TEST_SCRIPT = 1
"""The event script number that ``build_rom``'s ``scripts`` become."""
ROM_SIZE = 0x800000
SCRIPT_REGION_LENGTH = 0x18000

# Synthetic memory layout
FLAGS = RAM_BASE + 0x000
PARTS = RAM_BASE + 0x100
MEDALS = RAM_BASE + 0x200
MONEY = RAM_BASE + 0x300
SAFE = RAM_BASE + 0x400
IN_BATTLE = RAM_BASE + 0x401
IN_FIELD = RAM_BASE + 0x402
ARMOR_SCALE = RAM_BASE + 0x410
MEDAL_DISABLE = RAM_BASE + 0x411
FORCE_ENCOUNTER = RAM_BASE + 0x412
ENCOUNTER_AREA = RAM_BASE + 0x413

FLAG_BIT_SQUIDGUTS = 5
FLAG_BIT_MEDAL_ROOM = 9
FLAG_BIT_STORY_COMPLETE = 100

# Layout with the real shapes (see shaped_data)
SHAPED_FLAGS = RAM_BASE + 0x1000
SHAPED_PARTS = RAM_BASE + 0x1800
SHAPED_MEDALS = RAM_BASE + 0x1C00
SHAPED_MONEY = RAM_BASE + 0x2400
SHAPED_SAFE = RAM_BASE + 0x2410
SHAPED_MODE = RAM_BASE + 0x2411
SHAPED_SCENE = RAM_BASE + 0x2412
SHAPED_ENCOUNTER = RAM_BASE + 0x2413
SHAPED_ENCOUNTER_AREA = RAM_BASE + 0x2414
CHAPTER_BYTE = 2047
"""Offset of the chapter counter in the game_flags table (the last chapter is 9)."""

SMALL_POUCH, MEDIUM_POUCH, LARGE_POUCH = 1000, 5000, 20000
"""What the money pouches add, in cents ($10, $50, $200); test_data checks them against items.json."""


def medal_table() -> bytes:
    """An invented ROM medal table (30 entries of 16 bytes) shaped like the game's."""
    return b"".join(bytes([i, i, 1, 30, 60, 0xFF, 0xFF, 7, 8, 0, 8, 0, 0, 0, 6, 6]) for i in range(30))


def raw_data() -> dict[str, Any]:
    """The shipped JSON files as plain dictionaries (deep copies, safe to modify)."""
    source = PackageDataSource()
    return {name: json.loads(source.read(name)) for name in DATA_FILES}


def unverified_data() -> WorldData:
    """The shipped data with its story goal set back to a candidate, which makes the whole world unverified."""
    raw = copy.deepcopy(raw_data())
    raw["regions"]["goal_status"] = "candidate"
    return load_world_data(DictDataSource(raw))


def gendered_data() -> WorldData:
    """The shipped data with invented part genders: a quarter of the models female, never Metabee (model 42)."""
    raw = copy.deepcopy(raw_data())
    bots = raw["game_tables"]["bots"]
    raw["game_tables"]["bot_genders"] = ["female" if model % 4 == 1 else "male" for model in range(len(bots))]
    return load_world_data(DictDataSource(raw))


def verified_data(parts_layout: str = "model_major", with_optional: bool = True,
                  with_encounter_area: bool = True) -> WorldData:
    """The shipped data with a complete, invented memory map and verified locations.

    ``with_optional=False`` leaves the trap-only tables unknown, as a real calibration might;
    ``with_encounter_area=False`` leaves only the encounter-area byte unknown.
    """
    raw = copy.deepcopy(raw_data())
    ref = lambda address, kind, size, **extra: {"address": hex(address), "kind": kind, "size": size, **extra}  # noqa: E731
    raw["memory_map"].update(
        verified=True,
        tables={
            "game_flags": ref(FLAGS, "bitfield", 64),
            "parts_owned": ref(PARTS, "bitfield", 60, layout=parts_layout),
            "medals_owned": ref(MEDALS, "bitfield", 4),
            "money": ref(MONEY, "u32", 4, maximum=999_999),
        },
        state={
            "safe_to_deliver": ref(SAFE, "bytes", 1, values=[0]),
            "in_battle": ref(IN_BATTLE, "bytes", 1),
            "in_field": ref(IN_FIELD, "bytes", 1, values=[1]),
        },
        optional_tables={
            "battle_armor_scale": ref(ARMOR_SCALE, "u8", 1) if with_optional else None,
            "battle_medal_disable": ref(MEDAL_DISABLE, "u8", 1) if with_optional else None,
            "force_encounter": ref(FORCE_ENCOUNTER, "u8", 1) if with_optional else None,
            "encounter_area": ref(ENCOUNTER_AREA, "u8", 1) if with_optional and with_encounter_area else None,
        },
    )
    raw["regions"]["goal_detect"] = {"type": "flag", "table": "game_flags", "bit": FLAG_BIT_STORY_COMPLETE}
    raw["regions"]["goal_status"] = "verified"
    for entry in raw["locations"]["locations"]:
        if entry["status"] != "absent":
            entry["status"] = "verified"
        entry["detect"] = {"type": "flag", "table": "game_flags", "bit": entry["id"] % 50 + 20}
    by_id = {entry["id"]: entry for entry in raw["locations"]["locations"]}
    by_id[20003]["detect"]["bit"] = FLAG_BIT_SQUIDGUTS
    by_id[20001]["detect"]["bit"] = FLAG_BIT_MEDAL_ROOM
    return load_world_data(DictDataSource(raw))


def shaped_data() -> WorldData:
    """The shipped memory map shapes moved into the fake RAM window, with every existing location verified."""
    raw = copy.deepcopy(raw_data())
    tables = raw["memory_map"]["tables"]
    for name, address in (("game_flags", SHAPED_FLAGS), ("parts_owned", SHAPED_PARTS),
                          ("medals_owned", SHAPED_MEDALS), ("money", SHAPED_MONEY)):
        tables[name]["address"] = hex(address)
    state = raw["memory_map"]["state"]
    state["safe_to_deliver"][0]["address"], state["safe_to_deliver"][1]["address"] = hex(SHAPED_SAFE), hex(SHAPED_MODE)
    state["in_battle"][0]["address"], state["in_battle"][1]["address"] = hex(SHAPED_MODE), hex(SHAPED_SCENE)
    state["in_field"]["address"] = hex(SHAPED_MODE)
    raw["memory_map"]["optional_tables"]["force_encounter"]["address"] = hex(SHAPED_ENCOUNTER)
    raw["memory_map"]["optional_tables"]["encounter_area"]["address"] = hex(SHAPED_ENCOUNTER_AREA)
    raw["regions"]["goal_status"] = "verified"
    for entry in raw["locations"]["locations"]:
        if entry["status"] != "absent":
            entry["status"] = "verified"
            entry.setdefault("detect", {"type": "event", "flag": entry["id"] - 18000})
    return load_world_data(DictDataSource(raw))


class FakeMemory:
    """A tiny GBA memory: a RAM window at 0x02000000 plus a ROM image, addressed like BizHawk's domains."""

    def __init__(self, rom: bytes = b""):
        self.ram = bytearray(0x2800)
        self.rom = bytearray(rom)
        self.writes: list[tuple[int, bytes]] = []
        self.fail_next_guard = False
        # The invented layout starts out in the field, on a map with random encounters; tests move it away from there.
        self.ram[IN_FIELD - RAM_BASE] = 1
        self.ram[ENCOUNTER_AREA - RAM_BASE] = 1

    def _domain(self, name: str) -> tuple[bytearray, int]:
        return (self.ram, RAM_BASE) if name == SYSTEM_BUS else (self.rom, 0)

    def read(self, address: int, size: int, domain: str = SYSTEM_BUS) -> bytes:
        buffer, base = self._domain(domain)
        start = address - base
        if start < 0 or start + size > len(buffer):
            raise IndexError(f"read outside {domain}: 0x{address:X}+{size}")
        return bytes(buffer[start:start + size])

    def write(self, address: int, data: bytes, domain: str = SYSTEM_BUS) -> None:
        buffer, base = self._domain(domain)
        buffer[address - base:address - base + len(data)] = data
        self.writes.append((address, bytes(data)))

    # convenience accessors for tests
    def set_bit(self, address: int, bit: int) -> None:
        self.ram[address - RAM_BASE + (bit >> 3)] |= 1 << (bit & 7)

    def bit(self, address: int, bit: int) -> bool:
        return bool(self.ram[address - RAM_BASE + (bit >> 3)] & (1 << (bit & 7)))

    def u32(self, address: int) -> int:
        return int.from_bytes(self.ram[address - RAM_BASE:address - RAM_BASE + 4], "little")

    def set_u32(self, address: int, value: int) -> None:
        self.ram[address - RAM_BASE:address - RAM_BASE + 4] = value.to_bytes(4, "little")

    def byte(self, address: int) -> int:
        return self.ram[address - RAM_BASE]

    def set_byte(self, address: int, value: int) -> None:
        self.ram[address - RAM_BASE] = value


def build_rom(header_id: str = "MEDABOTSMTBVA8BEE9", scripts: bytes = b"", size: int = ROM_SIZE) -> bytes:
    """A blank (0x00, like the real ROMs' free space) ROM image with a valid header and an event-script bank.

    The script region starts with the documented signature, which is itself a 28-byte multi-way-jump instruction
    (script 0), followed by ``scripts`` (script ``TEST_SCRIPT``), an end instruction (script 2) and then one-byte
    no-ops up to the documented region length, so the whole region parses. The bank header and index tables sit
    0x8000 before the region, as in the real ROMs.
    """
    rom = bytearray(size)  # 0x00 is also the one-byte no-op of the script language
    rom[0xA0:0xA0 + len(header_id)] = header_id.encode("ascii")
    signature = bytes.fromhex("2F1B031134008601010A")
    first_instruction = signature + bytes(28 - len(signature))
    content = (first_instruction + scripts + b"\x06")[:size - SCRIPT_START]
    rom[SCRIPT_START:SCRIPT_START + len(content)] = content
    starts = [SCRIPT_START, SCRIPT_START + len(first_instruction), SCRIPT_START + len(content) - 1]
    table_b = 0x4000 + 2 * len(starts)
    rom[SCRIPT_BANK:SCRIPT_BANK + 4] = (0x4000).to_bytes(2, "little") + table_b.to_bytes(2, "little")
    for number, start in enumerate(starts):
        bank, offset = divmod(start - SCRIPT_BANK, 0x4000)
        entry = SCRIPT_BANK + 0x4000 + 2 * number
        rom[entry:entry + 2] = (offset + 0x4000).to_bytes(2, "little")
        rom[SCRIPT_BANK + table_b + number] = bank
    assert len(rom) == size
    return bytes(rom)


def make_options(**overrides: Any):
    """A fully populated ``MedabotsOptions`` with defaults except for ``overrides`` (given as raw option values)."""
    from ..options import MedabotsOptions
    hints = MedabotsOptions.type_hints
    return MedabotsOptions(**{name: option.from_any(overrides.get(name, option.default))
                              for name, option in hints.items()})
