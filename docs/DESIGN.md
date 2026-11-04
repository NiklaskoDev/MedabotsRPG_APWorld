# Medabots RPG for Archipelago: Design

This is the design the implementation follows: what the randomizer does, what is and is not known about the game, and
why the code is structured the way it is. [DEVELOPMENT.md](DEVELOPMENT.md) explains how to work on it and
[CALIBRATION.md](CALIBRATION.md) explains how to turn the unverified parts into verified data.

## 1. Scope

* **Game:** *Medabots: Metabee Version* and *Medabots: Rokusho Version* for the Game Boy Advance (Natsume, 2002), the
  English release of the remake of *Medarot 2*. In Archipelago the game is called **`Medabots RPG`**.
* **ROMs:** the four English ROMs (Metabee/Rokusho × USA/Europe). *Medabots AX* (a fighting game) and Japanese ROMs are
  rejected with a specific message.
* **Client:** BizHawk, Archipelago's standard path for GBA games, reusing core's `BizHawkClient`.
* **Minimum Archipelago version:** 0.6.8. The code stays compatible with Python 3.11 to 3.13.

## 2. What is known and what is not

Everything about the game that is **documented** (taken from the MIT-licensed community project
*STulling/Medabots-Randomizer*, see `NOTICE`) lives in the data files as fact. Everything that needs the ROM is **data
that a tool produces**, never a guess in code.

| Documented (`data/game_tables.json`, `data/rom_versions.json`) | Unknown without the ROM (data, marked unverified) |
|---|---|
| ROM header IDs of the four versions | Which script instructions are chests, gifts or battle rewards |
| Event-script opcode length table (137 opcodes) and the region signature | Save-flag, inventory and money addresses in RAM |
| 120 bot models × 4 parts = **480 medaparts** (names) | The "safe to deliver" and "in battle" state addresses |
| **30 medals**, **192 maps**, **96 characters** (names) | Free-space and hook addresses per ROM version |
| Battle (245), part (480) and encounter (191) record layouts | The real story order |

Locations that were only *inferred from a documented map name* (for example *Fort Fiyun - 4 Chest Room*) carry
`status: "candidate"`. Calibration promotes them to `status: "verified"`, or to `status: "absent"` when the spot turns
out to hold nothing detectable (the row keeps its ID but is never selected). A ROM identity of "unverified" propagates:
generation, patching and the client all know whether the data behind a seed was verified. The world counts as
verified only when the memory map, the goal flag and every existing location are.

Calibration (see [CALIBRATION_NOTES.md](CALIBRATION_NOTES.md)) found the shapes the game really uses: event flags two
per byte, numbered like the event scripts and map objects; part counts of two bytes per part; and a medal case of
64-byte records rather than bits. The client builds a new medal's record exactly like the game's own routine, from the
medal table in the player's ROM, so no game data ships with the world. Script rewrites name the event script and the
reward opcodes, because script positions differ between versions while their numbers do not.

## 3. The randomizer

### Goals
1. **Story Complete** (default): reach the last area's cleared event. The client detects the real end of the game
   through a flag (`goal_detect`).
2. **Collect Medals** or 3. **Collect Medaparts**: receive N different ones. The goal count is lowered, with a
   warning, when the pool cannot hold that many.

### Locations
Seven categories, each a YAML toggle: medal pickups, chests and pickups, gifts from characters, boss rewards,
mini-game prizes, shop purchases and trainer Robattles. A category without known locations contributes nothing.
Locations flagged `missable` only hold filler unless `include_missable_locations` is on.

### Items
* **Medaparts** (480): `Head: Psycho Missile (Noctobat)`, item ID `10000 + model * 4 + slot`.
* **Medals** (30): `Medal: Kabuto`, item ID `11000 + medal id`. `?` and `!` look like placeholders and are never
  placed.
* **Money pouches** (small, medium, large) are the filler.
* **Traps**: Money Drain, Rusty Armor, Medal Nap, Ambush.
* Parts and medals of the *other* game version are excluded unless `include_version_exclusives` is on. Which version
  the player owns is not known at generation time, so the exclusives of both versions are excluded together.

