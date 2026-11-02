import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import analyze_rom
from worlds.medabots_rpg.data_loader import get_world_data
from worlds.medabots_rpg.test.support import SCRIPT_START, TEST_SCRIPT, build_rom

DATA = get_world_data()
BATTLES = next(v for v in DATA.rom.versions if v.id == "metabee_us").battles_offset
RECORDS = BATTLES - 0x3000


def battle_record(character, bots):
    record = bytearray(40)
    record[0], record[2] = character, len(bots)
    for index, (head, right, left, legs, medal, level) in enumerate(bots):
        record[4 + index * 12:4 + index * 12 + 6] = bytes([head, right, left, legs, medal, level])
    return bytes(record)


def rom_with_content():
    # at script offset 0x1C: give medal 15, no-op, give medal 1; later a second 0x3C
    rom = bytearray(build_rom(scripts=bytes([0x3C, 0x0F, 0x00, 0x3C, 0x01, 0x00, 0x00, 0x3C, 0x1B])))
    # the battle table holds pointers; every battle points at the same record here
    record = battle_record(0x13, [(0, 0, 0, 0, 1, 5), (120, 120, 120, 120, 0, 9)])
    rom[RECORDS:RECORDS + 40] = record
    for index in range(245):
        rom[BATTLES + 4 * index:BATTLES + 4 * index + 4] = (0x08000000 + RECORDS).to_bytes(4, "little")
    return bytes(rom)


class TestAnalysis(unittest.TestCase):
    report = analyze_rom.analyze(rom_with_content())

    def test_version_and_tables(self):
        self.assertEqual(self.report["rom"]["id"], "metabee_us")
        self.assertEqual(self.report["tables"]["event_scripts"], hex(SCRIPT_START).upper().replace("0X", "0x"))
        self.assertIsNone(self.report["tables"]["part_table"])

    def test_give_medal_instructions_are_listed_with_names_and_offsets(self):
        found = [(m["script_offset"], m["medal"]) for m in self.report["scripts"]["give_medal"]]
        self.assertEqual(found, [("0x1C", "Bat"), ("0x1F", "Kabuto"), ("0x23", "?")])

    def test_script_walk_completes_on_a_clean_region(self):
        scripts = self.report["scripts"]
        self.assertIsNone(scripts["stopped_early"])
        self.assertGreater(scripts["instruction_count"], 1000)
        self.assertEqual(scripts["opcode_histogram"]["0x3C"], 3)

    def test_reward_scripts_are_listed_by_script_number(self):
        rewards = analyze_rom.analyze(build_rom(scripts=bytes([0x3C, 0x0F, 0x3A, 0x01, 0xF4, 0x13, 0x00, 0x01])))
        listed = rewards["reward_scripts"]
        self.assertEqual(listed["count"], 3)
        self.assertEqual(listed["scripts"], [{"script": TEST_SCRIPT, "rewards": ["medal Bat", "money 5000"],
                                              "sets_flags": [1], "sets_own_flag": True}])

    def test_battles_are_decoded_with_names(self):
        first = self.report["battles"][0]
        self.assertEqual(first["character"], "Dr. Aki")
        self.assertEqual(first["bots"][0]["head"], "Psycho Missile")
        self.assertEqual(first["bots"][0]["medal"], "Kabuto")
        self.assertEqual(first["bots"][0]["medal_level"], 5)
        self.assertEqual(first["bots"][1]["head"], "(none)", "the 'no part' ID")
        self.assertEqual(len(self.report["battles"]), 245)

    def test_identity_block_and_blank_runs(self):
        self.assertTrue(self.report["identity_block"]["blank"])
        lengths = [int(run["length"], 16) for run in self.report["blank_runs"]]
        self.assertTrue(lengths)
        self.assertEqual(lengths, sorted(lengths, reverse=True))

    def test_a_used_identity_block_is_detected(self):
        rom = bytearray(rom_with_content())
        rom[DATA.memory_map.ap_block_offset + 3] = 0x12
        self.assertFalse(analyze_rom.analyze(bytes(rom))["identity_block"]["blank"])

    def test_watched_opcode_context(self):
        report = analyze_rom.analyze(rom_with_content(), watch_opcodes=(0x3C,))
        hit = report["scripts"]["watched"]["0x3C"][0]
        self.assertEqual((hit["script_offset"], hit["raw"], hit["after"][:2]), ("0x1C", "3c0f", "00"))

    def test_unparseable_scripts_are_reported_not_fatal(self):
        report = analyze_rom.analyze(build_rom(scripts=bytes([0xEE])))
        self.assertIn("0xEE", report["scripts"]["stopped_early"])

    def test_blank_run_finder(self):
        data = bytes([1]) + bytes(300) + bytes([2]) + bytes(10) + bytes([3]) + bytes(500)
        runs = analyze_rom.blank_runs(data, minimum=256)
        self.assertEqual([r["length"] for r in runs], ["0x1F4", "0x12C"])


class TestCommandLine(unittest.TestCase):
    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = analyze_rom.main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def test_summary_and_json_report(self):
        with tempfile.TemporaryDirectory() as folder:
            rom, report = Path(folder, "game.gba"), Path(folder, "report.json")
            rom.write_bytes(rom_with_content())
            code, output, _ = self.run_main(rom, "--json", report, "--opcode", "0x3C")
            saved = json.loads(report.read_text())
        self.assertEqual(code, 0)
        self.assertIn("Medabots: Metabee Version (USA)", output)
        self.assertIn("'Give medal' instructions: 3", output)
        self.assertIn("Opcode 0x3C: 3 occurrences", output)
        self.assertIn("blank, usable", output)
        self.assertEqual(saved["rom"]["id"], "metabee_us")

    def test_unsupported_rom_is_a_clean_error(self):
        with tempfile.TemporaryDirectory() as folder:
            rom = Path(folder, "other.gba")
            rom.write_bytes(build_rom("POKEMON EMERBPEE01"))
            code, _, error = self.run_main(rom)
        self.assertEqual(code, 1)
        self.assertIn("not a supported version", error)

    def test_missing_file_is_a_clean_error(self):
        code, _, error = self.run_main("/nonexistent/game.gba")
        self.assertEqual(code, 1)
        self.assertIn("error:", error)
