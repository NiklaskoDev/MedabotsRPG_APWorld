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


# ---------------------------------------------------------------------------------------------------------------------
# The script bank: scripts by number
# ---------------------------------------------------------------------------------------------------------------------
BANK_HEADER_MAGIC = 0x4000
"""The game reads its index tables relative to bank + 0x4000, so the first header word is always 0x4000."""


@dataclass(frozen=True)
class ScriptBank:
    """The game's own index of event scripts: script ``n`` starts at ``starts[n]`` (a file offset).

    Script numbers are the same in all four ROM versions, even where a script's position in the ROM differs.
    """

    base: int
    starts: tuple[int, ...]

    def span(self, number: int) -> tuple[int, int]:
        """File offsets ``(start, end)`` of a script; it ends where the next script in the ROM begins."""
        if not 0 <= number < len(self.starts):
            raise ScriptError(f"There is no event script number {number}.")
        start = self.starts[number]
        later = [s for s in self.starts if s > start]
        return start, min(later) if later else start


def locate_script_bank(rom: bytes, info: RomInfo) -> ScriptBank:
    """Read the script index the game uses (header ``0x4000, table B``; table A at +0x4000 holds 16-bit offsets,
    table B one 16 KiB bank number per script; script n starts at ``base + A[n] - 0x4000 + (B[n] << 14)``)."""
    signature = info.signatures[SCRIPT_SIGNATURE]
    match = find_signature(rom, signature)
    if match is None or signature.bank_offset is None:
        raise ScriptError("The event-script bank was not found. This does not look like a supported Medabots ROM.")
    base = match + signature.bank_offset
    if base < 0 or base + 4 > len(rom) or int.from_bytes(rom[base:base + 2], "little") != BANK_HEADER_MAGIC:
        raise ScriptError("The event-script bank header is not where it was expected.")
    table_b = int.from_bytes(rom[base + 2:base + 4], "little")
    count = (table_b - BANK_HEADER_MAGIC) // 2
    if count <= 0 or base + table_b + count > len(rom):
        raise ScriptError("The event-script bank header is malformed.")
    starts = tuple(
        base + int.from_bytes(rom[base + BANK_HEADER_MAGIC + 2 * n:base + BANK_HEADER_MAGIC + 2 * n + 2], "little")
        - BANK_HEADER_MAGIC + (rom[base + table_b + n] << 14)
        for n in range(count)
    )
    return ScriptBank(base, starts)


def iter_script(rom: bytes, bank: ScriptBank, number: int, tables: GameTables) -> Iterator[tuple[int, Instruction]]:
    """Walk one script, yielding ``(file offset, instruction)`` pairs."""
    position, end = bank.span(number)
    while position < end:
        length = instruction_length(rom, position, tables)
        if position + length > end:
            raise ScriptError(f"Script {number} does not parse (instruction at ROM offset 0x{position:X})")
        yield position, Instruction(position - bank.starts[number], rom[position],
                                    bytes(rom[position + 1:position + length]))
        position += length
