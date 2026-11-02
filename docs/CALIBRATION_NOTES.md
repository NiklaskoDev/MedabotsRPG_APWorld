# Calibration notes

The record [CALIBRATION.md](CALIBRATION.md) asks for: every address, flag and location that was confirmed, on which ROM,
and how. Calibration took place on 2026-11-02 with BizHawk 2.9.1 (mGBA core) and the four English ROMs.

**Method.** Addresses were first read out of the game's own code (Thumb disassembly of the routines named below), then
confirmed in the running game: a Lua script in BizHawk paused the game between commands, started event scripts and
read and wrote memory, so each finding was observed changing as predicted. Ranges are Metabee (USA) ROM offsets unless
stated otherwise; the code is identical in all four versions apart from shifted data.

## Step 0: the four ROMs

| ROM | event_scripts | script bank | medal table | identity block `0x7FF000` |
|---|---|---|---|---|
| Metabee (USA) | `0x76CC8C` | `0x764C8C` | `0x3B6138` | zero, usable |
| Metabee (Europe) | `0x76DEC0` | `0x765EC0` | `0x3B62D8` | zero, usable |
| Rokusho (USA) | `0x76CCB0` | `0x764CB0` | `0x3B6158` | zero, usable |
| Rokusho (Europe) | `0x76DEE4` | `0x765EE4` | `0x3B62F8` | zero, usable |

* All signatures are found and the script walk completes in all four ROMs.
* **Free space is `0x00`, not `0xFF`.** `0x7F4488`-`0x7FFFFF` is zero in every version, so the identity block stays
  at `0x7FF000`, but the patcher and the analyzer used to look for `0xFF` and would have refused every real ROM. Both
  now treat `0x00` as blank.
* **Scripts are numbered.** The game reaches its 2288 event scripts through an index (header `0x4000, 0x51E0`, a
  16-bit offset table at bank + `0x4000`, a 16 KiB bank-number table after it); the bank pointer lives at
  `0x03005590`. 689 scripts sit at different positions in Metabee and Rokusho and 79 differ in content, so script
  rewrites now name the script number and the reward opcodes instead of a byte offset. The patch was applied with the
  world's own patcher to all four ROMs: only the reward instructions and the identity block changed.

## Step 1: memory map (all confirmed on Metabee USA)

| Entry | Address | Found in | Confirmed by |
|---|---|---|---|
| `game_flags` | `0x030057E0`, 2048 bytes | flag API `0x0805311C` (clear), `0x08053154` (set), `0x08053194` (test), reached through the pointer at `0x030057D8` | script 148 set `0x0300582A` bit 7 (even event), script 1609 set `0x03005B04` bit 3 (odd event) |
| `parts_owned` | `0x03004C40`, 960 bytes, stride 2, slot major | `0x0804213C` (add, capped at 99), `0x08042114` (read) | Guardian (model 39, head) at `0x03004C8E`, Ace Hooves (model 39, legs) at `0x03004F5E` |
| `medals_owned` | `0x03000BE0`, 30 records of 64 bytes | add `0x08041D70`, has `0x08041D3C`, remove `0x08041FE4` | the client's record builder matches the game's Tortoise and Bat records byte for byte; the game's own give-medal routine recognises a client-written Bat as owned, and a Robattle with it shows "BAT" |
| `money` | `0x03002B70`, u32, max 99999 | `0x08047D4C` / `0x08047D58` / `0x08047D74` | chest 1609 raised it from 0 to 5000 |
| `safe_to_deliver` | `0x03006468` = 0 | script engine "running" byte (script state + `0xC88`) | 0 in 19 free-walking snapshots; 1 in all dialogue, intro, step-trigger and scripted-battle snapshots |
| `in_battle` | `0x03000440` != 0 | game-mode block | 1 in 9 battle snapshots, 0 everywhere else |

