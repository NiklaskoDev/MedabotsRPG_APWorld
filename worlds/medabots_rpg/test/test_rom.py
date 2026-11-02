"""ROM identification, the seed identity block and the patch container (with all of its refusals)."""
import dataclasses
import os
import tempfile
import unittest
from unittest import mock

from .. import rom as rom_module
from ..data_loader import get_world_data
from ..rom import ApIdentity, MedabotsRPGProcedurePatch, collect_rewrites, write_patch
from ..rom_info import RomError, identify_header, identify_rom
from .support import SCRIPT_START, TEST_SCRIPT, build_rom, verified_data

SHIPPED = get_world_data()
VERIFIED = verified_data()
BLOCK = VERIFIED.memory_map.ap_block_offset
BLOCK_SIZE = VERIFIED.memory_map.ap_block_size


def apply_patch(rom: bytes, *, build_data=VERIFIED, installed_data=VERIFIED, allow_unverified=False,
                locations=()) -> bytes:
    """Build a patch for ``build_data``, then apply it to ``rom`` as if ``installed_data`` were installed."""
    patch = MedabotsRPGProcedurePatch(player=1, player_name="Ash")
    write_patch(patch, data=build_data, seed_name="seed-1", slot=1, player_name="Ash",
                allow_unverified=allow_unverified, locations=list(locations))
    with tempfile.TemporaryDirectory() as folder:
        patch_path, output_path = os.path.join(folder, "p.apmedabots"), os.path.join(folder, "out.gba")
        patch.write(patch_path)
        reader = MedabotsRPGProcedurePatch(patch_path)
        with mock.patch.object(MedabotsRPGProcedurePatch, "get_source_data_with_cache", classmethod(lambda cls: rom)), \
                mock.patch.object(rom_module, "get_world_data", return_value=installed_data):
            reader.patch(output_path)
        with open(output_path, "rb") as result:
            return result.read()


class TestIdentification(unittest.TestCase):
    def test_all_four_versions_are_recognised(self):
        for version in SHIPPED.rom.versions:
            rom = build_rom(version.header_id)
            self.assertEqual(identify_rom(rom, SHIPPED), version)

    def test_japanese_rom_gets_a_specific_message(self):
        with self.assertRaisesRegex(RomError, "Japanese"):
            identify_header(b"MEDACOREKBTV2222E9", SHIPPED)

    def test_medabots_ax_gets_a_specific_message(self):
        with self.assertRaisesRegex(RomError, "Medabots AX"):
            identify_header(b"MEDABOTSAXRKSVAAAA", SHIPPED)

    def test_unknown_rom_lists_supported_versions(self):
        with self.assertRaisesRegex(RomError, "Metabee Version \\(USA\\)"):
            identify_header(b"POKEMON EMER" + b"BPEE01", SHIPPED)

    def test_tiny_file(self):
        with self.assertRaisesRegex(RomError, "too small"):
            identify_rom(b"\0" * 10, SHIPPED)


class TestIdentityBlock(unittest.TestCase):
    identity = ApIdentity(3, ApIdentity.digest_seed("seed"), ApIdentity.digest_data(SHIPPED.content_hash), False, "Ash")

    def test_round_trip(self):
        raw = self.identity.pack(BLOCK_SIZE)
        self.assertEqual(len(raw), BLOCK_SIZE)
        self.assertEqual(ApIdentity.unpack(raw), self.identity)

    def test_unicode_name(self):
        identity = dataclasses.replace(self.identity, player_name="Métabée ★")
        self.assertEqual(ApIdentity.unpack(identity.pack(BLOCK_SIZE)).player_name, "Métabée ★")

    def test_unverified_flag_survives(self):
        identity = dataclasses.replace(self.identity, unverified=True)
        self.assertTrue(ApIdentity.unpack(identity.pack(BLOCK_SIZE)).unverified)

    def test_blank_memory_is_not_an_identity(self):
        self.assertIsNone(ApIdentity.unpack(bytes(BLOCK_SIZE)))
        self.assertIsNone(ApIdentity.unpack(b"\xFF" * BLOCK_SIZE))
        self.assertIsNone(ApIdentity.unpack(b""))

    def test_too_long_name_is_refused(self):
        with self.assertRaises(RomError):
            dataclasses.replace(self.identity, player_name="x" * 65).pack(BLOCK_SIZE)

    def test_digests_differ_per_seed(self):
        self.assertNotEqual(ApIdentity.digest_seed("a"), ApIdentity.digest_seed("b"))


