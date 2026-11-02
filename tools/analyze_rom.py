#!/usr/bin/env python3
"""Analyze a Medabots: Metabee / Rokusho ROM and report what the world's data needs to be verified.

Run it through the developer script so that the world and Archipelago are importable:

    tools/dev.sh run tools/analyze_rom.py path/to/rom.gba
    tools/dev.sh run tools/analyze_rom.py path/to/rom.gba --json report.json --opcode 0x3C

The tool never modifies the ROM and writes nothing but the optional JSON report. What it produces:

* which of the four supported versions the ROM is, and where the documented tables sit;
* every battle record (who fights, with which parts and medal);
* a walk through all event scripts: an opcode histogram, every "give medal" instruction with its script offset (these
  are the reward instructions that become checks), and on request every occurrence of any opcode with its context;
* every event script (by number) that gives an item, part, money, a medal or a Medabot, and the event flags it sets.
  Script n is also map object n and owns event flag n, so these are the candidates for locations;
* whether the memory map's identity-block region is still blank, plus the largest blank runs of the ROM as
  alternatives. See docs/CALIBRATION.md for what to do with the results.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from worlds.medabots_rpg.data_loader import WorldData, get_world_data
from worlds.medabots_rpg.rom_info import RomError, identify_rom
from worlds.medabots_rpg.rom_scripts import (
    ScriptError,
    find_signature,
    iter_instructions,
    iter_script,
    locate_script_bank,
    locate_script_region,
)

GIVE_MEDAL_OPCODE = 0x3C
ROM_BASE = 0x08000000
REWARD_OPCODES = {0x36: "item", 0x38: "part", 0x3A: "money", 0x3C: "medal", 0x3D: "medabot"}
"""Script opcodes that hand the player something; 'neutralize' entries in locations.json name these."""
SET_FLAG_OPCODE = 0x13
MONEY_SCALE = 10
"""Opcode 0x3A adds ten times its operand to the money."""
BLANK = 0x00  # the four ROMs pad their unused space with 0x00
CONTEXT_BYTES = 6


def hex_offset(value: int) -> str:
    return f"0x{value:X}"


def _name(names: tuple[str, ...], index: int, none: str = "(none)") -> str:
    return names[index] if 0 <= index < len(names) else none


def locate_tables(rom: bytes, data: WorldData) -> dict[str, Any]:
    """File offsets of every table that is found by a byte signature."""
    found: dict[str, Any] = {}
    for name, signature in data.rom.signatures.items():
        offset = find_signature(rom, signature)
        found[name] = None if offset is None else hex_offset(offset)
    return found


def decode_battles(rom: bytes, data: WorldData, offset: int) -> list[dict[str, Any]]:
    """Decode the battle table: character, number of bots, and each bot's parts, medal and medal level.

    ``offset`` is a table of 32-bit ROM pointers, one per battle, to the 40-byte records (this is how the battle code
    at 0x08011E84 in Metabee USA reads it).
    """
    layout = data.tables.record_layouts["battle"]
    size, count = layout["size"], layout["count"]
    tables, battles = data.tables, []
    for index in range(count):
        pointer = int.from_bytes(rom[offset + index * 4: offset + index * 4 + 4], "little") - ROM_BASE
        record = rom[pointer: pointer + size] if 0 <= pointer < len(rom) else b""
        if len(record) < size:
            break
        bots = []
        for bot_index in range(min(record[2], 3)):
            raw = record[4 + bot_index * 12: 4 + (bot_index + 1) * 12]
            head, right, left, legs, medal, level = raw[:6]
            bots.append({
                "head": _name(tuple(row[0] for row in tables.parts), head),
                "right_arm": _name(tuple(row[1] for row in tables.parts), right),
                "left_arm": _name(tuple(row[2] for row in tables.parts), left),
                "legs": _name(tuple(row[3] for row in tables.parts), legs),
                "medal": _name(tables.medals, medal),
                "medal_level": level,
            })
        battles.append({"index": index, "character": _name(tables.characters, record[0], "?"), "bots": bots})
    return battles


def analyze_scripts(rom: bytes, data: WorldData, watch_opcodes: tuple[int, ...] = ()) -> dict[str, Any]:
    """Walk the whole script region and collect what is interesting for locating rewards."""
    region = locate_script_region(rom, data.rom)
    histogram: Counter[int] = Counter()
    give_medal: list[dict[str, Any]] = []
    watched: dict[int, list[dict[str, Any]]] = {opcode: [] for opcode in watch_opcodes}
    stopped = None
    count = 0
    try:
        for instruction in iter_instructions(rom, region, data.tables):
            count += 1
            histogram[instruction.opcode] += 1
            absolute = region.start + instruction.offset
            if instruction.opcode == GIVE_MEDAL_OPCODE and instruction.operands:
                give_medal.append({
                    "script_offset": hex_offset(instruction.offset),
                    "medal_id": instruction.operands[0],
                    "medal": _name(data.tables.medals, instruction.operands[0], "?"),
                    "raw": instruction.raw.hex(),
                })
            if instruction.opcode in watched:
                before = rom[max(region.start, absolute - CONTEXT_BYTES):absolute]
                after = rom[absolute + instruction.length: absolute + instruction.length + CONTEXT_BYTES]
                watched[instruction.opcode].append({
                    "script_offset": hex_offset(instruction.offset),
                    "raw": instruction.raw.hex(),
                    "before": before.hex(),
                    "after": after.hex(),
                })
    except ScriptError as exc:
        stopped = str(exc)
    return {
        "region_start": hex_offset(region.start),
        "region_length": hex_offset(region.length),
        "instruction_count": count,
        "stopped_early": stopped,
        "opcode_histogram": {f"0x{op:02X}": n for op, n in sorted(histogram.items())},
        "give_medal": give_medal,
        "watched": {f"0x{op:02X}": hits for op, hits in watched.items()},
    }


def describe_reward(opcode: int, operands: bytes, data: WorldData) -> str:
    tables = data.tables
    kind = REWARD_OPCODES[opcode]
    if kind == "part" and len(operands) >= 2:
        model, slot = operands[0], operands[1]
        part = _name(tuple(row[slot] for row in tables.parts), model, "?") if slot < 4 else "?"
        return f"part {part} ({_name(tables.bots, model, '?')})"
    if kind == "medal":
        return f"medal {_name(tables.medals, operands[0], '?')}"
    if kind == "money":
        return f"money {int.from_bytes(operands[:2], 'big') * MONEY_SCALE}"
    if kind == "item":
        return f"item 0x{operands[0]:02X} x{max(operands[1], 1)}"
    return "medabot"


def reward_scripts(rom: bytes, data: WorldData) -> dict[str, Any]:
    """Every event script that gives something, with the flags it sets (by script number)."""
    try:
        bank = locate_script_bank(rom, data.rom)
    except ScriptError as exc:
        return {"error": str(exc), "scripts": []}
    found, unparsed = [], []
    for number in range(len(bank.starts)):
        rewards, flags = [], []
        try:
            for _, instruction in iter_script(rom, bank, number, data.tables):
                if instruction.opcode in REWARD_OPCODES:
                    rewards.append(describe_reward(instruction.opcode, instruction.operands, data))
                elif instruction.opcode == SET_FLAG_OPCODE:
                    flags.append(int.from_bytes(instruction.operands[:2], "big"))
        except ScriptError:
            unparsed.append(number)
            continue
        if rewards:
            found.append({"script": number, "rewards": rewards, "sets_flags": flags, "sets_own_flag": number in flags})
    return {"bank": hex_offset(bank.base), "count": len(bank.starts), "unparsed": unparsed, "scripts": found}


def blank_runs(rom: bytes, minimum: int = 256, limit: int = 8) -> list[dict[str, str]]:
    """The longest runs of blank (0x00) bytes, longest first: candidates for where the world may store data."""
    runs: list[tuple[int, int]] = []
    start = None
    for index, byte in enumerate(rom):
        if byte == BLANK and start is None:
            start = index
        elif byte != BLANK and start is not None:
            if index - start >= minimum:
                runs.append((index - start, start))
            start = None
    if start is not None and len(rom) - start >= minimum:
        runs.append((len(rom) - start, start))
    runs.sort(reverse=True)
    return [{"offset": hex_offset(offset), "length": hex_offset(length)} for length, offset in runs[:limit]]


def check_identity_block(rom: bytes, data: WorldData) -> dict[str, Any]:
    offset, size = data.memory_map.ap_block_offset, data.memory_map.ap_block_size
    if offset is None or size is None:
        return {"configured": False}
    region = rom[offset:offset + size]
    return {
        "configured": True,
        "offset": hex_offset(offset),
        "size": size,
        "inside_rom": len(region) == size,
        "blank": len(region) == size and all(b == BLANK for b in region),
    }


def analyze(rom: bytes, data: WorldData | None = None, watch_opcodes: tuple[int, ...] = ()) -> dict[str, Any]:
    data = data or get_world_data()
    version = identify_rom(rom, data)
    return {
        "rom": {"label": version.label, "id": version.id, "size": hex_offset(len(rom))},
        "tables": locate_tables(rom, data),
        "identity_block": check_identity_block(rom, data),
        "blank_runs": blank_runs(rom),
        "battles": decode_battles(rom, data, version.battles_offset),
        "scripts": analyze_scripts(rom, data, watch_opcodes),
        "reward_scripts": reward_scripts(rom, data),
    }


def _describe_block(block: dict[str, Any]) -> str:
    if not block["configured"]:
        return "not configured"
    verdict = "blank, usable" if block["blank"] else "NOT blank, choose another"
    return f"{block['offset']} +{block['size']}: {verdict}"


def render_summary(report: dict[str, Any]) -> str:
    scripts, block, rewards = report["scripts"], report["identity_block"], report["reward_scripts"]
    lines = [
        f"ROM: {report['rom']['label']} ({report['rom']['size']} bytes)",
        "",
        "Tables found by signature:",
        *(f"  {name:<16} {offset or 'NOT FOUND'}" for name, offset in report["tables"].items()),
        "",
        f"Battle records: {len(report['battles'])}",
        f"Script region: {scripts['region_start']} +{scripts['region_length']}, "
        f"{scripts['instruction_count']} instructions"
        + (f"  (stopped early: {scripts['stopped_early']})" if scripts["stopped_early"] else ""),
        f"'Give medal' instructions: {len(scripts['give_medal'])}",
        *(f"  script +{m['script_offset']:<8} {m['medal']:<12} ({m['raw']})" for m in scripts["give_medal"]),
        "",
        f"Reward scripts: {len(rewards['scripts'])}"
        + (f" of {rewards['count']} in the bank at {rewards['bank']}" if "bank" in rewards else
           f" (script bank not found: {rewards['error']})"),
        *(f"  script {r['script']:<5} {'sets own flag' if r['sets_own_flag'] else '             '} "
          f"{'; '.join(r['rewards'])}" for r in rewards["scripts"]),
        "",
        "Identity block (memory_map.json ap_block): " + _describe_block(block),
        "Largest blank ROM runs (alternatives):",
        *(f"  {run['offset']} +{run['length']}" for run in report["blank_runs"]),
    ]
    for opcode, hits in scripts["watched"].items():
        lines += ["", f"Opcode {opcode}: {len(hits)} occurrences"]
        lines += [f"  script +{h['script_offset']:<8} {h['before']} [{h['raw']}] {h['after']}" for h in hits]
    return "\n".join(lines)


def parse_opcode(text: str) -> int:
    value = int(text, 0)
    if not 0 <= value <= 0xFF:
        raise argparse.ArgumentTypeError("opcodes are bytes between 0x00 and 0xFF")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rom", type=Path, help="your own Medabots: Metabee or Rokusho ROM (never modified)")
    parser.add_argument("--json", type=Path, metavar="FILE", help="also write the full report as JSON")
    parser.add_argument("--opcode", type=parse_opcode, action="append", default=[], metavar="0xNN",
                        help="list every occurrence of this script opcode with surrounding bytes (repeatable)")
    args = parser.parse_args(argv)

    try:
        report = analyze(args.rom.read_bytes(), watch_opcodes=tuple(args.opcode))
    except (OSError, RomError, ScriptError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(render_summary(report))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nFull report written to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
