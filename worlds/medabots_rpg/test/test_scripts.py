import unittest

from ..data_loader import get_world_data
from ..rom_scripts import (
    ScriptError,
    ScriptRegion,
    find_signature,
    instruction_length,
    iter_instructions,
    locate_script_region,
)
from .support import SCRIPT_START, build_rom

DATA = get_world_data()


class TestScriptParser(unittest.TestCase):
    def test_region_is_found_by_signature(self):
        region = locate_script_region(build_rom(), DATA.rom)
        self.assertEqual(region, ScriptRegion(SCRIPT_START, 0x18000))

    def test_missing_signature(self):
        with self.assertRaises(ScriptError):
            locate_script_region(bytes(0x1000), DATA.rom)

    def test_region_is_clipped_to_the_file(self):
        rom = build_rom(size=SCRIPT_START + 0x100)
        self.assertEqual(locate_script_region(rom, DATA.rom).length, 0x100)

    def test_signature_target_adjust(self):
        rom = bytearray(64)
        rom[10:19] = bytes.fromhex("010200565D01621701")
        self.assertEqual(find_signature(bytes(rom), DATA.rom.signatures["starter_medal"]), 9)

    def test_instructions_are_walked_in_order(self):
        # give medal 15 (2 bytes), one-byte no-op, give medal 16
        rom = build_rom(scripts=bytes([0x3C, 0x0F, 0x00, 0x3C, 0x10]))
        region = locate_script_region(rom, DATA.rom)
        found = [(i.offset, i.opcode, i.operands) for i in iter_instructions(rom, region, DATA.tables)][:4]
        self.assertEqual(found, [(0, 0x2F, rom[SCRIPT_START + 1:SCRIPT_START + 28]), (28, 0x3C, b"\x0F"),
                                 (30, 0x00, b""), (31, 0x3C, b"\x10")])

    def test_variable_length_opcode_uses_its_length_byte(self):
        rom = build_rom()
        self.assertEqual(instruction_length(rom, SCRIPT_START, DATA.tables), 0x1B + 1)

    def test_unknown_opcode_is_reported_with_its_offset(self):
        rom = build_rom(scripts=bytes([0xEE]))
        region = locate_script_region(rom, DATA.rom)
        with self.assertRaisesRegex(ScriptError, "0xEE"):
            list(iter_instructions(rom, region, DATA.tables))

    def test_instruction_running_past_the_file_is_reported(self):
        rom = build_rom(scripts=bytes(0x17FD0 - 28) + bytes([0x3C]), size=SCRIPT_START + 0x17FD0 + 1)
        region = locate_script_region(rom, DATA.rom)
        with self.assertRaises(ScriptError):
            list(iter_instructions(rom, region, DATA.tables))

    def test_every_opcode_has_a_usable_length(self):
        for opcode, length in enumerate(DATA.tables.opcode_lengths):
            self.assertGreaterEqual(length, 1, f"opcode 0x{opcode:02X}")
