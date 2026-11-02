"""ROM identification, the seed identity block and the patch container (with all of its refusals)."""
import dataclasses
import os
import tempfile
import unittest
from unittest import mock

from .. import rom as rom_module
from ..data_loader import get_world_data
from ..rom import (
    ApIdentity,
    MedabotsRPGProcedurePatch,
    PatchError,
    collect_rewrites,
    identify_header,
    identify_rom,
    write_patch,
)
from .support import SCRIPT_START, build_rom, verified_data

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
        with self.assertRaisesRegex(PatchError, "Japanese"):
            identify_header(b"MEDACOREKBTV2222E9", SHIPPED)

    def test_medabots_ax_gets_a_specific_message(self):
        with self.assertRaisesRegex(PatchError, "Medabots AX"):
            identify_header(b"MEDABOTSAXRKSVAAAA", SHIPPED)

    def test_unknown_rom_lists_supported_versions(self):
        with self.assertRaisesRegex(PatchError, "Metabee Version \\(USA\\)"):
            identify_header(b"POKEMON EMER" + b"BPEE01", SHIPPED)

    def test_tiny_file(self):
        with self.assertRaisesRegex(PatchError, "too small"):
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
        self.assertIsNone(ApIdentity.unpack(b"\xFF" * BLOCK_SIZE))
        self.assertIsNone(ApIdentity.unpack(b""))

    def test_too_long_name_is_refused(self):
        with self.assertRaises(PatchError):
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
        with self.assertRaisesRegex(PatchError, "already has data"):
            apply_patch(apply_patch(build_rom()))

    def test_modified_memory_at_the_target_is_refused(self):
        rom = bytearray(build_rom())
        rom[BLOCK + 10] = 0x12
        with self.assertRaisesRegex(PatchError, "already has data"):
            apply_patch(bytes(rom))

    def test_unsupported_rom_is_refused(self):
        with self.assertRaisesRegex(PatchError, "not a supported version"):
            apply_patch(build_rom("POKEMON EMERBPEE01"))

    def test_patch_from_other_data_version_is_refused(self):
        with self.assertRaisesRegex(PatchError, "Install the matching version"):
            apply_patch(build_rom(), build_data=SHIPPED, installed_data=VERIFIED, allow_unverified=True)

    def test_unverified_build_will_not_patch_without_opt_in(self):
        with self.assertRaisesRegex(PatchError, "not been verified"):
            apply_patch(build_rom(), build_data=SHIPPED, installed_data=SHIPPED, allow_unverified=False)

    def test_unverified_build_patches_with_opt_in_and_says_so(self):
        patched = apply_patch(build_rom(), build_data=SHIPPED, installed_data=SHIPPED, allow_unverified=True)
        self.assertTrue(ApIdentity.unpack(patched[BLOCK:BLOCK + BLOCK_SIZE]).unverified)


class TestScriptRewrites(unittest.TestCase):
    """Vanilla rewards are overwritten only where the expected original bytes are found."""

    def location(self, offset="0x1C", expect="3c0f", replace="3c01"):
        neutralize = {"offset": offset, "expect": expect, "replace": replace}
        return dataclasses.replace(VERIFIED.locations[0], neutralize=neutralize)

    def rom_with_medal_instruction(self):
        return build_rom(scripts=bytes([0x3C, 0x0F, 0x00]))  # right after the 28-byte first instruction (0x1C)

    def test_rewrite_is_applied_in_place(self):
        rom = self.rom_with_medal_instruction()
        patched = apply_patch(rom, locations=[self.location()])
        start = SCRIPT_START + 0x1C
        self.assertEqual(patched[start:start + 2], bytes([0x3C, 0x01]))
        changed = [i for i, (a, b) in enumerate(zip(rom, patched, strict=True)) if a != b and i < BLOCK]
        self.assertEqual(changed, [start + 1])

    def test_unexpected_original_bytes_stop_the_patch(self):
        with self.assertRaisesRegex(PatchError, "Unexpected data"):
            apply_patch(self.rom_with_medal_instruction(), locations=[self.location(expect="3c10")])

    def test_rewrite_outside_the_region_is_refused(self):
        with self.assertRaisesRegex(PatchError, "outside the script region"):
            apply_patch(build_rom(), locations=[self.location(offset="0x20000")])

    def test_overlapping_rewrites_are_refused(self):
        first, second = self.location(), dataclasses.replace(self.location(), name="other")
        second = dataclasses.replace(second, neutralize={"offset": "0x1D", "expect": "0f00", "replace": "0f01"})
        with self.assertRaisesRegex(PatchError, "overlap"):
            collect_rewrites([first, second])

    def test_no_rewrites_means_no_script_lookup(self):
        """ROMs without a findable script region can still be patched when nothing needs rewriting."""
        rom = bytearray(build_rom())
        rom[SCRIPT_START:SCRIPT_START + 10] = bytes(10)  # destroy the signature
        self.assertIsNotNone(ApIdentity.unpack(apply_patch(bytes(rom))[BLOCK:BLOCK + BLOCK_SIZE]))