The pool builder splits the free slots between parts, medals and money by the configured weights (largest-remainder
rounding, redistributing what a capped kind cannot take), reserves the items a collection goal needs first, and
replaces `trap_percentage` percent of the money pouches with traps chosen by `trap_weights`. Excluded locations
always receive enough filler.

### Traps
Every trap is temporary, capped, deferred while the game is not in a safe state, and never changes permanent state.

| Trap | Effect | Ends |
|---|---|---|
| Money Drain | lose 10 / 25 / 50 % of the money (never below 0) | instant |
| Rusty Armor | armor scale 80 / 60 / 40 % | after the next battle |
| Medal Nap | medal ability disabled | after 1 / 1 / 2 battles |
| Ambush | forces an encounter | after 1 / 1 / 2 encounters |

Every effect is also lifted after five minutes even if the game never reports the end of a battle. A trap whose memory
entries are unknown in a verified memory map is dropped from the pool at generation (and fizzles in the client).

### Logic
* A linear chain of eleven story areas collapsed from the documented map table. Each area has a *Cleared* event that
  opens the next; the last area's event is the goal. The order is provisional and lives in `data/regions.json`.
* `battle_logic` (off / relaxed / standard) additionally gates each area behind a growing share of the medaparts in the
  pool (0 in the first area up to 15 % / 30 % in the last), **capped at half the number of locations in the earlier
  areas**, so the parts a gate needs can always be found before it. Only *usable* medaparts count, the ones of the
  gender of Ikki's first Tinpet (male), because a Tinpet cannot fit parts of the other gender; while `bot_genders` is
  unknown every part counts. Parts are progression items only while they count for it (or while the goal is *Collect
  Medaparts*, which counts every part).
* Rules are JSON expressions (`rules.py`) compiled to Archipelago's rule builder, which gives serialization and
  human-readable explanations.

## 4. Avoiding bricked seeds

