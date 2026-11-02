# Medabots RPG for Archipelago

[![CI](https://github.com/NiklaskoDev/MedabotsRPG_APWorld/actions/workflows/ci.yml/badge.svg)](https://github.com/NiklaskoDev/MedabotsRPG_APWorld/actions/workflows/ci.yml)

An [Archipelago](https://archipelago.gg) multiworld randomizer world for **Medabots: Metabee Version / Rokusho
Version** on the Game Boy Advance. Medals, medaparts and money become checks that can hold items for any player in the
multiworld, while the story itself stays untouched.

> **Status: pre-release (`0.x`).** Generation, options, logic, the patcher and the BizHawk client are implemented and
> tested, but the parts that depend on the game's memory layout have **not yet been verified against a real ROM**. By
> default the generator refuses to build a seed from unverified data. See [Status](#status).

## Features

* **Goals:** complete the story, or collect a number of medals or medaparts.
* **480 medaparts and 30 medals** as items, money pouches as filler, and four temporary, harmless traps.
* **Configurable:** location categories, item pool weights, battle logic, trap amount, kinds and strength, on-screen
  messages, plus WebHost presets (Casual, Standard, Chaos).
* **Built to avoid bricked seeds:** gates can never exceed what earlier areas can hold, missable spots only hold filler,
  delivery waits for a safe moment and repairs itself after loading an older save, and a ROM from another seed is
  refused. See [docs/DESIGN.md](docs/DESIGN.md).
* **Secure and plain connections:** `ws://` and `wss://` servers, bare `host:port` and `archipelago://` links all work.
* **Four ROMs:** Metabee and Rokusho, USA and Europe.

## Status

| Area | State |
|---|---|
| YAML options, item pool, logic, traps, WebHost page | Implemented and tested |
| Item names and IDs | From documented ROM tables (480 parts, 30 medals) |
| Check locations | *Candidates* inferred from documented map names, not yet verified |
| Patcher (`.apmedabots`) | Implemented; refuses unsupported, patched or mismatched ROMs |
| BizHawk client | Implemented and tested against a fake BizHawk; **memory addresses unverified** |
| In-game verification | Pending, see [docs/CALIBRATION.md](docs/CALIBRATION.md) |

## Installing

1. Download `medabots_rpg.apworld` from the [releases page](../../releases).
2. Double-click it, or place it in the `custom_worlds` folder of your Archipelago installation (0.6.8 or later).
3. Follow the setup guide, [`worlds/medabots_rpg/docs/setup_en.md`](worlds/medabots_rpg/docs/setup_en.md), which is also
   shown on the game's page of the Archipelago WebHost.

You need your own legally obtained English *Medabots: Metabee* or *Rokusho* ROM, and BizHawk 2.9 or newer.

## Documentation

* [Design](docs/DESIGN.md): what the randomizer does and how seeds are kept beatable
* [Development guide](docs/DEVELOPMENT.md): working on the code, adding data and options, releasing
* [Calibration](docs/CALIBRATION.md): turning unverified data into verified data using a real ROM
* [Changelog](CHANGELOG.md)

## Development

```bash
tools/dev.sh test     # clone Archipelago 0.6.8, copy the world in, run all tests
tools/dev.sh lint     # ruff
tools/dev.sh build    # dist/medabots_rpg.apworld
tools/dev.sh run tools/analyze_rom.py path/to/rom.gba   # inspect a ROM
```

Releases are tagged `vX.Y.Z`. To release, bump `world_version` and the changelog, then run **Actions > Tag a release**
on GitHub: it verifies everything, pushes the tag and publishes the release with the built `.apworld`. See
[Releasing](docs/DEVELOPMENT.md#releasing).

## Credits and licence

MIT licensed, see [LICENSE](LICENSE). Documented game facts come from
[STulling/Medabots-Randomizer](https://github.com/STulling/Medabots-Randomizer) (MIT), see [NOTICE](NOTICE).
Medabots and Medarot are trademarks of their respective owners; this is an unofficial fan project and ships no game
data.
