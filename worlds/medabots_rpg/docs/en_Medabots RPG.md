# Medabots RPG

> **Pre-release.** This version of the world has not yet been verified against a real ROM, so seeds cannot be generated
> without opting in (see [Status](#status)). Everything below describes what the world is designed to do.

## Where is the options page?

You can read through all the options and generate a YAML [here](../player-options).

## What does randomization do to this game?

*Medabots: Metabee Version* and *Rokusho Version* are turn-based RPGs about a boy, his Medabot and the Robattles that
take them from Riverview to Medabot Island and Medaropolis. This randomizer shuffles the **rewards** of the game:
medals, medaparts and money are removed from their usual places and become checks that can hold items for any player in
the multiworld. The story, its order and its cutscenes are left exactly as they are.

## What are the goals?

* **Story Complete** (default): finish the story by completing the last area.
* **Collect Medals** or **Collect Medaparts**: receive a chosen number of different medals or medaparts.

## What items and locations get randomized?

**Items** that can be received:

* **Medaparts**: any of the 480 heads, arms and legs, for example `Head: Psycho Missile (Noctobat)`.
* **Medals**: any of the medals, for example `Medal: Kabuto`.
* **Money pouches**: small, medium and large piles of money. These are the filler of the game.
* **Traps**, if you enable them (see below).

**Locations** (each category can be switched on or off in the options): medal pickups, chests and ground pickups,
gifts from characters, boss Robattles, mini-game prizes, shop purchases and trainer Robattles.

## What do the logic options do?

With **Battle Logic** on, later areas expect you to have collected some medaparts first, so you are never sent into a
fight with a bare Medabot and nothing to improve it with. *Relaxed* asks for a small share of all medaparts in the
pool, *Standard* for a larger one. The requirement for an area is always capped by the number of checks in the earlier
areas, so it can never make a seed impossible. The spoiler log lists the numbers.

## What are traps?

Traps are filler items with a short, harmless sting. They are always temporary and never take away parts or medals:

| Trap | Effect |
|---|---|
| Money Drain | You lose a share of your money (never below zero). |
| Rusty Armor | Your Medabot's armor is reduced for the next Robattle only. |
| Medal Nap | Your medal's special ability is disabled for the next Robattle. |
| Ambush | A random Robattle is triggered. |

Traps only take effect while you are walking around freely, never in the middle of a menu, a cutscene or a battle you
did not choose, and a trap that cannot be applied yet waits instead of being lost. You choose how many there are,
which kinds, and how harsh they are.

## What happens when I receive an item?

Received medaparts and medals are added to your collection straight away, and a short message appears on screen in
BizHawk. If you are in a menu, a cutscene or a battle, the item waits until you are back in the overworld. Items are
never lost: loading an older save simply gives you everything again.

## Which game versions are supported?

All four English releases: **Metabee Version** and **Rokusho Version**, each in the USA and Europe editions. Japanese
ROMs and *Medabots AX* are not supported. Parts and medals that only exist in the other version are left out of the
item pool unless you enable **Include Version-Exclusive Items**.

## Status

Item names and IDs come from documented game tables, but the exact list of check locations and the memory addresses the
client reads have not been confirmed on a real ROM yet. Until they are, generating a seed requires
`allow_unverified_build: true`, and the client and patcher warn you. Progress is tracked in the
[project repository](https://github.com/NiklaskoDev/MedabotsRPG_APWorld).
