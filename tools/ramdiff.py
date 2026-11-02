#!/usr/bin/env python3
"""Find game memory that changed between two snapshots, or that holds a given number.

Snapshots are the raw files written by tools/lua/dump_ram.lua. Typical use while calibrating (see
docs/CALIBRATION.md): take a snapshot, do ONE thing in the game (open a chest, buy a part, win a battle), take another
snapshot, and ask what changed:

    python tools/ramdiff.py diff before_EWRAM.bin after_EWRAM.bin --base 0x02000000 --kinds bit_set,increment

Memory that changes by itself (timers, animation) drowns the result in noise. Record two snapshots a few seconds apart
while doing nothing and pass them with --noise to hide those addresses:

    python tools/ramdiff.py diff a.bin b.bin --noise idle1.bin idle2.bin

To find a number such as your money, search a snapshot for it and narrow the candidates with a second search:

    python tools/ramdiff.py find snapshot.bin --u32 1234 --base 0x02000000
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

KINDS = ("bit_set", "bit_clear", "increment", "decrement", "other")


@dataclass(frozen=True)
class Change:
    offset: int
    before: int
    after: int

    @property
    def kinds(self) -> list[str]:
        """Every way this change can be read. ``4 -> 5`` is both a flag being set and a counter going up."""
        set_bits, cleared_bits = self.after & ~self.before, self.before & ~self.after
        found = []
        if set_bits and not cleared_bits:
            found.append("bit_set")
        if cleared_bits and not set_bits:
            found.append("bit_clear")
        if self.after == (self.before + 1) & 0xFF:
            found.append("increment")
        if self.after == (self.before - 1) & 0xFF:
            found.append("decrement")
        return found or ["other"]

    @property
    def kind(self) -> str:
        """The most specific reading, for display."""
        return self.kinds[0]

    def bit_indices(self) -> list[int]:
        """Flag-array indices (counting bits from the start of the snapshot) of every bit that changed."""
        return [self.offset * 8 + bit for bit in range(8) if (self.before ^ self.after) >> bit & 1]


def noisy_offsets(first: bytes, second: bytes) -> set[int]:
    """Offsets that differ between two snapshots in which nothing relevant happened."""
    return {i for i, (a, b) in enumerate(zip(first, second, strict=False)) if a != b}


def diff(before: bytes, after: bytes, ignore: set[int] | None = None) -> list[Change]:
    if len(before) != len(after):
        raise ValueError(f"snapshots differ in size ({len(before)} vs {len(after)} bytes)")
    ignore = ignore or set()
    return [Change(i, a, b) for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b and i not in ignore]


def find_number(snapshot: bytes, value: int, size: int) -> list[int]:
    """Aligned offsets at which the little-endian number ``value`` of ``size`` bytes occurs."""
    needle = value.to_bytes(size, "little")
    return [i for i in range(0, len(snapshot) - size + 1, size) if snapshot[i:i + size] == needle]


def render_changes(changes: list[Change], base: int, limit: int) -> str:
    lines = [f"{len(changes)} changed byte(s)" + (f", showing the first {limit}" if len(changes) > limit else "")]
    for change in changes[:limit]:
        bits = ", ".join(str(i) for i in change.bit_indices()) if "bit_set" in change.kinds else ""
        lines.append(f"0x{base + change.offset:08X}  {'/'.join(change.kinds):<18}  "
                     f"0x{change.before:02X} -> 0x{change.after:02X}"
                     + (f"  flag bit index(es) from snapshot start: {bits}" if bits else ""))
    return "\n".join(lines)


def hex_int(text: str) -> int:
    return int(text, 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    diff_cmd = commands.add_parser("diff", help="list the bytes that differ between two snapshots")
    diff_cmd.add_argument("before", type=Path)
    diff_cmd.add_argument("after", type=Path)
    diff_cmd.add_argument("--base", type=hex_int, default=0, help="address of the first byte, e.g. 0x02000000")
    diff_cmd.add_argument("--noise", type=Path, nargs=2, metavar=("IDLE_A", "IDLE_B"),
                          help="two snapshots taken while idle; addresses that differ in them are hidden")
    diff_cmd.add_argument("--kinds", default="bit_set,bit_clear,increment,decrement,other",
                          help=f"comma separated subset of {', '.join(KINDS)}")
    diff_cmd.add_argument("--limit", type=int, default=200)

    find_cmd = commands.add_parser("find", help="search a snapshot for a number")
    find_cmd.add_argument("snapshot", type=Path)
    find_cmd.add_argument("--base", type=hex_int, default=0)
    group = find_cmd.add_mutually_exclusive_group(required=True)
    for size, name in ((1, "u8"), (2, "u16"), (4, "u32")):
        group.add_argument(f"--{name}", type=int, help=f"a {size * 8}-bit number")
    args = parser.parse_args(argv)

    try:
        if args.command == "diff":
            kinds = set(args.kinds.split(","))
            if not kinds <= set(KINDS):
                parser.error(f"unknown kind(s): {', '.join(sorted(kinds - set(KINDS)))}")
            ignore = noisy_offsets(args.noise[0].read_bytes(), args.noise[1].read_bytes()) if args.noise else None
            changes = [c for c in diff(args.before.read_bytes(), args.after.read_bytes(), ignore)
                       if kinds.intersection(c.kinds)]
            print(render_changes(changes, args.base, args.limit))
        else:
            size, value = next((s, getattr(args, n)) for s, n in ((1, "u8"), (2, "u16"), (4, "u32"))
                               if getattr(args, n) is not None)
            hits = find_number(args.snapshot.read_bytes(), value, size)
            print(f"{len(hits)} match(es)")
            print("\n".join(f"0x{args.base + offset:08X}" for offset in hits[:200]))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
