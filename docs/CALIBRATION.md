# Calibration: turning candidate data into verified data

The world ships with everything that can be derived from documented game tables, and with *candidate* data for
everything else. Until a person with a real ROM has confirmed that data, generation refuses to run
(`allow_unverified_build`), and the client and patcher say so. This guide is the procedure for doing that once. It needs
no programming, only BizHawk, your own ROM and the tools in this repository.

You are done when:

* `data/memory_map.json` has `"verified": true` and every required entry filled in,
* every location in `data/locations.json` has `"status": "verified"` with a `detect` entry (and a `neutralize` entry
  where the vanilla reward must be removed), or `"status": "absent"` when it turned out not to exist,
* `data/regions.json` has a `goal_detect` entry and `"goal_status": "verified"`,
* `tools/dev.sh test` passes, and a two-player test multiworld plays through (step 5).

**Where things stand** (calibration of 2026-11-02, see [CALIBRATION_NOTES.md](CALIBRATION_NOTES.md) for every
finding and how it was confirmed): the memory map is verified on Metabee (USA) and Rokusho (Europe); all 11 existing
locations are verified and 11 are absent; the story order is confirmed; the goal is the ending's event 147, seen set
after the staff roll. The world therefore counts as verified and seeds generate without `allow_unverified_build`.
Rusty Armor and Medal Nap have no address to poke and stay unavailable. Step 5, the multiworld play-test, is still open.

## Requirements

* BizHawk 2.9 or later and an English *Metabee* or *Rokusho* ROM (any of the four versions; calibrate on one, then check
  the others with the analysis tool).
* A checkout of this repository. `tools/dev.sh setup` prepares everything else.

Keep notes. For every memory address or flag you confirm, write down the ROM version and how you confirmed it.

## Step 0: analyze the ROM

```bash
tools/dev.sh run tools/analyze_rom.py path/to/rom.gba --json report.json
```

This tells you which version the ROM is, where the documented tables are, every battle, every *give medal*
instruction in the event scripts (with its script offset and the medal it gives), and every **reward script by
number**: each event script that gives an item, part, money, a medal or a Medabot, with the event flags it sets. Script
`n` is also map object `n` and owns event flag `n`, and most reward scripts set their own flag ("sets own flag"), so
this list is where locations come from. Check three things:

1. **All signatures are found** (`event_scripts` at least) and the script bank is found. If one says `NOT FOUND`, the
   ROM differs from the documented one; note which.
2. **The identity block is blank.** `memory_map.json` reserves `ap_block` (default `0x7FF000`, 256 bytes) in the ROM for
   the seed identity. Blank means `0x00`: all four ROMs pad their unused space with zeros. The report says "blank,
   usable" or lists other blank runs. Pick one, update `ap_block.rom_offset`, and make sure it is blank in all four ROM
   versions.
3. **The script walk completes** (`stopped early` is not shown). If it stops, the opcode table has a wrong entry near the
   reported offset; fix `script_opcode_lengths` in `data/game_tables.json`.

## Step 1: find the memory map

You will use two tools. `tools/lua/dump_ram.lua` saves snapshots of the game's RAM from BizHawk, and `tools/ramdiff.py`
compares them.

1. In BizHawk: `Tools > Lua Console > Script > Open Script…`, choose `tools/lua/dump_ram.lua`, then load the game.
2. Press **F9** at any time to save a snapshot. Files named `medabots_snapshot_001_EWRAM.bin`,
   `medabots_snapshot_001_IWRAM.bin`, … appear in BizHawk's folder. The numbers follow the order you pressed F9, so write
   down what you did before each one.
3. Compare two snapshots, giving the base address of the memory area (`0x02000000` for EWRAM, `0x03000000` for IWRAM):

   ```bash
   python tools/ramdiff.py diff medabots_snapshot_001_EWRAM.bin medabots_snapshot_002_EWRAM.bin --base 0x02000000
   ```

**Hide noise first.** Memory that changes by itself (timers, animations) buries the signal. Take two snapshots a few
seconds apart while standing still, and pass them as `--noise IDLE_A IDLE_B`.

Each entry of `memory_map.json` has a recipe. Work through them in this order and write the address into the JSON as you
go (`{"address": "0x...", "kind": "...", "size": N}`):

