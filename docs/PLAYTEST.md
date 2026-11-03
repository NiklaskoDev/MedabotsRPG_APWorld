# Play-test plan (Step 5 of the calibration)

[CALIBRATION.md](CALIBRATION.md#step-5-play-test-a-multiworld) asks for a play-test of a multiworld before `1.0.0`.
This is the plan for it. Calibration ([CALIBRATION_NOTES.md](CALIBRATION_NOTES.md)) showed that every address and every
verified location works *when triggered from a savestate by a Lua script*. This plan shows that the whole thing works
for a person playing the game, from the first minute to the ending, over a real server.

Status: **plan, not yet run.** Copy this file (or its tables) into an issue or a `PLAYTEST_RESULTS.md` outside the
repository and fill in the *Result* columns there; do not commit savestates, saves or ROMs.

## What the play-test has to settle

The automated suite already covers the logic with a fake BizHawk: delivery rules, guards, idempotence, traps, goals,
`ws://` and `wss://` loopback, patching, generation. A person with a real game is needed for what a fake cannot show.
In order of how much each can still go wrong:

1. **The real ending.** Event 147 (the goal) was seen only on a copy with the text blanked out, script 1902 (Fort Fiyun
   courtyard) was only read, and the Mega-Emperor finale was never played through. Nothing else proves that the goal
   fires at the end of a real game, and not before it.
2. **Rewards removed in a real run.** Squidguts was calibrated with its dialogue and battles blanked, the arcade win was
   forced through the result byte, and every location was started by a warp. Whether each one can be reached in normal
   play, at the chapter `regions.json` says, and still behaves, is untested.
3. **Delivery in every state a player really reaches**: shops, mini-games, scene fades, the title screen, both kinds of
   Robattle. The safe-state rule is two bytes; the play-test is where its blind spots show up.
4. **Money and traps are counted, not state-based.** Loading an older save keeps parts and medals (they are re-asserted)
   but loses money received since, and a trap is never re-applied. This is by design; confirm it is acceptable.
5. **A forced encounter that never fires.** Ambush writes 32 to the encounter counter. When it is received where there
   are no random encounters, the trap expires after 5 minutes *without clearing the counter*. Observe what happens next.
6. **An item that cannot be written blocks the queue behind it** (nothing is lost, but nothing after it arrives either).
   The medal case is the likeliest cause.
7. **Only four location categories have checks:** medals (1), chests and pickups (7), boss rewards (1), mini-game prizes
   (2). Gifts and trainer Robattles have none and the nine shop rows are `absent`. Test what exists; do not expect more.

Not tested, because it does not exist yet: Rusty Armor and Medal Nap (seeds drop them), DeathLink, enemy shuffling,
starting-Medabot choice.

## Findings so far

| Finding | Status |
|---|---|
| **P0.** Choosing New Game fills the game's RAM, the event flags included, with `0xFF`; the client read that as all 11 checks made and the story complete (Metabee USA and Rokusho USA; the Europe versions show the same RAM). | Fixed in code with tests: flags are read only in the field and never from an all-`0xFF` table. Retest **SV-8** and **SV-9** on all four versions. |
| **P1.** After connecting a ROM to another seed's server once, the client stayed stopped on the right server too, until it was restarted. | Fixed in code with tests: a stop belongs to one connection. Retest **CN-8**. |

Seeds and patches made before the fix are refused by the fixed client (the data hash changed); generate and patch again.

## Setup

**Software.** Archipelago 0.6.8, BizHawk 2.9.1 (the version calibration used), this repository's
`medabots_rpg.apworld` (from `tools/dev.sh build` or a release candidate). In EmuHawk turn on *Config > Customize > Run
in background*. Keep a BizHawk RAM Watch with these entries (domain *System Bus*) open; they explain most surprises:

| Address | Size | Meaning |
|---|---|---|
| `0x03002B70` | 4 bytes | money, in cents (`1000` is $10.00; the wallet holds `99999`) |
| `0x03006468` | 1 byte | event-script engine: 0 = idle (required for delivery) |
| `0x0300178C` | 1 byte | main mode: 1 = field (required for delivery), 0 = Robattle or B menu, 2 = scene change, 3 = title |
| `0x0300640B` | 1 byte | random-encounter step counter (Ambush writes 32) |

**ROMs.** Your own dumps of Metabee USA (main run) and Rokusho Europe (second slot), plus Metabee Europe and Rokusho USA
for the quick checks. `.gba`, `.sav` and `.ss*` are already in `.gitignore`.

**Two players, one machine.** One slot is played; the other is stood in for by the server console, which is faster and
repeatable. Useful commands: `/send Bee "Medal: Kabuto"`, `/send_multiple 20 Bee "Money Pouch (Small)"`,
`/send_location Roku "<location name>"`, `/release Roku`, `/collect Bee`. Item names are the ones on the game page, for
example `Head: Psycho Missile (Noctobat)`, `Money Pouch (Large)`, `Money Drain Trap`, `Ambush Trap`. A second EmuHawk
can run next to the first (the connector takes the next free port in 43055-43059); if pairing two clients with two
emulators gets awkward, play the slots one after the other, which also exercises reconnecting.

**Save hygiene.** Use two kinds of save on purpose. *In-game saves* (the game's own save, kept in the `.sav`) test
persistence. *BizHawk savestates* are for getting back quickly to a place or state. Make a savestate before every
location, before every boss and at each new area.

**Seeds.** Generate all three with the default YAML structure of the options page and these overrides.

Traps replace a share of the *filler* (money pouches), and a seed of 9 to 11 locations per slot has only about two filler
items, so these seeds hold none or one trap. Every trap case below therefore injects traps with `/send`; the seeds only
decide the strength. Real traps in a real seed are covered by the first hour of the playthrough, if any come up.

Seed A, two slots (`Bee` plays Metabee USA, `Roku` plays Rokusho Europe), 11 locations each. The trap weights stay at
their defaults on purpose: the seed must come out without Rusty Armor and Medal Nap.

```yaml
name: Bee            # and a second file with name: Roku
game: Medabots RPG
Medabots RPG:
  goal: story_complete
  shuffle_minigame_prizes: true
  battle_logic: standard
  trap_percentage: 30
  trap_strength: normal
  receive_item_messages: all
```

Seed B, one slot (`Collector`), quick goal and quiet messages:

```yaml
name: Collector
game: Medabots RPG
Medabots RPG:
  goal: collect_medals
  goal_medal_count: 2
  shuffle_minigame_prizes: true
  trap_percentage: 0
  receive_item_messages: progression_only
```

Seed C, one slot (`Parts`), quick goal, no messages, harsh traps:

```yaml
name: Parts
game: Medabots RPG
Medabots RPG:
  goal: collect_medaparts
  goal_part_count: 3
  trap_percentage: 40
  trap_strength: harsh
  receive_item_messages: none
```

Each case has a priority: **P0** blocks `1.0.0`, **P1** should pass or get a recorded decision, **P2** is worth doing
if time allows.

## How the client behaves (to tell a bug from the design)

* An item is delivered only while the event-script engine is idle **and** the main mode is the field, and never while a
  Robattle is running. Up to 4 items are delivered per tick, in order, each exactly once.
* Parts and medals are *ensured to be owned*, silently re-asserted every 5 seconds. Owning a part twice does not raise
  its count. A medal is written as the record the game's own routine would build: its own name, level half way between
  the best and the fourth-best medal in the case.
* Money pouches are $10, $50 and $200 and are clamped at $999.99 (the excess is lost). Money Drain takes 10, 25 or 50
  percent (mild, normal, harsh), never below zero.
* Ambush forces a Robattle on the next step in an area with random encounters, once (mild and normal) or twice in a row
  (harsh). Every trap is lifted after 5 minutes at the latest.
* How many received items were handled is kept on the server (key `medabots_rpg_<team>_<slot>_applied`), so a restart of
  the client, BizHawk or the server does not deliver anything again.
* On-screen messages are `Found <item>` for items from your own slot and `Received <item> from <player>` otherwise.
* A check is reported when its event flag appears in game memory, so progress made offline is sent when the client
  connects.

## 1. Before anything is run (no emulator)

| ID | Pri | Case | Expected | Result |
|---|---|---|---|---|
| PF-1 | P0 | `tools/dev.sh lint` and `tools/dev.sh test` | Both pass. | |
| PF-2 | P0 | Build the apworld, install it into a clean Archipelago 0.6.8 (`custom_worlds`), open the WebHost or launcher options page and the game page. | The world loads, the options page shows six groups, the game page and setup guide render. | |
| PF-3 | P0 | Generate from the unmodified default YAML (no `allow_unverified_build`). | Generates. 9 locations (11 with mini-game prizes). The spoiler lists no Rusty Armor or Medal Nap, even with the default trap weights. | |

## 2. Generating and patching

| ID | Pri | Case | Expected | Result |
|---|---|---|---|---|
| GP-1 | P0 | Generate Seed A. | One `.apmedabots` per slot, no warnings about unverified data. | |
| GP-2 | P0 | Patch Metabee USA for `Bee`, Rokusho Europe for `Roku`, then patch Metabee Europe and Rokusho USA once each. | A patched `.gba` for all four versions. | |
| GP-3 | P1 | `cmp -l original.gba patched.gba` for each version. | The differences are the 256-byte identity block at `0x7FF000` and the reward instructions of the active locations, nothing else. | |
| GP-4 | P1 | Patch an already patched ROM, a Japanese ROM, a ROM with one byte changed in the identity block. | Each refused with the message from the setup guide; no patched ROM is produced. | |
| GP-5 | P0 | Start a new game on each patched ROM and play about 10 minutes without a client. | Plays normally; no crash, no changed text or music. | |

## 3. Connecting

| ID | Pri | Case | Expected | Result |
|---|---|---|---|---|
| CN-1 | P0 | Enter `localhost:38281` (bare) in the client. | Connects; the slot name is not asked for. | |
| CN-2 | P1 | Enter `ws://localhost:38281`, then an `archipelago://Bee@localhost:38281` link. | Both connect. | |
| CN-3 | P0 | Host with `MultiServer --cert … --cert_key …` on a name with a certificate from a public authority and connect with `wss://name:port`. | Connects, encrypted, and play works as in the plain case. | |
| CN-4 | P1 | Same with a self-signed certificate. | Refused with "Failed to connect to the multiworld server"; the client does not ignore the certificate. | |
| CN-5 | P0 | Load the patched ROM, run `connector_bizhawk_generic.lua`. | The client names Medabots RPG and the correct slot; no unverified-build warning. | |
| CN-6 | P1 | Load the original, unpatched ROM. | "This is an unpatched Medabots ROM…" once, no spam, nothing written. | |
| CN-7 | P1 | Connect `Bee`'s ROM to a server hosting a different generation. | The client stops with the "different multiworld" message and delivers nothing. | |
| CN-8 | P0 | After CN-7, without restarting the client or BizHawk, disconnect and connect to the right server. | The client joins, resumes at once and says so in its log; open a chest and send an item: the check is sent and the item arrives. | |

## 4. Delivery in every state

Probe: `/send Bee "Money Pouch (Small)"` and watch the money address. In an unsafe state nothing may change and no message
may appear; after returning to free walking the money rises by exactly $10, once, with one message. Wait at least 10
seconds in each state before leaving it.

| ID | Pri | State | How | Expected | Result |
|---|---|---|---|---|---|
| DG-1 | P0 | Walking, town and dungeon | Walk around. | Delivered within a few seconds. | |
| DG-2 | P0 | Dialogue | Talk to anyone. | Waits, then arrives once. | |
| DG-3 | P0 | Chest or item pickup | Open a chest, stay in the text. | Waits, then arrives once. | |
| DG-4 | P0 | B menu, Medawatch, parts screen | Open them. | Waits, then arrives once. | |
| DG-5 | P0 | Cutscene | Any story scene. | Waits, then arrives once. | |
| DG-6 | P0 | Story (scripted) Robattle | Any boss fight. | Waits until the battle and its result screens are over. | |
| DG-7 | P0 | Random-encounter Robattle | Walk until one starts. | Waits until it is over. | |
| DG-8 | P0 | Shop | Enter a shop menu. | Waits, then arrives once. | |
| DG-9 | P0 | Title screen and file select | Soft reset (A+B+Start+Select), wait at the title, send the probe there. | Nothing is written at the title (a value written there would be wiped by loading the save); after loading the save and walking, it arrives once. | |
| DG-10 | P1 | Scene fade | Walk through a door repeatedly while sending. | Never arrives mid-fade; no glitch. | |
| DG-11 | P1 | Mini-games | Arcade game, Ninja Park hide and seek. | Waits, then arrives once. | |
| DG-12 | P1 | Save prompt and naming screens | Save the game; start a medal naming screen if one appears. | Waits, then arrives once. | |
| DG-13 | P0 | Queue while unsafe | In a Robattle send 10 different items (parts, a medal, pouches). | After the battle all 10 arrive, once each, in order. | |
| DG-14 | P1 | Burst | While walking `/send_multiple 20 Bee "Money Pouch (Small)"`. | Arrive a few per tick; wallet +$200 or clamped at $999.99; no crash. | |
| DG-15 | P2 | Wallet cap | Near $999.99 send a large pouch, then a part. | Wallet clamps; the part still arrives. | |
| DG-16 | P1 | Emulation paused | Pause BizHawk, send items, resume. | Arrive after resuming, once. | |

## 5. What the items do

| ID | Pri | Case | Expected | Result |
|---|---|---|---|---|
| IT-1 | P0 | Send one part per slot (head, right arm, left arm, legs). | Each is named correctly in the parts screen, can be equipped, and works in a Robattle. | |
| IT-2 | P2 | Send the same part again. | Still owned once; nothing breaks. (The game's own pickup would raise the count.) | |
| IT-3 | P0 | Send a medal the player does not own. | In the medal case under its own name with a plausible level and stats; can be put into a Medabot and used in a Robattle with the right name shown; survives an in-game save and reload. | |
| IT-4 | P0 | Send the same medal again, then several different ones. | No second copy; each new one sits at the level the rule gives. | |
| IT-5 | P0 | Send a small, medium and large pouch. | +$10, +$50, +$200 as the menu shows dollars and cents. | |
| IT-6 | P1 | Receive items on Seed A (all), Seed B (progression only), Seed C (none). | `Found …` for own items, `Received … from …` otherwise; Seed B only announces progression items; Seed C nothing. | |
| IT-7 | P2 | Generate once with `include_version_exclusives: true` and send a part that exists only in the other version. | Owned, equippable. | |

## 6. Saves and persistence

| ID | Pri | Case | Expected | Result |
|---|---|---|---|---|
| SV-1 | P0 | Receive parts, a medal and money, save in-game, close BizHawk, reopen, load the save, reconnect. | Everything is still there; money is not added again; no messages are repeated. | |
| SV-2 | P0 | Save in-game at S. Receive 3 parts, a medal and a pouch. Reload S. | Within about 10 seconds the parts and the medal are back, silently. The pouch is **not** added again (money since S is lost with the older save; record that this matches expectations). | |
| SV-3 | P1 | Same with a BizHawk savestate taken before the delivery. | Same result; no crash. | |
| SV-4 | P0 | Close and reopen the client mid-session. | Nothing is delivered twice. | |
| SV-5 | P1 | Stop and restart the server from its save file. | Checks and the delivery counter persist; no duplicates. | |
| SV-6 | P0 | Play with BizHawk open but the client closed: open a chest, receive nothing. Items are sent to you meanwhile. Start the client. | The check is sent once, the waiting items arrive once. | |
| SV-7 | P1 | Soft reset mid-session. | The client survives and keeps delivering. | |
| SV-8 | P0 | With the client connected and a server that has not seen any checks, choose **New Game** from the title menu, once with no save file and once with one, and play the first ten minutes. Watch the server and the client log while you are on the title menu, at the confirmation prompt and on the first screens. Repeat on all four versions. | No check and no goal are sent at any point. The first real check (once you reach one) is still sent. | |
| SV-9 | P0 | **Continue** an existing save with the client connected, then go back to the title and choose New Game. | Continue behaves as before: checks already made are not sent twice. The New Game afterwards sends nothing, and checks made in the old game are not undone. | |

## 7. Locations

Play each one **in the natural course of the story**, not from a warp, with the client connected. For every location
check: the check is sent exactly once and names the right location; the vanilla reward is not received (and write down
what the game's text says, since only the reward instruction is removed, not the dialogue); the story continues; the
check is still marked after saving and reloading; and the place became available at the chapter `regions.json` implies.
Make a savestate right before each.

| ID | Pri | Location | What to do | Specific points | Result |
|---|---|---|---|---|---|
| LC-1 | P0 | 20001 Research Center, Nae's medal room | Take a medal (one of six). | Test at least two of the six choices; every one sends the check and none gives a medal. | |
| LC-2 | P0 | 20002 Odoro Marsh, broken parts room | Open the salvage. | No item received. | |
| LC-3 | P0 | 20003 Odoro Marsh, Squidguts | Fight him for real. | Calibrated with its dialogue and battles blanked, so this is the first real run: no parts or medal, flag set, story continues. | |
| LC-4 | P0 | 20004 Medabot Island, arcade | Play the $1 game until you win (play again after a loss if the game lets you). | The check is for a win only: a loss should send nothing (record it if it does). The win sends it once and the prize item is not received. The win was only forced before. | |
| LC-5 | P0 | 20006 Surprise site, right locker | Do the part trade. | The trade's reward is not received; record whether the part you hand in is taken or kept. | |
| LC-6 | P0 | 20008 Rubberobo base, medal room chest | Open it. | No money received. | |
| LC-7 | P0 | 20009 Fort Fiyun, chest 1 | Open it. | The Medabot it would give is not received. | |
| LC-8 | P0 | 20010-20012 Fort Fiyun, chests 2 to 4 | Open each. | One check each, no money. | |
| LC-9 | P0 | 20013 Ninja Park, hide and seek | Finish the tour. | Sent once whatever the result; neither money nor Repair Spring received. | |
| LC-10 | P1 | The absent rows | Look at the Rosewood medal-room display, the left surprise-site locker, buy something in each shop. | Nothing is sent and nothing odd happens. | |
| LC-11 | P1 | Items from checks | Each check holds an item for someone; find items for `Bee` itself and for `Roku`. | Own items arrive as `Found …`; items for `Roku` do not appear in `Bee`'s game. | |

## 8. Traps

Inject with `/send Bee "<name>"`. Strength comes from the seed: normal on Seed A, harsh on Seed C.

| ID | Pri | Case | Expected | Result |
|---|---|---|---|---|
| TR-1 | P0 | Money Drain on Seed A with $100. | Wallet becomes $75. Repeating at $0 leaves $0. | |
| TR-2 | P1 | Money Drain on Seed C (harsh) with $100, and at the edge of a safe state (in a menu). | $50; in the menu it waits and then applies once. | |
| TR-3 | P0 | Ambush on Seed A while walking in an area with random encounters. | A Robattle starts on the next step; once it is over, encounters return to the normal rate. | |
| TR-4 | P1 | Ambush on Seed C. | Two Robattles in a row, then normal. | |
| TR-5 | P1 | Ambush in a town or indoors, then keep walking there for more than 5 minutes, then enter an encounter area. | Record exactly what happens. The counter keeps its armed value after the trap expires; decide whether an ambush an hour later is acceptable or the trap should clear the counter. | |
| TR-6 | P1 | Ambush on the way to a story battle or during a long walking scene. | Record whether it can fire at a bad moment or break a scene. | |
| TR-7 | P1 | `/send Bee "Rusty Armor Trap"` and `/send Bee "Medal Nap Trap"`, then a pouch. | No effect in game, a message at most, and the pouch still arrives (these traps are not in seeds but must not jam the queue). | |
| TR-8 | P0 | Send any trap during DG-4 to DG-8 states. | It waits and applies once when safe. | |

## 9. Goals

| ID | Pri | Case | Expected | Result |
|---|---|---|---|---|
| GL-1 | P0 | Play Seed A from the start to the end of the story with the client connected, checking the server's status after each chapter. | Not complete at any point before the ending. After the ending movie and staff roll, once Ikki is back home, the slot becomes *Goal Complete* once. Note which ending script ran (2070 or 2073 on the chapter-8 docks, or 1902 in the Fort Fiyun courtyard). | |
| GL-2 | P0 | Reload before and after the ending, play on. | The goal is not sent a second time; items and checks keep working. | |
| GL-3 | P0 | Seed B: send two different medals, in a menu. | Completes on the second different medal even in the menu; the same medal twice does not count. | |
| GL-4 | P1 | Seed C: send three different parts. | Completes on the third. | |
| GL-5 | P1 | A quick ending check, for repeats only: from a savestate shortly before the ending, play just the ending. | Same as GL-1. Not a substitute for GL-1. | |

## 10. Other versions

| ID | Pri | Case | Expected | Result |
|---|---|---|---|---|
| CV-1 | P0 | On Rokusho Europe (`Roku`): CN-5, DG-1, DG-4, DG-7, IT-1, IT-3, IT-5, TR-1, TR-3, and the first two locations you reach. | As on Metabee USA. | |
| CV-2 | P1 | On Metabee Europe and Rokusho USA: patch, boot, connect, IT-1, IT-3, IT-5 and one location. | As on Metabee USA. | |

## 11. Robustness

| ID | Pri | Case | Expected | Result |
|---|---|---|---|---|
| NG-1 | P0 | Play at least an hour connected while a `/send` of a part, medal, pouch or trap is made about once a minute, then save, close and load the save. | No crash, softlock or corrupted save; the save loads and holds the items. | |
| NG-2 | P1 | Close BizHawk without warning, reopen, reload the Lua script. | The client reconnects on its own; nothing delivered twice. | |
| NG-3 | P1 | Cut the server for a few minutes while you open a chest, then restore it. | The client reconnects and sends the check; waiting items arrive. | |
| NG-4 | P1 | Generate a YAML with every location category off except `shuffle_npc_gifts`. | Generation stops with "the selected options leave no locations to randomize…". | |
| NG-5 | P2 | Turn BizHawk's fast-forward on during deliveries. | Items still arrive once. | |

## Running it

1. **Preflight and setup:** PF, GP, CN, then DG, IT, TR-1 to TR-4, TR-7 and SV from savestates. This is fast and finds
   most delivery bugs before anything long is started.
2. **The playthrough:** start Seed A on Metabee USA and play the whole story connected, `Roku` stood in for by the
   server. This one run covers LC, GL-1 and GL-2, TR-5 and TR-6, and the natural cases of SV-1, SV-2 and SV-6 and of
   DG-2 to DG-8. Make an in-game save at the start of every area, keep a log by chapter, and send a trickle of items.
   Run NG-1 inside it.
3. **Other versions:** CV on Rokusho Europe (with the second slot), then the quick checks on the other two ROMs.
4. **Retest** whatever was fixed, and every P0 that touched the fixed code.

## Recording and reporting

For every failure, note the ROM version, the test ID, the steps, expected and actual, the client log around it, the
values of the four RAM-watch addresses and, if it reproduces, a savestate (kept out of the repository). Use one issue per
defect and link it from the *Result* cell.

## Exit criteria

The play-test is passed when:

* every P0 case passes on Metabee USA, and the P0 cases of CV-1 pass on Rokusho Europe;
* every P1 case has either passed or has an issue with a recorded decision (fix, document, or accept);
* deviations that are accepted by design (money lost on loading an older save, the cap on the wallet, what the game's
  text says after a removed reward, TR-5's outcome) are written into [CALIBRATION_NOTES.md](CALIBRATION_NOTES.md) and,
  where a player would notice, the game page.

Then continue with [Step 6](CALIBRATION.md#step-6-release): version `1.0.0`, the changelog, and removing the pre-release
notices from the README, the game page and the troubleshooting table of the setup guide.
