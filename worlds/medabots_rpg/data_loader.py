"""Loading and validation of the JSON game data.

All game knowledge (items, locations, areas, ROM tables, memory addresses) lives in ``data/*.json``. This module is the
only place that reads those files. It turns them into immutable, typed objects and refuses to continue when the data is
inconsistent, so a typo in a JSON file fails loudly at import time instead of producing a broken seed.

Updating the world for new findings therefore means editing JSON, not Python.
"""
from __future__ import annotations

import hashlib
import json
import pkgutil
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import cached_property, lru_cache
from typing import Any, Protocol

from .constants import (
    GROUP_MEDALS,
    GROUP_MONEY,
    GROUP_PARTS,
    GROUP_TRAPS,
    KIND_CONSUMABLE,
    KIND_MEDAL,
    KIND_PART,
    KIND_TRAP,
    PART_SLOT_GROUPS,
    PART_SLOTS,
    STATUS_CANDIDATE,
    STATUS_VERIFIED,
)

DATA_FILES = ("game_tables", "rom_versions", "items", "locations", "regions", "rules", "memory_map")


class DataError(ValueError):
    """Raised when the bundled game data is missing or inconsistent."""


# ---------------------------------------------------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------------------------------------------------
class DataSource(Protocol):
    def read(self, name: str) -> bytes:
        """Return the raw JSON bytes of data file ``name`` (without extension)."""


class PackageDataSource:
    """Reads the data files that ship inside the APWorld (works for folders and ``.apworld`` archives)."""

    def read(self, name: str) -> bytes:
        raw = pkgutil.get_data(__package__, f"data/{name}.json")
        if raw is None:
            raise DataError(f"Missing data file: data/{name}.json")
        return raw


class DictDataSource:
    """In-memory data source, used by tests to feed alternative data sets."""

    def __init__(self, files: Mapping[str, Any]):
        self._files = files

    def read(self, name: str) -> bytes:
        return json.dumps(self._files[name]).encode("utf-8")


# ---------------------------------------------------------------------------------------------------------------------
# Typed data
# ---------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class RomVersion:
    id: str
    label: str
    version: str  # "metabee" or "rokusho"
    region: str  # "us" or "eu"
    header_id: str
    battles_offset: int
    starter_offset: int
    text_offset: int


@dataclass(frozen=True)
class Signature:
    """A byte pattern that locates a table inside the ROM."""

    pattern: bytes
    target_adjust: int = 0
    region_length: int | None = None


@dataclass(frozen=True)
class RomInfo:
    header_offset: int
    header_length: int
    versions: tuple[RomVersion, ...]
    unsupported_prefixes: Mapping[str, str]
    signatures: Mapping[str, Signature]

    def identify(self, header: bytes) -> RomVersion | None:
        """Match the ROM header bytes against the supported versions."""
        text = header.decode("ascii", errors="replace")
        return next((v for v in self.versions if v.header_id == text), None)

    def unsupported_reason(self, header: bytes) -> str | None:
        """Explain why a recognisable but unsupported ROM cannot be used (``None`` if it is simply unknown)."""
        text = header.decode("ascii", errors="replace")
        return next((why for prefix, why in self.unsupported_prefixes.items() if text.startswith(prefix)), None)


@dataclass(frozen=True)
class GameTables:
    """Documented ROM tables. Every list is indexed by the in-game ID."""

    no_part_id: int
    variable_length_opcode: int
    opcode_lengths: tuple[int, ...]
    medals: tuple[str, ...]
    bots: tuple[str, ...]
    parts: tuple[tuple[str, ...], ...]
    maps: tuple[str, ...]
    characters: tuple[str, ...]
    record_layouts: Mapping[str, Any]


@dataclass(frozen=True)
class Area:
    name: str
    parent: str | None
    map_prefixes: tuple[str, ...]
    index: int  # position in the provisional story order

    @property
    def clear_event(self) -> str:
        """Name of the AP event item granted once this area has been completed."""
        return f"{self.name} Cleared"

    def owns_map(self, map_name: str) -> bool:
        return any(map_name.startswith(prefix) for prefix in self.map_prefixes)


@dataclass(frozen=True)
class LocationDef:
    id: int
    name: str
    map_name: str
    area: str
    category: str
    status: str
    missable: bool = False
    requires: Any = None
    detect: Mapping[str, Any] | None = None

    @property
    def verified(self) -> bool:
        return self.status == STATUS_VERIFIED


