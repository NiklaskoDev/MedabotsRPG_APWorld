"""Test helpers: a synthetic verified data set, a synthetic ROM and a fake BizHawk memory.

The shipped data is (honestly) unverified, so everything that needs a "verified" world, such as delivering items or
patching, is tested against data built here. The synthetic memory map is an invented but self-consistent layout.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from ..data_loader import DATA_FILES, DictDataSource, PackageDataSource, WorldData, load_world_data

SYSTEM_BUS = "System Bus"
RAM_BASE = 0x02000000
SCRIPT_START = 0x100000
ROM_SIZE = 0x800000
SCRIPT_REGION_LENGTH = 0x18000

# Synthetic memory layout
FLAGS = RAM_BASE + 0x000
PARTS = RAM_BASE + 0x100
MEDALS = RAM_BASE + 0x200
MONEY = RAM_BASE + 0x300
SAFE = RAM_BASE + 0x400
IN_BATTLE = RAM_BASE + 0x401
ARMOR_SCALE = RAM_BASE + 0x410
MEDAL_DISABLE = RAM_BASE + 0x411
FORCE_ENCOUNTER = RAM_BASE + 0x412

FLAG_BIT_SQUIDGUTS = 5
FLAG_BIT_MEDAL_ROOM = 9
FLAG_BIT_STORY_COMPLETE = 100


def raw_data() -> dict[str, Any]:
    """The shipped JSON files as plain dictionaries (deep copies, safe to modify)."""
    source = PackageDataSource()
    return {name: json.loads(source.read(name)) for name in DATA_FILES}


def verified_data(parts_layout: str = "model_major", with_optional: bool = True) -> WorldData:
    """The shipped data with a complete, invented memory map and verified locations.

    ``with_optional=False`` leaves the trap-only tables unknown, as a real calibration might.
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
        },
        optional_tables={
            "battle_armor_scale": ref(ARMOR_SCALE, "u8", 1) if with_optional else None,
            "battle_medal_disable": ref(MEDAL_DISABLE, "u8", 1) if with_optional else None,
            "force_encounter": ref(FORCE_ENCOUNTER, "u8", 1) if with_optional else None,
        },
    )
    raw["regions"]["goal_detect"] = {"type": "flag", "table": "game_flags", "bit": FLAG_BIT_STORY_COMPLETE}
    for entry in raw["locations"]["locations"]:
        entry["status"] = "verified"
        entry["detect"] = {"type": "flag", "table": "game_flags", "bit": entry["id"] % 50 + 20}
    by_id = {entry["id"]: entry for entry in raw["locations"]["locations"]}
    by_id[20003]["detect"]["bit"] = FLAG_BIT_SQUIDGUTS
    by_id[20001]["detect"]["bit"] = FLAG_BIT_MEDAL_ROOM
    return load_world_data(DictDataSource(raw))


class FakeMemory:
    """A tiny GBA memory: a RAM window at 0x02000000 plus a ROM image, addressed like BizHawk's domains."""

    def __init__(self, rom: bytes = b""):
        self.ram = bytearray(0x1000)
        self.rom = bytearray(rom)
        self.writes: list[tuple[int, bytes]] = []
        self.fail_next_guard = False

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
    """A blank (0xFF) ROM image with a valid header and an event-script region.

    The region starts with the documented signature, which is itself a 28-byte multi-way-jump instruction, followed
    by ``scripts`` and then one-byte no-ops up to the documented region length, so the whole region parses.
    """
    rom = bytearray(b"\xFF" * size)
    rom[0xA0:0xA0 + len(header_id)] = header_id.encode("ascii")
    region_end = min(size, SCRIPT_START + SCRIPT_REGION_LENGTH)
    rom[SCRIPT_START:region_end] = bytes(region_end - SCRIPT_START)  # 0x00 = one-byte no-op
    signature = bytes.fromhex("2F1B031134008601010A")
    first_instruction = signature + bytes(28 - len(signature))
    content = (first_instruction + scripts)[:size - SCRIPT_START]
    rom[SCRIPT_START:SCRIPT_START + len(content)] = content
    assert len(rom) == size
    return bytes(rom)


def make_options(**overrides: Any):
    """A fully populated ``MedabotsOptions`` with defaults except for ``overrides`` (given as raw option values)."""
    from ..options import MedabotsOptions
    hints = MedabotsOptions.type_hints
    return MedabotsOptions(**{name: option.from_any(overrides.get(name, option.default))
                              for name, option in hints.items()})
