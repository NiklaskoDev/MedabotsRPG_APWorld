# Medabots RPG for Archipelago

An [Archipelago](https://archipelago.gg) multiworld randomizer world for **Medabots: Metabee Version / Rokusho
Version** on the Game Boy Advance.

> **Status: pre-release (`0.x`).** Generation, options, logic, the patcher and the BizHawk client are implemented and
> tested, but the parts that depend on the game's memory layout have **not yet been verified against a real ROM**. By
> default the generator refuses to build a seed from unverified data. See [Status](#status).

## Status

| Area | State |
|---|---|
| YAML options, item pool, logic, traps, WebHost page | Implemented and tested |
| Item and location data | Item names and IDs come from documented ROM tables. Locations are *candidates* inferred from map names |
| Patcher (`.apmedabots`) | Implemented; refuses to write unless the target memory is verified blank |
| BizHawk client | Implemented; works against a fake BizHawk in tests, **memory addresses unverified** |
| In-game verification | Pending, see [docs/CALIBRATION.md](docs/CALIBRATION.md) |

## Installing

1. Download `medabots_rpg.apworld` from the [releases page](../../releases).
2. Double-click it, or place it in the `custom_worlds` folder of your Archipelago installation.
3. Follow the setup guide in the game's page on the Archipelago WebHost (source:
   [`worlds/medabots_rpg/docs/setup_en.md`](worlds/medabots_rpg/docs/setup_en.md)).

You need your own legally obtained English *Medabots: Metabee* or *Rokusho* ROM, and BizHawk 2.9 or newer.

## Documentation

* [Design](docs/DESIGN.md): what the randomizer does and how seeds are kept beatable
* [Development guide](docs/DEVELOPMENT.md): working on the code, updating data, releasing
* [Calibration](docs/CALIBRATION.md): turning unverified data into verified data using a real ROM

## Development

```bash
tools/dev.sh test     # clone Archipelago 0.6.8, copy the world in, run the tests
tools/dev.sh lint     # ruff
tools/dev.sh build    # dist/medabots_rpg.apworld
```

## Credits and licence

MIT licensed, see [LICENSE](LICENSE). Documented game facts come from
[STulling/Medabots-Randomizer](https://github.com/STulling/Medabots-Randomizer) (MIT), see [NOTICE](NOTICE).
Medabots and Medarot are trademarks of their respective owners; this is an unofficial fan project and ships no game
data.