class TestApplyingPatches(unittest.TestCase):
    def test_only_the_identity_block_changes(self):
        rom = build_rom()
        patched = apply_patch(rom)
        changed = [i for i, (a, b) in enumerate(zip(rom, patched, strict=True)) if a != b]
        self.assertTrue(changed)
        self.assertGreaterEqual(changed[0], BLOCK)
        self.assertLess(changed[-1], BLOCK + BLOCK_SIZE)
        identity = ApIdentity.unpack(patched[BLOCK:BLOCK + BLOCK_SIZE])
        self.assertEqual((identity.slot, identity.player_name, identity.unverified), (1, "Ash", False))
        self.assertEqual(identity.seed_digest, ApIdentity.digest_seed("seed-1"))

    def test_every_supported_version_can_be_patched(self):
        for version in SHIPPED.rom.versions:
            self.assertIsNotNone(ApIdentity.unpack(apply_patch(build_rom(version.header_id))[BLOCK:]))

    def test_already_patched_rom_is_refused(self):
        with self.assertRaisesRegex(RomError, "already has data"):
            apply_patch(apply_patch(build_rom()))

    def test_modified_memory_at_the_target_is_refused(self):
        rom = bytearray(build_rom())
        rom[BLOCK + 10] = 0x12
        with self.assertRaisesRegex(RomError, "already has data"):
            apply_patch(bytes(rom))

    def test_unsupported_rom_is_refused(self):
        with self.assertRaisesRegex(RomError, "not a supported version"):
            apply_patch(build_rom("POKEMON EMERBPEE01"))

    def test_patch_from_other_data_version_is_refused(self):
        with self.assertRaisesRegex(RomError, "Install the matching version"):
            apply_patch(build_rom(), build_data=SHIPPED, installed_data=VERIFIED, allow_unverified=True)

    def test_unverified_build_will_not_patch_without_opt_in(self):
        with self.assertRaisesRegex(RomError, "not been verified"):
            apply_patch(build_rom(), build_data=SHIPPED, installed_data=SHIPPED, allow_unverified=False)

    def test_unverified_build_patches_with_opt_in_and_says_so(self):
        patched = apply_patch(build_rom(), build_data=SHIPPED, installed_data=SHIPPED, allow_unverified=True)
        self.assertTrue(ApIdentity.unpack(patched[BLOCK:BLOCK + BLOCK_SIZE]).unverified)


class TestScriptRewrites(unittest.TestCase):
    """Vanilla rewards are blanked out by script number, and only where the script holds such an instruction."""

    def location(self, scripts=(TEST_SCRIPT,), opcodes=("3C",), name=None):
        neutralize = {"scripts": list(scripts), "opcodes": list(opcodes)}
        location = dataclasses.replace(VERIFIED.locations[0], neutralize=neutralize)
        return dataclasses.replace(location, name=name) if name else location

    def rom_with_rewards(self):
        # script TEST_SCRIPT: give medal 15, a one-byte no-op, give 500 money, give medal 1
        return build_rom(scripts=bytes([0x3C, 0x0F, 0x00, 0x3A, 0x00, 0x32, 0x3C, 0x01]))

    def test_matching_instructions_are_blanked_with_no_ops(self):
        rom = self.rom_with_rewards()
        patched = apply_patch(rom, locations=[self.location()])
        start = SCRIPT_START + 0x1C
        self.assertEqual(patched[start:start + 8], bytes([0, 0, 0x00, 0x3A, 0x00, 0x32, 0, 0]))
        changed = [i for i, (a, b) in enumerate(zip(rom, patched, strict=True)) if a != b and i < BLOCK]
        self.assertEqual(changed, [start, start + 1, start + 6, start + 7])

    def test_several_opcodes_and_scripts(self):
        patched = apply_patch(self.rom_with_rewards(), locations=[self.location(opcodes=("3C", "3A"))])
        self.assertEqual(patched[SCRIPT_START + 0x1C:SCRIPT_START + 0x24], bytes(8))

    def test_a_script_without_such_a_reward_stops_the_patch(self):
        with self.assertRaisesRegex(RomError, "no reward instruction"):
            apply_patch(self.rom_with_rewards(), locations=[self.location(opcodes=("38",))])

    def test_an_unknown_script_stops_the_patch(self):
        with self.assertRaisesRegex(RomError, "no event script number 7"):
            apply_patch(self.rom_with_rewards(), locations=[self.location(scripts=(7,))])

    def test_a_script_that_does_not_parse_stops_the_patch(self):
        with self.assertRaisesRegex(RomError, "Unknown opcode 0xEE.*stopped before it could damage"):
            apply_patch(build_rom(scripts=bytes([0x3C, 0x0F, 0xEE])), locations=[self.location()])

    def test_two_locations_rewriting_one_script_are_refused(self):
        with self.assertRaisesRegex(RomError, "Two locations rewrite event script 1"):
            collect_rewrites([self.location(), self.location(name="other")])

    def test_no_rewrites_means_no_script_lookup(self):
        """ROMs without a findable script bank can still be patched when nothing needs rewriting."""
        rom = bytearray(build_rom())
        rom[SCRIPT_START:SCRIPT_START + 10] = bytes(10)  # destroy the signature
        self.assertIsNotNone(ApIdentity.unpack(apply_patch(bytes(rom))[BLOCK:BLOCK + BLOCK_SIZE]))

    def test_a_missing_script_bank_stops_the_patch(self):
        rom = bytearray(self.rom_with_rewards())
        rom[SCRIPT_START - 0x8000] = 0x12  # break the bank header
        with self.assertRaisesRegex(RomError, "bank header"):
            apply_patch(bytes(rom), locations=[self.location()])