**Event flags.** Event `n` lives in byte `n >> 1` of `game_flags`, high nibble for even `n`. Bit 3 of the nibble is the
done flag (script opcode `0x13` sets it, `0x12` clears it); bits 0-2 are a small value (opcode `0x17`, and the
multi-way jump `0x2F` branches on the current script's own value). Map objects carry a 12-bit id that is both their
script number and their flag, and an object disappears once its flag is set. Reward scripts usually set their own flag.

**Medal records.** Byte 0 bit 7 marks a used slot (the low bits keep a slot number), byte 1 is the medal id, bytes 2-3
the experience to the next level ((level + 1) × 100), byte 5 the level, byte 8 a tier from the medal's level
thresholds, `0x0A`-`0x17` the name (A=1 … Z=26, padded with `0xFE`, normally typed on a naming screen), `0x20`-`0x27`
eight stats (`min(100, (level // 10 + 1) × base)`). A new medal starts half way between the best and the fourth-best
medal level. Bytes 1, 2 and 7 and the stat bases come from the 16-byte medal table entry. The client now writes exactly
this record; the party's byte 2 refers to a medal by id.

**Not yet known.** `battle_armor_scale`, `battle_medal_disable` and `force_encounter` stay `null`, so seeds drop the
Rusty Armor, Medal Nap and Ambush traps (Money Drain works). The random battle id is chosen into script state +
`0xC2A` (`0x0300640A`) from the map's encounter table when `0x0300640D` is 0; that is the likely hook for
`force_encounter`. The start menu could not be opened during calibration (its unlock condition was not found), so the
safe state was not observed with the menu open.

**Delivery rule.** Delivery now also waits while `in_battle` is set, so a random-encounter battle (which runs no event
script) is never written to.

## Step 2: locations (Metabee USA)

Each verified location was run twice from the same savestate: on the original ROM (flag set, vanilla reward received)
and on a ROM patched by the world (flag set, no vanilla reward, script ends normally).

| ID | Location | Script | Detect | Removed reward | Status |
|---|---|---|---|---|---|
| 20001 | Nae's medal room | 236-241 (choose one of six) | event 230 | medal | verified |
| 20002 | Broken parts room | 384 | event 384 | item `0x04` | verified |
| 20003 | Squidguts | 368 | event 368 | 2 parts + medal | candidate: rewards and removal confirmed, the flag is set after two Robattles that the test party could not win |
| 20004 | Arcade prize | 489 / 495 | none found | | candidate |
| 20005 | Surprise site left locker | none | | | absent: no reward on the map |
| 20006 | Surprise site right locker | 606 (a part trade) | event 606 value 1 | the received part (the hand-in stays) | verified |
| 20007 | Rosewood medal room | 1317 | | | absent: a display, text only |
| 20008 | Rubberobo medal room | 1548 | event 1548 | money (2000) | verified; renamed "Medal Room Chest", the room holds money, not a medal |
| 20009-20012 | Fort Fiyun four chests | 1608-1611 | events 1608-1611 | a Medabot, 5000, 500, 500 money | verified |
| 20013 | Ninja hide & seek prize | probably 1971 (Main Area) | | | candidate |
| 20101-20109 | Shop purchases | | | | absent: buying sets no flag |

Money note: script money is ten times the script operand (chests give 500 to 5000), while money pouches add 200, 1000
and 5000. The pouch sizes may want rebalancing.

## Starting scripts and warping from a Lua script

Useful for trying a reward without playing to it (all addresses Metabee USA, same in every version):

* **Start event script `n`:** write `n` to `0x0300646E` and `0x03006470` (u16), 0 to `0x0300646A` (u16, offset) and
  `0x03006469`, 0 to `0x03006494`, 1 to `0x03003815`, then 1 to `0x03006468`. The engine runs it from the next frame.
  Writing an offset to `0x0300646A` right after starts it in the middle.
* **Run your own bytes:** build a bank in free EWRAM (`0x02038600`: `00 40 02 40`; at +`0x4000`: `04 80 00 00` and
  then the script), point `0x03005590` at it, start script 0 as above, and restore the pointer once `0x03006468` is 0
  again.
* **Warp:** run `0B <map> 00 00 <x> <y> 06` that way (opcode `0x0C` is the same without the fade). The current map is
  `0x03005FDE`.
* **Robattle:** `33 <battle> 00 01 06`; a soft reset follows a lost battle.
* Useful opcodes: `06` end, `00` no-op, `01` text, `13`/`12` set/clear flag, `17` set flag value, `36` item, `38` part,
  `3A` money, `3C` medal, `3D` Medabot.

## What is left

1. **`goal_detect`.** The flag that marks the end of the story was not identified (the credits mode is entry 20 of the
   scene table at `0x483AE0`; what starts it was not traced). Without it the Story Complete goal cannot be detected.
2. **The three candidate locations** above, and the start-menu state.
3. **The other versions at runtime.** RAM addresses were only exercised on Metabee (USA); the code that uses them is
   identical in all four ROMs, but CALIBRATION.md asks for one more version to be checked.
4. **Story order** in `regions.json` is still the provisional one.
5. **More locations.** `analyze_rom.py` lists 180 reward scripts; the world uses 22 rows of which 8 are verified.
6. **Step 5**, the two-player play-test.

## Second pass (same day): open items

* **State flags corrected.** `0x03000440` is *not* "in battle": it stays 1 after the first battle. The game's main mode
  `0x0300178C` is 1 in the field, 0 in Robattles and the B-button menu, 2 during scene switches and some menus, 3 at
  the title/boot screen. `safe_to_deliver` is now two conditions (script engine idle **and** mode 1); without the
  second one the client would have delivered at the title screen, where no script runs. `in_battle` is mode 0 **and**
  mode-0 sub-scene (`0x03002B8C`) in {3, 5, 6, 7, 8, 9}; the menu uses 1 and 2. Checked live with the world's own code
  while walking, in a chest dialogue, in and after a won Robattle, in the B menu, the Medawatch screen and at the real
  title screen. State entries may now be a list of conditions that must all hold.
* **The menu** opens with **B** (not Start) once `0x03006413` (script state + `0xC33`, set by opcode `0x5D`) is non-zero.
  It shows money as dollars and cents: the stored money is in cents, so the client's money pouches (200/1000/5000) are
  only $2/$10/$50 while chests give $5-$50. Worth rebalancing.
* **Story order** comes from the game's chapter byte (`0x03005FDF`, set by opcode `0x6B`; map objects carry a chapter
  mask): Riverview (0-1), Mt. Odori/Odoro Marsh (2), Medabot Island, Haunted House and a first Castle visit (3),
  Medaropolis and Rosewood (4), Rubberobo and a first Fort Fiyun visit (5), Kodine Kingdom (6), Fort Fiyun (7), the
  Castle finale with Mega-Emperor (event 916) and Babyblu (8), then chapter 9 (Babyblu rematch, most of Ninja Park),
  set by Ikki's-room trigger 157 after the chapter-8 return home. By first visit this matches `regions.json`.
* **Goal (not yet in the data).** Best candidate: the chapter byte reaching 9, i.e. byte `0x7FF` of `game_flags`. The
  credits are scene 20 (reached from the battle-end code through scenes 25 and 12) but the exact trigger was not traced.
* **Winning battles for tests.** Battle part records are 0x18 bytes, current armor at +0x11: own side from `0x030005D8`,
  enemies from `0x030008D8`, bots 0x100 apart. Keeping enemy armor at 1 and own at 255 wins any Robattle.
* **Analyzer bug.** `battles_offset` is a table of pointers to the 40-byte records (which follow the encounter table);
  `analyze_rom.py` still decodes the pointers as records.
