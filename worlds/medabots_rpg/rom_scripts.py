"""Event-script bytecode: locating the script region in a ROM and walking its instructions.

The game stores all event scripts back to back in one region. Every instruction starts with an opcode byte whose total
length comes from a documented table, except one multi-way jump opcode whose second byte gives the length. Sweeping the
region from its start therefore visits every instruction. This module has no Archipelago imports so the analysis tool
can use it on its own.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from .data_loader import GameTables, RomInfo, Signature

SCRIPT_SIGNATURE = "event_scripts"


class ScriptError(ValueError):
    """Raised when the script region cannot be found or contains bytes that do not parse."""


@dataclass(frozen=True)
class Instruction:
    offset: int
    """Offset of the instruction relative to the start of the script region."""
    opcode: int
    operands: bytes

    @property
    def length(self) -> int:
        return 1 + len(self.operands)

    @property
    def raw(self) -> bytes:
        return bytes([self.opcode]) + self.operands


@dataclass(frozen=True)
class ScriptRegion:
    start: int
    """File offset of the first script byte."""
    length: int


def find_signature(rom: bytes, signature: Signature) -> int | None:
    """File offset the signature points at (first match, plus its adjustment), or ``None`` if it is absent."""
    index = rom.find(signature.pattern)
    return None if index < 0 else index + signature.target_adjust


def locate_script_region(rom: bytes, info: RomInfo) -> ScriptRegion:
    """Find the script region of a ROM by its signature."""
    signature = info.signatures[SCRIPT_SIGNATURE]
    start = find_signature(rom, signature)
    if start is None:
        raise ScriptError("The event-script region was not found. This does not look like a supported Medabots ROM.")
    length = min(signature.region_length or len(rom) - start, len(rom) - start)
    return ScriptRegion(start, length)


def instruction_length(rom: bytes, position: int, tables: GameTables) -> int:
    """Total length in bytes of the instruction at ``position``."""
    opcode = rom[position]
    if opcode >= len(tables.opcode_lengths):
        raise ScriptError(f"Unknown opcode 0x{opcode:02X} at ROM offset 0x{position:X}")
    if opcode == tables.variable_length_opcode:
        if position + 1 >= len(rom):
            raise ScriptError(f"Truncated instruction at ROM offset 0x{position:X}")
        return rom[position + 1] + 1
    return tables.opcode_lengths[opcode]


def iter_instructions(rom: bytes, region: ScriptRegion, tables: GameTables) -> Iterator[Instruction]:
    """Walk every instruction of the region in order."""
    position, end = region.start, region.start + region.length
    while position < end:
        length = instruction_length(rom, position, tables)
        if position + length > len(rom):
            raise ScriptError(f"Instruction at ROM offset 0x{position:X} runs past the end of the file")
        yield Instruction(position - region.start, rom[position], bytes(rom[position + 1:position + length]))
        position += length