@dataclass(frozen=True)
class ItemDef:
    id: int
    name: str
    kind: str
    groups: tuple[str, ...]
    data: Mapping[str, Any] = field(default_factory=dict)
    """Kind specific payload: part -> model/slot/bot, medal -> medal_id, consumable -> effect, trap -> trap key."""

    @property
    def version_exclusive(self) -> str | None:
        return self.data.get("version_exclusive")


@dataclass(frozen=True)
class TableRef:
    """Location and shape of a table in game memory."""

    address: int
    kind: str  # "bitfield", "bytes", "u8", "u16" or "u32"
    size: int
    values: tuple[int, ...] | None = None
    """For state flags: the byte values that mean "yes" (for example the values of an 'overworld, idle' state)."""


@dataclass(frozen=True)
class MemoryMap:
    verified: bool
    domain: str
    ap_block_offset: int | None
    ap_block_size: int | None
    tables: Mapping[str, TableRef | None]
    state: Mapping[str, TableRef | None]
    optional_tables: Mapping[str, TableRef | None]
    """Tables that only some features (traps) need. They may stay unknown even in a verified map."""

    def resolve(self, path: str) -> TableRef | None:
        """Look up an entry by its dotted path, e.g. ``tables.money`` or ``state.in_battle``."""
        section, _, name = path.partition(".")
        sections = {"tables": self.tables, "state": self.state, "optional_tables": self.optional_tables}
        if section not in sections or name not in sections[section]:
            raise DataError(f"Unknown memory map entry {path!r}")
        return sections[section][name]

    def has(self, *paths: str) -> bool:
        """True when every named entry is known."""
        return all(self.resolve(path) is not None for path in paths)

    @property
    def missing(self) -> list[str]:
        """Dotted paths of every *required* table or state entry that is still unknown."""
        return [f"tables.{k}" for k, v in self.tables.items() if v is None] + [
            f"state.{k}" for k, v in self.state.items() if v is None
        ]


@dataclass(frozen=True)
class WorldData:
    tables: GameTables
    rom: RomInfo
    areas: tuple[Area, ...]
    goal_event: str
    goal_detect: Mapping[str, Any] | None
    locations: tuple[LocationDef, ...]
    items: tuple[ItemDef, ...]
    memory_map: MemoryMap
    rules: Mapping[str, Any]
    pool_exclusions: Mapping[str, tuple[str, ...]]
    content_hash: str
    """SHA-256 over all data files. Stored in slot data so a client can detect a generator/client data mismatch."""

    @cached_property
    def item_by_name(self) -> Mapping[str, ItemDef]:
        return {item.name: item for item in self.items}

    @cached_property
    def location_by_name(self) -> Mapping[str, LocationDef]:
        return {loc.name: loc for loc in self.locations}

    @cached_property
    def area_by_name(self) -> Mapping[str, Area]:
        return {area.name: area for area in self.areas}

    def area_of_map(self, map_name: str) -> Area | None:
        return next((area for area in self.areas if area.owns_map(map_name)), None)

    @property
    def is_verified(self) -> bool:
        """True when the memory map and every location are confirmed against a real ROM."""
        return self.memory_map.verified and all(loc.verified for loc in self.locations)


def part_item_name(tables: GameTables, model: int, slot: int) -> str:
    """Canonical item name of a medapart, e.g. ``Head: Psycho Missile (Noctobat)``."""
    return f"{PART_SLOTS[slot]}: {tables.parts[model][slot]} ({tables.bots[model]})"


def medal_item_name(tables: GameTables, medal_id: int) -> str:
    return f"Medal: {tables.medals[medal_id]}"


# ---------------------------------------------------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------------------------------------------------
def _int(value: Any, what: str) -> int:
    try:
        return int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError) as exc:
        raise DataError(f"{what}: expected an integer or hex string, got {value!r}") from exc


def _parse_tables(raw: Mapping[str, Any]) -> GameTables:
    return GameTables(
        no_part_id=raw["no_part_id"],
        variable_length_opcode=raw["variable_length_opcode"],
        opcode_lengths=tuple(raw["script_opcode_lengths"]),
        medals=tuple(raw["medals"]),
        bots=tuple(raw["bots"]),
        parts=tuple(tuple(row) for row in raw["parts"]),
        maps=tuple(raw["maps"]),
        characters=tuple(raw["characters"]),
        record_layouts=raw["record_layouts"],
    )


