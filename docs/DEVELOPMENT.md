# Development guide

## Getting started

```bash
tools/dev.sh setup    # clone Archipelago 0.6.8 into .ap-core and create .venv (needs git, Python 3.11 to 3.13)
tools/dev.sh test     # copy the world into Archipelago and run the world's and the tools' tests
tools/dev.sh lint     # ruff
tools/dev.sh build    # dist/medabots_rpg.apworld, built by Archipelago's own packager
tools/dev.sh run tools/analyze_rom.py rom.gba   # run a developer tool with the world importable
```

`AP_REF=main tools/dev.sh test` tests against Archipelago's development branch. CI runs both and treats `main` as a
non-blocking early warning for upcoming Archipelago changes.

## Layout

```
worlds/medabots_rpg/     the APWorld (the folder name must stay lower case and equal to the .apworld name)
  data/*.json            all game knowledge, with permanent IDs and a verification status
  data_loader.py         the only reader of data/; immutable typed objects and validation (no Archipelago imports)
  options.py             YAML options, groups and WebHost presets
  items.py  locations.py  regions.py  rules.py
                         generation: item pool, location selection, region graph, logic
  rom_scripts.py         event-script parser (no Archipelago imports)
  rom_info.py            ROM identification (no Archipelago imports)
  rom.py                 the .apmedabots patch container and the seed identity block
  effects.py             the client's game logic: detection, delivery, traps (no BizHawk, no network)
  client.py              the BizHawk client: plumbing around effects.py
  __init__.py            the World class
  docs/                  the game page and setup guide shown on the WebHost
  test/                  tests
tools/                   developer tools, not shipped: dev.sh, analyze_rom.py, ramdiff.py, lua/, release_notes.py
docs/                    DESIGN.md, CALIBRATION.md and this file
```

The modules without Archipelago imports can be used by the tools without installing Archipelago's dependencies. Keep
them that way.

## Rules for the data files

* **IDs are permanent.** An item or location ID is stored in every multiworld and save that ever used it. Never change
  or reuse one; only add new ones. A test pins a sample of them, and the loader rejects duplicates.
* **Names are part of the user interface.** Item names are `Slot: Part (Bot)`, medals `Medal: Name`, locations
  `Area - Place Reward`. They appear in hints, trackers and logs; keep them short and consistent.
* **Facts, not guesses.** `game_tables.json` and `rom_versions.json` hold documented facts only. Anything inferred is a
  location with `status: "candidate"` or a `null` entry in `memory_map.json`. Nothing may pretend to be verified.
* **Edit data, not code.** New locations, a different area order or a changed logic threshold are JSON edits. The
  loader validates every file when the world is imported and names the problem.

## Adding a location

Add a row to `data/locations.json` with the next free ID, a `map` from the documented map table, a `category` and
`"status": "candidate"`. Its area comes from the map. Run the tests. To make it playable, follow
[CALIBRATION.md](CALIBRATION.md#step-2-verify-the-locations).

## Adding an option

1. Add the option class to `options.py` with a `display_name` and a docstring written for players (it becomes the YAML
   comment and the WebHost description, rendered as reStructuredText), add it to `MedabotsOptions` and to exactly one
   group in `OPTION_GROUPS`.
2. Use it where it belongs (`locations.py`, `items.py`, `regions.py`, …) and add it to `fill_slot_data` if the client
   needs it.
3. Document it in the game page. Tests check documentation, grouping and presets for you.

## Writing tests

Tests run with Archipelago's `unittest`-based suite inside `worlds/medabots_rpg/test/`. `test/support.py` provides a
synthetic *verified* data set, a synthetic ROM and a fake BizHawk memory, so everything that needs verified data can be
tested without a real ROM. Prefer testing `effects.py` and the data layer directly; they have no external dependencies.

## Releasing

Versions follow [Semantic Versioning](https://semver.org/). The version lives in exactly one place,
`worlds/medabots_rpg/archipelago.json` (`world_version`, always `major.minor.patch`). Versions below `1.0.0` are
published as GitHub pre-releases.

1. Move the `[Unreleased]` entries of `CHANGELOG.md` under a new `## [x.y.z] - YYYY-MM-DD` heading.
2. Set `world_version` to `x.y.z`.
3. Commit, then tag exactly `vx.y.z` (a release candidate may carry a suffix, `vx.y.z-rc.1`) and push the tag.

The `Release` workflow then checks that the tag equals the world version, runs the linter and the tests, builds
`medabots_rpg.apworld` with Archipelago's packager, writes `SHA256SUMS.txt`, takes the release notes from the
changelog and creates the GitHub release (marked as a pre-release while the major version is 0 or the tag has a
suffix). Raise `minimum_ap_version` in `archipelago.json` only when you deliberately start using something newer.

## Updating for a new Archipelago version

When the canary job (Archipelago `main`) fails, read the failure, fix the world so it works with both versions where
possible (a `try`/`except` around a moved import) and keep `minimum_ap_version` unchanged. Raise it only if supporting the
old version is not worth the trouble.
