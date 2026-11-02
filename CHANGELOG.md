# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Versions below `1.0.0` are **pre-releases**: generation works, but the
in-game layer has not yet been verified against a real ROM.

## [Unreleased]

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
  development branch, and a tag-triggered release workflow.

### Known limitations

- Check locations are *candidates* inferred from documented map names, and every memory address is unknown. A seed can
  only be generated with `allow_unverified_build: true`, and the game cannot be played from it until calibration.
- Enemy shuffling, starting-Medabot choice, DeathLink and collection-milestone checks are designed for but not
  implemented.
