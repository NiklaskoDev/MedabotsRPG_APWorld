import tempfile
import unittest
from pathlib import Path

import ramdiff
from ramdiff import Change, diff, find_number, noisy_offsets


class TestChangeKinds(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(Change(0, 0b0000, 0b0100).kinds, ["bit_set"])
        self.assertEqual(Change(0, 0b0110, 0b0100).kinds, ["bit_clear"])
        self.assertEqual(Change(0, 7, 8).kinds, ["increment"])
        self.assertEqual(Change(0, 8, 7).kinds, ["decrement"])
        self.assertEqual(Change(0, 0b0101, 0b1010).kinds, ["other"])

    def test_ambiguous_changes_report_every_reading(self):
        self.assertEqual(Change(0, 4, 5).kinds, ["bit_set", "increment"])
        self.assertEqual(Change(0, 0xFF, 0x00).kinds, ["bit_clear", "increment"], "a byte wraps around")
        self.assertEqual(Change(0, 4, 5).kind, "bit_set", "display the most specific reading")

    def test_flag_bit_indices_count_from_the_start_of_the_snapshot(self):
        self.assertEqual(Change(3, 0b0000, 0b0100).bit_indices(), [3 * 8 + 2])
        self.assertEqual(Change(0, 0b0001, 0b0101).bit_indices(), [2])


class TestDiff(unittest.TestCase):
    def test_changed_bytes_are_reported_in_order(self):
        before, after = bytes([0, 0, 0, 0]), bytes([0, 1, 0, 8])
        self.assertEqual(diff(before, after), [Change(1, 0, 1), Change(3, 0, 8)])

    def test_noise_is_hidden(self):
        before, after = bytes(4), bytes([1, 1, 1, 1])
        noise = noisy_offsets(bytes(4), bytes([1, 0, 0, 0]))
        self.assertEqual([c.offset for c in diff(before, after, noise)], [1, 2, 3])

    def test_snapshots_of_different_sizes_are_refused(self):
        with self.assertRaises(ValueError):
            diff(bytes(4), bytes(5))


class TestFind(unittest.TestCase):
    def test_finds_aligned_numbers(self):
        snapshot = bytes(8) + (1234).to_bytes(4, "little") + bytes(4) + (1234).to_bytes(4, "little")
        self.assertEqual(find_number(snapshot, 1234, 4), [8, 16])

    def test_ignores_unaligned_matches(self):
        self.assertEqual(find_number(bytes(1) + (1234).to_bytes(4, "little"), 1234, 4), [])


class TestCommandLine(unittest.TestCase):
    def run_main(self, *args):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ramdiff.main([str(a) for a in args])
        return code, out.getvalue()

    def test_diff_prints_addresses_from_the_base(self):
        with tempfile.TemporaryDirectory() as folder:
            before, after = Path(folder, "a.bin"), Path(folder, "b.bin")
            before.write_bytes(bytes(16))
            after.write_bytes(bytes(5) + bytes([0b100]) + bytes(10))
            code, output = self.run_main("diff", before, after, "--base", "0x02000000")
        self.assertEqual(code, 0)
        self.assertIn("0x02000005  bit_set", output)
        self.assertIn("flag bit index(es) from snapshot start: 42", output)

    def test_kind_filter(self):
        with tempfile.TemporaryDirectory() as folder:
            before, after = Path(folder, "a.bin"), Path(folder, "b.bin")
            before.write_bytes(bytes([0, 3]))
            after.write_bytes(bytes([1, 4]))  # 0 -> 1 sets a bit; 3 -> 4 is a counter increment
            _, only_flags = self.run_main("diff", before, after, "--kinds", "bit_set")
            _, only_counters = self.run_main("diff", before, after, "--kinds", "increment")
        self.assertIn("1 changed byte", only_flags)
        self.assertIn("0x00000000", only_flags)
        self.assertIn("0x00000001", only_counters)

    def test_size_mismatch_is_a_clean_error(self):
        with tempfile.TemporaryDirectory() as folder:
            before, after = Path(folder, "a.bin"), Path(folder, "b.bin")
            before.write_bytes(bytes(2))
            after.write_bytes(bytes(3))
            code, _ = self.run_main("diff", before, after)
        self.assertEqual(code, 1)

    def test_find_command(self):
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Path(folder, "s.bin")
            snapshot.write_bytes(bytes(4) + (500).to_bytes(2, "little"))
            _, output = self.run_main("find", snapshot, "--u16", "500", "--base", "0x03000000")
        self.assertIn("1 match", output)
        self.assertIn("0x03000004", output)