def _parse_rom(raw: Mapping[str, Any]) -> RomInfo:
    versions = tuple(
        RomVersion(
            id=v["id"],
            label=v["label"],
            version=v["version"],
            region=v["region"],
            header_id=v["header_id"],
            battles_offset=_int(v["battles_offset"], f"{v['id']}.battles_offset"),
            starter_offset=_int(v["starter_offset"], f"{v['id']}.starter_offset"),
            text_offset=_int(v["text_offset"], f"{v['id']}.text_offset"),
        )
        for v in raw["versions"]
    )
    signatures = {
        name: Signature(
            pattern=bytes.fromhex(sig["bytes"]),
            target_adjust=sig.get("target_adjust", 0),
            region_length=_int(sig["region_length"], f"{name}.region_length") if "region_length" in sig else None,
        )
        for name, sig in raw["signatures"].items()
        if isinstance(sig, dict)
    }
    return RomInfo(
        header_offset=_int(raw["header_offset"], "header_offset"),
        header_length=raw["header_length"],
        versions=versions,
        unsupported_prefixes=dict(raw["unsupported_header_prefixes"]),
        signatures=signatures,
    )


def _parse_areas(raw: Mapping[str, Any]) -> tuple[Area, ...]:
    return tuple(
        Area(name=a["name"], parent=a.get("from"), map_prefixes=tuple(a["map_prefixes"]), index=i)
        for i, a in enumerate(raw["areas"])
    )


def _parse_table_ref(entry: Mapping[str, Any] | None, what: str) -> TableRef | None:
    if entry is None:
        return None
    values = tuple(entry["values"]) if "values" in entry else None
    return TableRef(address=_int(entry["address"], f"{what}.address"), kind=entry["kind"], size=entry["size"],
                    values=values)


def _parse_memory_map(raw: Mapping[str, Any]) -> MemoryMap:
    ap_block = raw.get("ap_block")
    return MemoryMap(
        verified=bool(raw["verified"]),
        domain=raw["bizhawk_domain"],
        ap_block_offset=_int(ap_block["rom_offset"], "ap_block.rom_offset") if ap_block else None,
        ap_block_size=ap_block["size"] if ap_block else None,
        tables={k: _parse_table_ref(v, f"tables.{k}") for k, v in raw["tables"].items()},
        state={k: _parse_table_ref(v, f"state.{k}") for k, v in raw["state"].items()},
        optional_tables={k: _parse_table_ref(v, f"optional_tables.{k}")
                         for k, v in raw["optional_tables"].items()},
    )