| # | Invariant | How it is enforced |
|---|---|---|
| G1 | A build whose data is unverified cannot be played by accident. | Generation raises `OptionError` unless `allow_unverified_build` is set; the patcher refuses unless the patch says so; the client warns; the identity block records it. |
| G2 | Data is consistent. | `data_loader.validate` (unique IDs and names, every map owned by exactly one area, rule references, trap requirements, verified entries complete). |
| G3 | The pool always has exactly one item per location. | `build_item_pool` asserts it; a randomized test covers 200 cases. |
| G4 | Seeds are beatable and the first sphere is not empty. | Core's `WorldTestBase` suite for every goal and logic setting, plus gate-feasibility property tests. |
| G5 | Missable spots never hold progression. | `LocationProgressType.EXCLUDED`. |
| G6 | Story scripts are never damaged. | A rewrite carries the expected original bytes and aborts on any mismatch; overlapping rewrites are refused. |
| G7 | The player always has a complete bot. | Archipelago items only ever add parts or medals; nothing is removed. |
| G8 | Delivery is safe and idempotent. | Parts and medals are *state based* (ensured to be owned, so repeating or loading an older save is harmless). Money and traps use a counter kept on the server. Nothing is delivered unless the game is in a verified safe state and not in a battle; every write is guarded by the bytes that were read; four deliveries per tick at most. |
| G9 | Traps cannot soft-lock. | Safe state only, expiry, no stacking, deferral rather than dropping. |
| G10 | The ROM matches the seed and the world version. | The ROM carries digests of the seed and of the data; the client compares them with the server's `seed_name` and the slot data and stops with an explanation on a mismatch. |
| G11 | Only recognised ROMs are patched, and only blank memory is written. | Header check of the four versions; the identity block region must be blank (`0x00`, the ROMs' padding). Script rewrites only replace instructions with the expected reward opcodes, inside scripts that parse, with the one-byte no-op. |
| G12 | Item and location IDs never change. | Explicit IDs, a test that pins a sample, and the rule in DEVELOPMENT.md. |

## 5. YAML options (v0.1.0)

* **Goal & Victory:** `goal`, `goal_medal_count`, `goal_part_count`
* **Locations:** `shuffle_medal_pickups`, `shuffle_chests_and_pickups`, `shuffle_npc_gifts`, `shuffle_boss_rewards`,
  `shuffle_minigame_prizes`, `shopsanity`, `trainer_robattles`, `include_missable_locations`
* **Item Pool:** `part_weight`, `medal_weight`, `money_weight`, `include_version_exclusives`, `battle_logic`
* **Traps:** `trap_percentage`, `trap_weights`, `trap_strength`
* **Quality of Life:** `receive_item_messages`
* **Advanced:** `allow_unverified_build`
* Core options: `local_items`, `non_local_items`, `exclude_locations`, `priority_locations`, `item_links`,
  `plando_items`, `start_inventory`, `start_inventory_from_pool`, `start_hints`; WebHost presets Casual, Standard, Chaos.

### Not implemented (designed for, no option yet)
Starting Medabot choice, enemy medal-level scaling and bot shuffling (the battle table layout is documented), DeathLink,
area-pass shuffling via map-transition hooks, and collection-milestone checks. An option is only added once the
feature behind it works.

## 6. Architecture

```
worlds/medabots_rpg/
  data/*.json         all game knowledge, with permanent IDs and a verification status
  data_loader.py      the only reader of data/; typed immutable objects; validation (no Archipelago imports)
  options.py          YAML options, groups, presets
  items.py            classification, item groups, the pool builder
  locations.py        which checks exist for the chosen options
  regions.py          regions, entrances, event locations, completion rule
  rules.py            JSON rule expressions -> rule builder; the battle-logic gates
  rom_scripts.py      event-script parser (no Archipelago imports)
  rom_info.py         ROM identification (no Archipelago imports)
  rom.py              the .apmedabots patch container and the seed identity block
  effects.py          client game logic: detection, delivery, traps (no BizHawk, no network)
  client.py           BizHawk client: reads memory, talks to the server, applies effects.py's plans
  __init__.py         the World class
tools/                developer tools (not shipped): dev.sh, analyze_rom.py, ramdiff.py, lua/dump_ram.lua,
                      release_notes.py
```

**The client reads one snapshot, plans on a copy, then applies guarded writes.** `effects.plan_step` never touches
memory. It returns the writes, the bytes each write expects to replace, the on-screen messages and the new state. The
client applies the writes with a guard; if the game changed in between, nothing is written and the same step is planned
again. This makes delivery safe and makes all of it testable without an emulator.

**The patch contains no game data.** It describes which script bytes may be rewritten (with the expected originals)
and carries the identity block. `verify_rom` checks the ROM version, the data version and the blank target memory
before anything is written.

## 7. Connections: `ws://` and `wss://`

The client runs on Archipelago's `CommonClient.server_loop`, which accepts a bare `host:port` (tried as `ws://`
first and retried as `wss://` when the server speaks TLS), an explicit `ws://` or `wss://` address (certificates are
verified against the `certifi` bundle) and `archipelago://` links. The project does not re-implement any of that;
`test/test_connection.py` connects the client context to a local `ws://` server and a local `wss://` server (with a
generated certificate), including the fallback and the rejection of untrusted certificates, to protect the behaviour
across Archipelago updates.

## 8. Release process

Semantic versioning with a leading `v` tag (`v0.1.0`). The **Tag a release** workflow, started by hand from the Actions
tab, derives the tag from `world_version`, verifies the changelog, lint and tests, pushes an annotated tag and calls the
**Release** workflow, which builds the `.apworld` with Archipelago's packager and creates a GitHub release with the
matching changelog section (a pre-release while the major version is 0 or the tag has a suffix). The release workflow is
called directly because a tag pushed with the built-in token does not trigger other workflows. Details are in
[DEVELOPMENT.md](DEVELOPMENT.md#releasing).
