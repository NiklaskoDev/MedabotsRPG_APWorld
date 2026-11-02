# Medabots RPG for Archipelago: Design

This is the design the implementation follows. It records what the randomizer looks like, what is and is not known
about the game, and why the code is structured the way it is. [DEVELOPMENT.md](DEVELOPMENT.md) explains how to work on
it, and [CALIBRATION.md](CALIBRATION.md) explains how to turn the unverified parts into verified data.

## 1. Scope

* **Game:** *Medabots: Metabee Version* and *Medabots: Rokusho Version* for the Game Boy Advance (Natsume, 2002), the
  English release of the remake of *Medarot 2*. In Archipelago the game is called **`Medabots RPG`**.
* **ROMs:** the four English ROMs (Metabee/Rokusho × USA/Europe). *Medabots AX* (a fighting game) and Japanese ROMs are
  not supported.
* **Client:** BizHawk (Archipelago's standard path for GBA games), reusing core's `BizHawkClient`.
* **Minimum Archipelago version:** 0.6.8.

## 2. What is known and what is not

The world is built from facts about the game that are **documented** (taken from the MIT-licensed community project
*STulling/Medabots-Randomizer*, see `NOTICE`) and keeps everything that needs the ROM as **data** that is produced by a
tool, never guessed.

| Documented (shipped in `data/game_tables.json`, `data/rom_versions.json`) | Unknown without the ROM (data, unverified) |
|---|---|
| ROM header IDs of the four versions | Which script instructions are chests, gifts or battle rewards |
| Event-script opcode length table (137 opcodes) and the region signature | Save-flag and inventory addresses in RAM |
| 120 bot models × 4 parts = **480 medaparts** (names) | "Safe to deliver" and "in battle" state addresses |
| **30 medals**, **192 maps**, **96 characters** (names) | Hook and free-space addresses per ROM version |
| Battle (245), part (480), encounter (191) record layouts | The real story order |

Locations that were only *inferred from a documented map name* (for example *Fort Fiyun - 4 Chest Room*) are stored
with `status: "candidate"`. The ROM analysis tool promotes them to `status: "verified"`.

## 3. The randomizer

### Goals
1. **Complete the story** (default): reach the final area's *Story Complete* event.
2. **Collect N medals** received through Archipelago.
3. **Collect N medaparts** received through Archipelago.

The goal event is an Archipelago *event*, so it can never hold an item.

### Locations (each category is a YAML toggle)
Medal pickups, chests and ground pickups, gifts from characters, boss Robattle rewards, mini-game prizes, shop
purchases and trainer Robattles. Categories that currently have no known locations simply contribute nothing.

### Items
* **Medaparts** (480): `Head: Psycho Missile (Noctobat)`. Item IDs `10000 + model * 4 + slot`.
* **Medals** (30): `Medal: Kabuto`. Item IDs `11000 + medal id`.
* **Money pouches** (filler) and **traps**.
* Parts and medals that only exist in the *other* version are excluded unless `include_version_exclusives` is on.

### Traps
Money Drain, Rusty Armor, Medal Nap, Ambush. Every trap is temporary, capped, deferred while the player is in a unsafe
state and never changes permanent state. Weights, the share of filler that becomes traps, and their strength are
configurable.

### Logic
* A linear chain of ~11 story areas collapsed from the documented map table. Each area has a *Cleared* event that opens
  the next. The order is provisional and lives in `data/regions.json`.
* `battle_logic` (off / relaxed / standard) additionally gates areas behind a growing share of the medaparts in the
  pool, capped so that the requirement is always satisfiable from earlier areas. Parts become *progression* items only
  while it is on.
* Rules are plain JSON compiled to Archipelago's rule builder (see `rules.py`), which gives serialization and
  human-readable explanations for free.

## 4. Avoiding bricked seeds

| # | Invariant | How it is enforced |
|---|---|---|
| G1 | A build whose data is unverified cannot be played by accident. | Generation raises an `OptionError` unless `allow_unverified_build` is set; the client and patcher refuse unverified memory maps. |
| G2 | Every location has a detection method and every item a delivery method. | `data_loader.validate` plus tests. |
| G3 | Item pool size always equals the number of free locations. | Pool builder pads or trims filler; tested across option permutations. |
| G4 | Seeds are beatable and the first sphere is not empty. | Core `WorldTestBase` checks plus tests per goal and option set. |
| G5 | One-time or missable spots never hold progression. | `LocationProgressType.EXCLUDED` unless `include_missable_locations`. |
| G6 | Story scripts are never altered, only reward opcodes. | Patch rewrites carry the expected original bytes and abort on mismatch. |
| G7 | The player always has a complete bot. | Archipelago items only ever add parts or medals; nothing is removed. |
| G8 | Delivery is safe and idempotent. | Parts and medals are *state based* (re-applied until present, so loading an older save repairs itself). Consumables and traps use a server-side counter. Only delivered in the safe state, with guarded writes. |
| G9 | Traps cannot soft-lock. | Safe state only, expiry timers, per-type caps, deferral (never dropping). |
| G10 | The ROM matches the seed. | Seed and slot are written into the ROM; the client compares them with the server's `seed_name`. |
| G11 | Only recognised ROMs are patched. | Header check of the four versions; the patcher writes only into verified-blank space. |
| G12 | Item IDs never change between releases. | Explicit IDs in data, uniqueness and range tests, rule documented in DEVELOPMENT.md. |

## 5. YAML options (v0.1.0)

* **Goal & Victory:** `goal`, `goal_medal_count`, `goal_part_count`
* **Locations:** `shuffle_medal_pickups`, `shuffle_chests_and_pickups`, `shuffle_npc_gifts`,
  `shuffle_boss_rewards`, `shuffle_minigame_prizes`, `shopsanity`, `trainer_battles`, `include_missable_locations`
* **Item Pool:** `part_weight`, `medal_weight`, `money_weight`, `include_version_exclusives`, `battle_logic`
* **Traps:** `trap_percentage`, `trap_weights`, `trap_strength`
* **Quality of Life:** `death_link`, `receive_item_messages`
* **Advanced:** `allow_unverified_build`
* Core options: `local_items`, `non_local_items`, `exclude_locations`, `priority_locations`, `item_links`,
  `plando_items`, `start_inventory`, `start_hints`, plus WebHost presets.

### Roadmap (designed for, not implemented)
Starting medabot choice, enemy medal-level scaling and bot shuffling (the battle table layout is documented), area-pass
shuffle via map-transition hooks, collection-milestone checks.

## 6. Architecture

```
worlds/medabots_rpg/
  data/*.json         all game knowledge, with stable IDs and a verification status
  data_loader.py      the only reader of data/; typed immutable objects and validation
  options.py          YAML options and WebHost presets
  items.py            item creation and item pool construction
  locations.py        location selection by options
  regions.py          area regions and entrances
  rules.py            JSON rule expressions -> rule builder
  traps.py            trap definitions
  rom_scripts.py      event-script parser shared by the patcher and the analysis tool
  rom.py              ROM identification, the patch container and the seed identity block
  client.py           BizHawk client
  __init__.py         the World class tying everything together
tools/                developer tools (not shipped): analyze_rom.py, lua/dump_ram.lua, dev.sh
```

Updating the world for new findings means running the analysis tool, reviewing the JSON diff, and bumping
`world_version`.

## 7. Connections: `ws://` and `wss://`

The client runs on Archipelago's `CommonClient.server_loop`, which already accepts a bare `host:port` (tried as `ws://`
first and retried as `wss://` when the server speaks TLS), an explicit `ws://` or `wss://` address (certificates are
verified against the `certifi` bundle) and `archipelago://` links. The project does not re-implement any of that; its
tests connect the client context to a local `ws://` server and a local `wss://` server to protect the behaviour across
Archipelago updates.

## 8. Release process

Semantic versioning with a leading `v` tag (`v0.1.0`). Pushing a tag that equals `v<world_version>` runs
`.github/workflows/release.yml`, which builds the `.apworld`, checks the version, extracts the matching changelog
section and creates a GitHub release (a pre-release while the major version is 0).