def _version_exclusives(tables: GameTables, raw: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Map bot name -> version and medal name -> version, checking that every name exists in the tables."""
    bots: dict[str, str] = {}
    medals: dict[str, str] = {}
    for version, entry in raw.items():
        if version.startswith("_"):
            continue
        for bot in entry["bots"]:
            if bot not in tables.bots:
                raise DataError(f"version_exclusive[{version}] references unknown bot {bot!r}")
            bots[bot] = version
        for medal in entry["medals"]:
            if medal not in tables.medals:
                raise DataError(f"version_exclusive[{version}] references unknown medal {medal!r}")
            medals[medal] = version
    return bots, medals


def _build_items(tables: GameTables, raw: Mapping[str, Any]) -> tuple[ItemDef, ...]:
    bases = raw["id_bases"]
    exclusive_bots, exclusive_medals = _version_exclusives(tables, raw["version_exclusive"])
    items: list[ItemDef] = []

    for model, bot in enumerate(tables.bots):
        for slot in range(len(PART_SLOTS)):
            data: dict[str, Any] = {"model": model, "slot": slot, "bot": bot}
            if bot in exclusive_bots:
                data["version_exclusive"] = exclusive_bots[bot]
            items.append(ItemDef(
                id=bases["part"] + model * len(PART_SLOTS) + slot,
                name=part_item_name(tables, model, slot),
                kind=KIND_PART,
                groups=(GROUP_PARTS, PART_SLOT_GROUPS[slot], bot),
                data=data,
            ))
    for medal_id, medal in enumerate(tables.medals):
        data = {"medal_id": medal_id}
        if medal in exclusive_medals:
            data["version_exclusive"] = exclusive_medals[medal]
        items.append(ItemDef(bases["medal"] + medal_id, medal_item_name(tables, medal_id), KIND_MEDAL,
                             (GROUP_MEDALS,), data))
    for entry in raw["consumables"]:
        items.append(ItemDef(entry["id"], entry["name"], KIND_CONSUMABLE, (GROUP_MONEY,),
                             {"effect": entry["effect"], "weight": entry["weight"]}))
    for entry in raw["traps"]:
        items.append(ItemDef(entry["id"], entry["name"], KIND_TRAP, (GROUP_TRAPS,),
                             {"trap": entry["trap"], "requires": tuple(entry.get("requires", ()))}))
    return tuple(items)


def _build_locations(areas: tuple[Area, ...], raw: Mapping[str, Any]) -> tuple[LocationDef, ...]:
    result = []
    for entry in raw["locations"]:
        area = next((a for a in areas if a.owns_map(entry["map"])), None)
        if area is None:
            raise DataError(f"Location {entry['name']!r}: map {entry['map']!r} belongs to no area")
        result.append(LocationDef(
            id=entry["id"],
            name=entry["name"],
            map_name=entry["map"],
            area=area.name,
            category=entry["category"],
            status=entry.get("status", STATUS_CANDIDATE),
            missable=entry.get("missable", False),
            requires=entry.get("requires"),
            detect=entry.get("detect"),
        ))
    return tuple(result)


# ---------------------------------------------------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------------------------------------------------
def rule_problems(expr: Any, known_names: set[str], known_groups: set[str], where: str) -> list[str]:
    """Check a JSON rule expression.

    Supported forms: ``null`` (always true), ``"Item"``, ``{"has": "Item", "count": n}``,
    ``{"group": "Group", "count": n}``, ``{"all": [...]}`` and ``{"any": [...]}``.
    """
    if expr is None:
        return []
    if isinstance(expr, str):
        return [] if expr in known_names else [f"{where}: unknown item or event {expr!r}"]
    if not isinstance(expr, dict) or len(expr.keys() - {"count"}) != 1:
        return [f"{where}: malformed rule expression {expr!r}"]
    (key,) = expr.keys() - {"count"}
    if key in ("all", "any"):
        if not isinstance(expr[key], list):
            return [f"{where}: {key!r} needs a list"]
        return [p for child in expr[key] for p in rule_problems(child, known_names, known_groups, where)]
    if key == "has":
        return [] if expr["has"] in known_names else [f"{where}: unknown item or event {expr['has']!r}"]
    if key == "group":
        return [] if expr["group"] in known_groups else [f"{where}: unknown item group {expr['group']!r}"]
    return [f"{where}: unknown rule keyword {key!r}"]


def _duplicates(values: Iterable[Any]) -> list[Any]:
    return sorted((value for value, count in Counter(values).items() if count > 1), key=str)


def validate(data: WorldData, location_categories: Iterable[str]) -> list[str]:
    """Return a list of human readable problems (empty when the data is consistent)."""
    problems: list[str] = []
    tables = data.tables

    # Tables
    if len(tables.parts) != len(tables.bots):
        problems.append(f"parts has {len(tables.parts)} rows but bots has {len(tables.bots)} entries")
    if any(len(row) != len(PART_SLOTS) for row in tables.parts):
        problems.append(f"every parts row must have exactly {len(PART_SLOTS)} columns")
    if not 0 <= tables.variable_length_opcode < len(tables.opcode_lengths):
        problems.append("variable_length_opcode is outside the opcode length table")
    if any(length < 1 for length in tables.opcode_lengths):
        problems.append("script_opcode_lengths contains a length below 1")
    problems += [f"duplicate bot name {name!r}" for name in _duplicates(tables.bots)]

    # ROM versions
    for version in data.rom.versions:
        if len(version.header_id) != data.rom.header_length:
            problems.append(f"{version.id}: header_id must be {data.rom.header_length} characters")
    problems += [f"duplicate ROM header id {dup!r}" for dup in _duplicates(v.header_id for v in data.rom.versions)]
    problems += [f"duplicate ROM version id {dup!r}" for dup in _duplicates(v.id for v in data.rom.versions)]

    # Areas: unique names, known parents declared earlier, a single root, every map owned exactly once
    names = [area.name for area in data.areas]
    problems += [f"duplicate area {dup!r}" for dup in _duplicates(names)]
    roots = [area.name for area in data.areas if area.parent is None]
    if len(roots) != 1:
        problems.append(f"expected exactly one start area, found {roots}")
    for area in data.areas:
        if area.parent is None:
            continue
        if area.parent not in names:
            problems.append(f"area {area.name!r} has unknown parent {area.parent!r}")
        elif names.index(area.parent) >= area.index:
            problems.append(f"area {area.name!r} must be listed after its parent {area.parent!r}")
    for map_name in tables.maps:
        owners = [area.name for area in data.areas if area.owns_map(map_name)]
        if len(owners) != 1:
            problems.append(f"map {map_name!r} is owned by {len(owners)} areas ({owners}); expected exactly 1")
    if not data.goal_event:
        problems.append("regions.json must define goal_event")

    # Items
    problems += [f"duplicate item id {dup}" for dup in _duplicates(item.id for item in data.items)]
    problems += [f"duplicate item name {dup!r}" for dup in _duplicates(item.name for item in data.items)]
    for group, excluded in data.pool_exclusions.items():
        known = tables.medals if group == "medals" else tables.bots
        problems += [f"pool_exclusions[{group}] references unknown name {name!r}"
                     for name in excluded if name not in known]

    # Locations
    categories = set(location_categories)
    problems += [f"duplicate location id {dup}" for dup in _duplicates(loc.id for loc in data.locations)]
    problems += [f"duplicate location name {dup!r}" for dup in _duplicates(loc.name for loc in data.locations)]
    for loc in data.locations:
        if loc.map_name not in tables.maps:
            problems.append(f"location {loc.name!r} references unknown map {loc.map_name!r}")
        if loc.category not in categories:
            problems.append(f"location {loc.name!r} has unknown category {loc.category!r}")
        if loc.status not in (STATUS_CANDIDATE, STATUS_VERIFIED):
            problems.append(f"location {loc.name!r} has unknown status {loc.status!r}")
        if loc.verified and not loc.detect:
            problems.append(f"location {loc.name!r} is verified but has no 'detect' entry")

    names_for_rules = {item.name for item in data.items} | {area.clear_event for area in data.areas}
    names_for_rules.add(data.goal_event)
    groups_for_rules = {group for item in data.items for group in item.groups}
    for loc in data.locations:
        problems += rule_problems(loc.requires, names_for_rules, groups_for_rules, f"location {loc.name!r}")

    # Traps must only require memory entries that exist in the memory map schema
    for item in data.items:
        for path in item.data.get("requires", ()) if item.kind == KIND_TRAP else ():
            try:
                data.memory_map.resolve(path)
            except DataError:
                problems.append(f"trap {item.name!r} requires unknown memory map entry {path!r}")

    # Memory map
    if data.memory_map.verified and data.memory_map.missing:
        problems.append(f"memory map is marked verified but is missing {data.memory_map.missing}")
    return problems


# ---------------------------------------------------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------------------------------------------------
def load_world_data(source: DataSource | None = None) -> WorldData:
    """Read, assemble and validate all game data. Raises DataError describing every problem found."""
    source = source or PackageDataSource()
    raw_bytes = {name: source.read(name) for name in DATA_FILES}
    try:
        raw = {name: json.loads(blob) for name, blob in raw_bytes.items()}
    except json.JSONDecodeError as exc:
        raise DataError(f"Invalid JSON in a data file: {exc}") from exc

    tables = _parse_tables(raw["game_tables"])
    areas = _parse_areas(raw["regions"])
    exclusions = raw["items"].get("pool_exclusions", {})
    data = WorldData(
        tables=tables,
        rom=_parse_rom(raw["rom_versions"]),
        areas=areas,
        goal_event=raw["regions"]["goal_event"],
        goal_detect=raw["regions"].get("goal_detect"),
        locations=_build_locations(areas, raw["locations"]),
        items=_build_items(tables, raw["items"]),
        memory_map=_parse_memory_map(raw["memory_map"]),
        rules=raw["rules"],
        pool_exclusions={"medals": tuple(exclusions.get("medals", ())), "bots": tuple(exclusions.get("bots", ()))},
        content_hash=hashlib.sha256(b"".join(raw_bytes[name] for name in DATA_FILES)).hexdigest(),
    )
    problems = validate(data, raw["locations"]["categories"])
    if problems:
        raise DataError("Medabots RPG game data is inconsistent:\n  - " + "\n  - ".join(problems))
    return data


@lru_cache(maxsize=1)
def get_world_data() -> WorldData:
    """The data bundled with this APWorld, loaded once."""
    return load_world_data()