| Entry | How to find it |
|---|---|
| `tables.money` (`u32`) | Snapshot, then `ramdiff.py find SNAPSHOT --u32 <your money>`. Buy or sell something, snapshot again and search for the new amount. The address present in both searches is your money. Set `maximum` to the highest amount the game allows. |
| `tables.parts_owned` (`bitfield` or `bytes`) | Snapshot, buy a part, snapshot, diff. Do it for two parts of the *same bot* (different slot) and two of the *same slot* (different bots). The distance between the changes tells you the layout: `model_major` if parts of the same bot are next to each other, `slot_major` if parts of the same slot are. Set `size` to cover all 480 entries (60 bytes for a bitfield). A `bytes` table whose entries are wider than one byte (a count plus something else) takes `"stride"`; the first byte of an entry is the count. *(Found: `bytes`, stride 2, slot major.)* |
| `tables.medals_owned` | The same, with a medal pickup. If the game keeps whole medal records instead of bits, use `"kind": "records"` with `"record_size"`; the client then builds records like the game's add-medal routine from the ROM medal table (`medal_table_offset` in `rom_versions.json`). *(Found: 30 records of 64 bytes.)* |
| `tables.game_flags` (`bitfield`) | Snapshot, open one chest or take one gift, snapshot, diff with `--kinds bit_set`. The changed bit is the flag of that check. Repeat for several checks; the flags cluster in one array. The array starts at its lowest address; `size` must cover the highest flag you need. *(Found: 4096 event flags, two per byte; see the comment in `memory_map.json`. Locations refer to them by event number.)* |
| `state.safe_to_deliver` | A byte that has one value while you walk around freely (list those in `values`) and another in menus, dialogue, battles and screen transitions. Take snapshots in each situation and diff them. The client delivers nothing unless this is true, so be strict. |
| `state.in_battle` | A byte that is non-zero during a battle. |
| `state.in_field` | A byte that has one value while you walk around the overworld (list it in `values`) and another at the title screen, between scenes and in battles. The client reads check and goal flags only while it holds, because choosing **New Game** fills the game's RAM, the event flags included, with `0xFF`. Check it from the title menu through "New Game" and the first minutes of a fresh game: no check may appear. A verified map without this entry is rejected. |
| `optional_tables.*` | Only if you find them: a value the game reads at the start of a battle for armor (`battle_armor_scale`, 100 means unchanged), for disabling the medal (`battle_medal_disable`) and for forcing an encounter (`force_encounter`). Leave them `null` if you cannot find them; the matching trap is then dropped from seeds automatically. |

Test every address with BizHawk's *RAM Watch* or *Hex Editor*: poke the value yourself and see the game react, and make
sure it survives saving and reloading. The memory map's `hints` section lists pointers from earlier community research
that may save time (they are never read by the client).

When every required entry is filled in, set `"verified": true`. The loader refuses a verified map with missing entries.

## Step 2: verify the locations

For each location in `data/locations.json`:

1. Find its reward script in the report's reward-script list (the map object at that spot has the same number), or play
   to it, snapshot before and after receiving the reward, and diff with `--kinds bit_set`. Fill in
   `"detect": {"type": "event", "flag": <n>}` for an event's done flag, or
   `"detect": {"type": "event_value", "flag": <n>, "value": <v>}` when the script only raises the event's 3-bit value
   (some trades do). `{"type": "flag", "table": "game_flags", "bit": <index>}` still works for a raw bit.
2. Name the vanilla reward the patch must remove: `"neutralize": {"scripts": [<n>, ...], "opcodes": ["38", ...]}`. The
   patch blanks every instruction with one of those opcodes in those scripts with the one-byte no-op `0x00`, and stops
   if a script does not parse or holds no such instruction. Reward opcodes: `36` item, `38` part, `3A` money, `3C`
   medal, `3D` Medabot. Scripts are addressed by number because a script's position in the ROM differs between
   Metabee and Rokusho, while its number does not. Apply the patch, trigger the event and confirm that the vanilla
   reward is gone, the flag is still set and the story continues.
3. Check the name (`Area - Place Reward`), the `map` (it decides the area) and whether the spot can be missed
   (`"missable": true`). Set `"status": "verified"`. A spot that holds no reward or cannot be detected gets
   `"status": "absent"`: its row (and ID) stays, but it is never selected.

New locations are added as new rows with a **new ID** (continue the numbering, never reuse or change an ID). Locations
that turn out not to exist stay in the file with `"status": "absent"`; removing a row breaks existing seeds only if it
was ever released, so prefer fixing it.

To try a reward script without playing to it, the calibration notes describe how to start any event script (and warp)
from a BizHawk Lua script by writing the script engine's state.

Also confirm `data/regions.json`: the order of the areas, the `goal_event`, and the `goal_detect` flag that marks the end
of the game, then set `goal_status` to `verified`; until then the world counts as unverified. If the real order differs,
reorder the areas (each must be listed after its parent).

## Step 3: check the other three ROM versions

Run `analyze_rom.py` on each of the other three ROMs. The tables, the script region and the blank block must all be
found. RAM addresses are expected to be the same in all versions; confirm the important ones (flags, money, safe state)
on at least one more.

## Step 4: run the tests

```bash
tools/dev.sh lint
tools/dev.sh test
```

The tests check that IDs are unique, that every map belongs to one area, that rules refer to real items, that verified
locations have a `detect` entry, and that a verified memory map is complete.

## Step 5: play-test a multiworld

Generate a two-player seed (this world plus any other, or two Medabots slots) and play at least:

* receive an item while walking, in a menu, in a battle and in a cutscene (it must wait, then arrive once);
* send a check from each category you enabled;
* save, receive items, load the *older* save and confirm the items are restored;
* every trap type once, including that its effect ends;
* reaching the goal;
* connect with `ws://` and with `wss://` (see the setup guide).

[PLAYTEST.md](PLAYTEST.md) turns this list into a full plan: what calibration could not prove, the seeds to generate,
every case with its priority and expected result, a suggested order, and the exit criteria for this step. Rusty Armor
and Medal Nap are unavailable, so "every trap type" means Money Drain and Ambush.

## Step 6: release

Edit `CHANGELOG.md`, set `world_version` in `worlds/medabots_rpg/archipelago.json` to `1.0.0`, commit, and tag
`v1.0.0`. See [DEVELOPMENT.md](DEVELOPMENT.md#releasing). Remove the pre-release notices from the README and the game
page.
