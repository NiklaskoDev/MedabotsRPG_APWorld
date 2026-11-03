# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Versions below `1.0.0` are **pre-releases**: the world works, but has not
yet been through a full multiworld play-test.

## [Unreleased]

Calibration against Medabots: Metabee Version (USA) in BizHawk; see `docs/CALIBRATION_NOTES.md`.

### Added

- **Verified memory map**: event flags, medapart counts, the medal case, money, the safe-to-deliver and in-battle
  states. Medals are delivered as complete medal records built like the game builds them, from the medal table in the
  player's ROM.
- **Verified locations**: Nae's medal room, the Odoro Marsh broken parts room, the right locker trade on Medabot
  Island, a Rubberobo medal room chest and all four Fort Fiyun chests. Locations can be detected by an event's done
  flag or its value, and new location status `absent` marks spots that turned out not to exist.
- **Verified** Squidguts, the Medabot Island arcade prize and the Ninja Park hide-and-seek prize, so every existing
  location is verified. The calibrated addresses were also checked on Rokusho (Europe).
- **Verified story goal**: the ending's event 147, set only by the three ending scripts once the staff roll has played
  and Ikki is home. New `goal_status` in `regions.json`; the world counts as verified only once the goal is. A new
  detection type `byte_at_least` reads one byte of a table.
- **Ambush trap**: forces a random Robattle through the game's encounter step counter. An optional table can name the
  value that switches it on.
- State entries in `memory_map.json` may list several conditions that must all hold.
- `tools/analyze_rom.py` lists every reward script by number, with what it gives and the flags it sets.

### Changed

- The identity block and every blank-memory check use `0x00`, how all four ROMs pad their free space. Before, every
  real ROM would have been refused.
- Script rewrites name the event script and the reward opcodes (`{"scripts": [...], "opcodes": [...]}`) and blank
  those instructions with the game's no-op, instead of a byte offset that differs between Metabee and Rokusho. The
  patch format is now 2.
- Items are only delivered in the field with no event running, never in a battle, a menu or at the title screen.
- The story order in `regions.json` is confirmed against the game's chapters.
- The generation gate uses the same rule as the patcher (memory map, goal and every location verified). The shipped data
  passes it, so seeds no longer need `allow_unverified_build`.
- Money pouches add $10, $50 and $200 instead of $2, $10 and $50 (the game keeps money in cents), in line with the
  game's own chests and prizes.
- *Rubberobo Base - Medal Room Medal* is now *Rubberobo Base - Medal Room Chest* (the room holds money).

### Fixed

- Choosing **New Game** made the client report every check and the story goal. The game fills its RAM, the event flags
  included, with `0xFF` as soon as New Game is chosen, and the client read the flags on every tick. They are now read
  only while the game is in the field and the flag table is not all `0xFF`. New required memory-map state `in_field`.
- After connecting to the wrong server once (the "different multiworld" error), the client stayed stopped even when you
  connected to the right one, until it was restarted. A stop now lasts only for the connection that caused it.
- `tools/analyze_rom.py` decoded the battle table's pointers as battle records.

### Removed

- The two lockers and medal room that hold no reward and all shop purchases (buying records nothing) are `absent`;
  their IDs stay reserved. The Shop Purchases option currently adds nothing.

## [0.1.0] - 2026-11-02

First pre-release. Everything that does not depend on the game's memory layout is implemented and tested; everything
that does is data that still has to be confirmed on a real ROM (see `docs/CALIBRATION.md`).

### Added

- **Archipelago world** for *Medabots: Metabee / Rokusho* (GBA, all four English ROM versions), named `Medabots RPG`.
- **YAML options** in six groups with WebHost presets (Casual, Standard, Chaos): goal (story complete, collect medals,
  collect medaparts), location categories (medals, chests, gifts, boss rewards, mini-games, shops, trainer Robattles,
  missable locations), item pool weights, version-exclusive items, battle logic, traps (percentage, per-trap weights,
  strength), received-item messages, and an explicit opt-in for unverified builds.
- **Items**: all 480 medaparts and 30 medals with permanent IDs, money pouches as filler, and four traps (Money Drain,
  Rusty Armor, Medal Nap, Ambush).
- **Logic**: a chain of eleven story areas with *cleared* events, plus optional battle logic that gates areas behind a
  share of the medaparts, capped so a gate can never make a seed unbeatable.
- **Safety nets**: generation refuses unverified data unless opted in; patching refuses unsupported, already-patched or
  mismatched ROMs and only overwrites script bytes it recognises; the client delivers only in a safe game state with
  guarded writes, is idempotent (loading an older save repairs itself) and refuses a ROM that belongs to another seed or
  another version of the world.
- **BizHawk client** built on Archipelago's connection logic, which supports `ws://`, `wss://`, bare `host:port`
  (with automatic fallback to `wss://`) and `archipelago://` links.
- **Developer tools**: `tools/analyze_rom.py` (ROM version, tables, battles, event scripts, free space),
  `tools/ramdiff.py` and `tools/lua/dump_ram.lua` (finding flags and memory tables), `tools/dev.sh`.
- **Documentation**: design, development and calibration guides, the game page and a setup guide.
- **GitHub Actions**: CI on Archipelago 0.6.8 (Python 3.11 to 3.13) with a non-blocking check against Archipelago's
  development branch; a manually run **Tag a release** workflow that derives the tag from `world_version`, checks the
  changelog, lint and tests, pushes an annotated tag and publishes the release; and a **Release** workflow that builds
  the `.apworld` and creates the GitHub release (also usable for an existing tag).

### Known limitations

- Check locations are *candidates* inferred from documented map names, and every memory address is unknown. A seed can
  only be generated with `allow_unverified_build: true`, and the game cannot be played from it until calibration.
- Enemy shuffling, starting-Medabot choice, DeathLink and collection-milestone checks are designed for but not
  implemented.
