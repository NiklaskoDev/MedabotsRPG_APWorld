# Play-test results (Step 5)

## Third run: story play with a walkthrough (`b518f89`)

Walkthrough used: Kenshin Xtreme's Medabots RPG FAQ (GBA rev 3.50), a Portuguese translation hosted as the README of
[a Wokwi project](https://wokwi.com/projects/375774638861240321). Its section 9 runs from the first scene to the credits.

Build: `b518f89` built locally. `tools/dev.sh` now works under Windows Git Bash: lint clean, world tests (298 collected)
and 51 tool tests pass. Generation warns that part genders are not in the data yet (expected until `analyze_rom.py`
fills `bot_genders`). Frozen Archipelago 0.6.8, BizHawk 2.9.1, fresh Seed A, Metabee USA, continued from the state
where Ikki has just bought the Tinpet. Fights were won with a cheat, by agreement (enemy armor 0, enemy leg stats 0,
own armor full, own accuracy, power and speed maxed); random encounters were switched off while walking, except for
the encounter tests.

| ID | Result | Notes |
|---|---|---|
| LC-1 | **Pass, now in natural play** | The story itself set the six pedestals to "offer" (chapter 2, after Nae), the shortcut of the second run was not needed. Check sent once; the item (a Money Drain) applied: $60.20 → $45.15. |
| DG-3 | **Pass** | Treasure-island chest on Mt. Odori: text held open, script engine 1, nothing delivered; arrived once afterwards. |
| DG-7 | **Pass** | Real random Robattle (schoolyard, script engine idle, main mode 0): nothing delivered; +$10 and a medal arrived once afterwards. |
| TR-3 | **Pass** | Ambush in the schoolyard: counter 32, Robattle on the next step, counter back to normal after it. |
| TR-5 | **Pass (new behavior)** | Received in town: counter stays 0, encounter flag `0x03006409` 0. On entering the schoolyard (flag 1) it armed and fired once. |
| DG-2 | **New gap, low severity** | Simple "inspect" text boxes ("It's a closed tool box.") leave the script engine at 0 in main mode 1, so the client treats them as free walking: a pouch landed (+$10, message) with the box open. No harm seen. NPC dialogue and chests do set the engine and are held back. |
| Chapter progress | Reached chapter 2 | Tinpet → Dad and the first medal → Erika → school trio → Koji → factory → second Tinpet → medal room → Mt. Odori (maps 33-35) → Select Corps at the Troop house. One location check and no goal were sent the whole way (1 `sent` line, 0 `completed` lines on the server). |

### Where it stopped

Mt. Odori, left side (map 34), at the step the guide words as "cross the bridge and read the sign in front of it". The
sign there is plain text ("Odoro Marsh Water Taxi / $1 a ride") and starts no scene. The ROM's scripts show the river
scene hanging on a separate value chain (objects 393, 397, 399; event 399 is still 0), so which object starts it was
not found. Further guessing would have been brute force. Savestate `stop_water_taxi` is kept for picking this up.

### Not retested on this build

SV-8/SV-9/CN-8 were not run again on `b518f89`; that commit does not touch check detection or reconnect handling.

### Unverified risk from reading the values

The client's `in_battle` is main mode 0 with sub-scene 3, 5, 6, 7, 8 or 9. The Medawatch Medabots screen read sub-scene
3 and the Medaparts screen 5, so those menus count as battles. Leaving them could look like "a battle ended" and use up
a harsh Ambush's remaining battle. Not tested.

### Still open

DG-8, DG-11, LC-2 to LC-11, TR-2, TR-4, TR-6, GL-1/GL-2/GL-5, NG-1, CN-3. All but CN-3 need more of the story.

---

## Second run: retest of the fix (`147cb95`, tag `v0.1.0-rc2`)

Built locally from `147cb95` (the commit the `v0.1.0-rc2` pre-release points at; the release asset itself was not
downloaded). ruff clean, 283 world tests and 47 tool tests pass. Seed A regenerated and all four ROMs patched again.
Same frozen Archipelago 0.6.8 and BizHawk 2.9.1, same harness.

**Both defects are fixed.** No case regressed. With a real check now reachable, LC-1, the battle delivery cases and the
check halves of SV-6 and NG-3 pass as well.

| ID | Result | Notes |
|---|---|---|
| SV-8, no save | **Pass, all four versions** | Client connected at the title; 15 s on the `0xFF` New Game menu (about 6 minutes on Metabee Europe), New Game, intro, walking: no check and no goal sent on any version. |
| SV-8, with a save | Pass (Metabee USA) | With a save present, the New Game prompt keeps the save's RAM (no `0xFF`); Yes, intro, walking: nothing sent. Not repeated on the other three versions (my in-game-save helper failed on a first-ever save); the no-save case is the one that fills RAM with `0xFF`. |
| SV-9 | Pass (partial) | Continue, then soft reset and New Game over the save: nothing sent. The save held no check yet, so "checks already made are not sent twice" was covered by LC-1's save/reload instead. |
| CN-8 | **Pass** | Connected to another seed's server (stopped with the "different multiworld" message), then `/connect` to the right one without restarting anything: log says "Connected to a server again; checking the ROM against it afresh.", the item arrives, and (via LC-1) checks are sent. |
| LC-1 | **Pass** | See "How LC-1 and the battles were reached" below. Bat: "Should I take this Medal?" Yes → "Okay, that's the one!", the pedestal shows empty, **no medal received**, no "You got…" text. Flag 230 set, the check was sent **once**, and Bee's own item arrived: `Found Head: Sacrifice Head (Aquacrown)`. Second choice (Chameleon) from the same savestate: flag set, no medal, not sent again. In-game save, soft reset, Continue: flag still set, nothing re-sent. The room belongs to the Riverview region (chapter 0), as `regions.json` has it. |
| DG-6 | **Pass** | A trainer Robattle (script 63, battle `0x9B`): 15 s at "Get ready to Robattle" and the whole fight (several minutes): nothing written. |
| DG-13 | **Pass** | Ten mixed items sent during that Robattle: after the win all ten arrive once, in order (4 per tick); money $40.20 → $275.15 is exactly small, medium, drain −25%, large in that order. |
| IT-1 | **Pass for same-gender parts** | Received ANTENNA (Rokusho) is offered in the build screen, fitted to Metabee and usable in a Robattle ("ANTENNA — Support / Scout, 5/5"). See the gender finding below. |
| IT-3 | **Pass** | The client-written KABUTO record is fitted in the build screen, shown as "KABUTO" in battle, gains "SKILL UP!! SHOOT 11" and reaches level 1 from battle experience. |
| SV-6 | **Pass** | Medal taken with no client running; on start the client sent the check once and the item arrived once. |
| NG-3 | **Pass** | Server stopped with `/exit`, medal taken during the outage, server restarted from its `.apsave`: the client rejoined on its own, sent the check once, item arrived once. |
| DG-8 | Not run | The only shop reached (Riverview City Market, map 30) answers "Sorry. We're still preparing." at this point of the story. |

### New finding: opposite-gender parts cannot be fitted (design, P1 decision)

Ikki's Tinpet is male. The received *Sacrifice Head (Aquacrown)* is a female part (♀ in the Medaparts list) and is
never offered in the build screen, while the male *Antenna (Rokusho)* is. So part items of the other gender are useless
until the player owns a female Tinpet. The item pool and Battle Logic currently treat every part alike. Decide whether
to weight the pool toward the player's Tinpet gender, count only usable parts in Battle Logic, or document it on the
game page.

### Other observations in this run

* The TV show cutscene in Ikki's room runs in main mode 3 (the mode the notes list for the title screen). Delivery and
  detection are gated on mode 1, so nothing happens there, which is correct.
* Archipelago's core client re-sends every check it remembers when it connects again (same process), even to a fresh
  server copy. Correct for one seed, but test the "check made offline" cases with a fresh client process.
* Mom's $50 (script 145) and Henry's $49.80 Tinpet sale (script 269) behave normally on the patched ROM.

### How LC-1 and the battles were reached

Played naturally: intro, lab, Dr. Aki (name entry), Nae, her medal room, Ikki's house, the TV scene, Mom's errand, the
Riverview City Market, Henry's Metabee parts and Tinpet. Shortcuts, each agreed beforehand:

* **Walk home skipped.** The calibration script runner moved Ikki to his front door at (23,24) on the town map; he
  walked in himself. (His house is the red-roofed one at the east end of the southern street.)
* **Story gate for the medal pick.** At this point the pedestals only describe their medals (event value 0). The game's
  own scripts 216, 231, 232 and 234 set events 236-241 to value 1 later in the story; I wrote that value (three bytes)
  and then picked the medal normally, so the real pedestal script ran in its own room.
* **Robattles** were started by script number (63 and 79, ordinary trainer battles), Kabuto came from `/send`, and the
  B menu flag was set by hand. To end the fight, the enemy's armor was held at 0-1 and Metabee's refilled.
* The story itself is stuck at Mom's Spice-A-Roni errand (cashier "still preparing", lab closed with Ikki's
  "Spice-A-Roni is not the kind of thing that you ask neighbors for…"); the way forward was not found.

### Still open after the second run

DG-3, DG-7, DG-8, DG-11, LC-2 to LC-11, TR-2 to TR-6, GL-1/GL-2/GL-5 (no longer blocked by D1), NG-1, CN-3, the
SV-8 with-save variant on three versions, and a seed generated with `include_version_exclusives`. All need further
story progress (an encounter area, a chest, a working shop, the ending) or a real certificate.

---

## First run

Run on 2026-11-03 against `claude/gallant-mayer-8bc6s9` at `606097d` (world version 0.1.0), with the frozen
Archipelago 0.6.8 install (Generate, Server, BizHawk Client in `--nogui` mode) and BizHawk 2.9.1 (mGBA core).
The game was driven by a Lua harness that loads Archipelago's own `connector_bizhawk_generic.lua` and adds a
command channel (button presses, tile walking, screenshots, RAM reads, savestates). The second player was the server
console. Plan: [PLAYTEST.md](PLAYTEST.md).

**Verdict: not ready for 1.0.0.** There is one P0 defect, the goal and every check fire when a new game is started,
and one P1 defect. Most delivery, item, save and trap cases pass. Everything that needs a Medabot, a Robattle, a
chest or the ending is still open: the story was played naturally only up to Nae's medal room in chapter 0.

## Defects

### D1 (P0): New Game sends every check and completes the goal

When New Game is chosen on the title menu, the game fills all of IWRAM with `0xFF`: `game_flags`, parts, medals,
money and the state bytes. It does this while the Continue / New Game menu is shown when no save exists yet, and while
the "previously saved data will be erased" prompt is shown when one does. A connected client reads that snapshot,
sees every event flag as set and

* sends **all** of the slot's locations (`_report_locations`), and
* sends **CLIENT_GOAL** (`_report_goal`, event 147 reads as set).

Both run on every tick regardless of game state (`worlds/medabots_rpg/client.py:162`,
`worlds/medabots_rpg/client.py:163`). Only delivery is guarded.

Reproduced three times, on Metabee USA, Rokusho USA and Seed A:
1. Load the patched ROM, connect the client, sit at the title.
2. Press Start, then choose New Game (with a save present the confirmation prompt appears; without one the menu itself
   is already `0xFF`).
3. Server log: `Bee sent … (Odoro Marsh - Squidguts Battle Reward)`, … all 11 locations …, then
   `Bee (Team #1) has completed their goal.`

The `0xFF` fill was also seen on Metabee Europe and Rokusho Europe; there, the client was kept offline on purpose.
Continue does **not** do this: the save is preloaded into RAM with valid flags while the menu is shown.

This is the normal first-session flow (load ROM, connect, start a new game), so nearly every player hits it.
Suggested fix: only detect locations and the story goal while the main mode is the field (`0x0300178C == 1`, the
second condition of `safe_to_deliver`). Flags set in battles or menus are then reported a moment later. As a second
guard, ignore a snapshot whose `game_flags` are all `0xFF`. Add a test with an all-`0xFF` snapshot.

### D2 (P1): After connecting to the wrong server, the client stays stopped on the right one

Connecting the Seed A ROM to the Seed B server correctly stops the client with "This ROM was patched for a different
multiworld…". Connecting to the correct server afterwards succeeds (`Bee … has joined`), but nothing is delivered or
detected, and nothing in the log says so. `self.blocked` is only cleared in `_reset()`, which runs when a ROM is
validated again (`worlds/medabots_rpg/client.py:146`, `worlds/medabots_rpg/client.py:158`).
Restarting the client recovered it at once. The setup guide's advice for this message ("Connect to the right server")
therefore does not work. Fix: clear `blocked` on each new `RoomInfo`/`Connected` that matches the ROM's seed, or when
the server connection drops.

### Documentation that does not match observed behavior

* Game page, "what happens when i receive an item?": *"Items are never lost: loading an older save simply gives you
  everything again."* Money pouches received since the save are lost, by design (SV-2, SV-3).
* Game page, traps: *"a trap that cannot be applied yet waits instead of being lost."* An Ambush received on a map
  without encounters arms the counter at once (32), and the game resets the counter to 0 on the next map load, so the
  trap is lost (TR-5).
* Setup guide troubleshooting row for "different multiworld": see D2.

## Results

Pass = behaved as the plan expects. Partial = the testable part passed and the rest is noted. Not run = not reachable
in this run.

### 1. Before anything is run

| ID | Result | Notes |
|---|---|---|
| PF-1 | Pass | ruff clean; 272 world tests (245 subtests) and 47 tool tests pass. Run directly, see "Environment notes". |
| PF-2 | Pass | Built apworld installed in the frozen 0.6.8 `custom_worlds`; loads (no errors in Generate/Server/Client). WebHost from source with the built apworld: options page shows the six groups (Goal & Victory, Locations, Item Pool, Traps, Quality of Life, Advanced), game page and setup guide render. |
| PF-3 | Pass | Default template generates 9 locations, no Rusty Armor/Medal Nap in the spoiler. |

### 2. Generating and patching

| ID | Result | Notes |
|---|---|---|
| GP-1 | Pass | Seed A: two `.apmedabots`, 11 locations each, no unverified warnings. Seed A holds an Ambush (for Roku) and a Money Drain (for Bee). Seed C (40% harsh) holds no trap, as the plan predicts. |
| GP-2 | Pass | Patched through the frozen BizHawk Client: Metabee USA, Rokusho Europe, Metabee Europe, Rokusho USA (plus Seeds B and C on Metabee USA). |
| GP-3 | Pass | Byte diff of all six: only the identity block (46-52 bytes) and blanked reward instructions changed; no unexpected byte; every reward byte now `00`. |
| GP-4 | Pass | Already patched ROM and one changed identity byte: "The ROM already has data where the patch wants to write…"; header `MEDACORE`: "This is a Japanese Medarot ROM…". No ROM produced. The Japanese case was simulated by editing the header (no Japanese dump available). |
| GP-5 | Partial | Metabee USA new game played ~10 minutes of game time without a client (intro, lab, Dr. Aki, Nae). No crash, text intact. Music not checked. The other three ROMs were booted and played through the intro (with client, see CV). |

### 3. Connecting

| ID | Result | Notes |
|---|---|---|
| CN-1 | Pass | `/connect localhost:38281` joins; slot name read from the ROM. |
| CN-2 | Pass | `ws://localhost:38281`, `--connect localhost:38281`, `archipelago://Roku:pw@localhost:38281` all join. `archipelago://Bee@…` *without* a password fails in core (`InvalidURI: username provided without password`); not a world issue. |
| CN-3 | Not run | Needs a host name with a publicly trusted certificate. |
| CN-4 | Pass | Self-signed certificate: "Failed to connect to the multiworld server" (`CERTIFICATE_VERIFY_FAILED`). |
| CN-5 | Pass | "Running handler for Medabots RPG", correct slot, no unverified warning (all four versions). |
| CN-6 | Pass | Unpatched Metabee USA: the unpatched message once in 40 s, then core's "No handler was found…", nothing written. |
| CN-7 | Pass, but see D2 | Stops with the "different multiworld" message, server refuses the slot, nothing delivered. |

### 4. Delivery in every state

| ID | Result | Notes |
|---|---|---|
| DG-1 | Pass | +$10 within ~1 s, one message. |
| DG-2 | Pass | 12 s in an NPC dialogue: nothing; arrives once when it closes. |
| DG-3 | Not run | No chest reached. |
| DG-4 | Pass | B menu, Medawatch and Medaparts screens: waits, then arrives once. The B menu was unlocked by writing `0x03006413 = 1` (the story's opcode `0x5D` sets it later). |
| DG-5 | Pass | Nae's cutscene: waits, arrives once afterwards. |
| DG-6 | Not run | No Medabot yet. |
| DG-7 | Not run | No Medabot yet. |
| DG-8 | Not run | No shop reached. |
| DG-9 | Pass | Probe sent at the title: money stays 0, no message; also nothing at the Continue menu; arrives once after Continue. (Starting a *new* game here triggers D1.) |
| DG-10 | Pass | 12 pouches during six round trips through a door: exactly +$120, 12 messages, no glitch. |
| DG-11 | Not run | No mini-game reached. |
| DG-12 | Pass | Name entry screen and the save prompt: waits, arrives once afterwards. |
| DG-13 | Partial | 10 mixed items (4 parts, 2 medals, 3 pouches, a Money Drain) sent while in the B menu, not a Robattle: all 10 arrive afterwards, once, in order (4 per tick); money $50 → $282.50 proves the drain ran between the medium and the large pouch. |
| DG-14 | Pass | `/send_multiple 20`: +$200 exactly, 20 messages, no crash. |
| DG-15 | Pass | At $990, a large pouch clamps at $999.99 (menu shows $999.99); the part after it arrives. |
| DG-16 | Pass | 20 s paused: the client drops the BizHawk link ("Connection timed out", core), reconnects after resume, both items arrive once. |

### 5. What the items do

| ID | Result | Notes |
|---|---|---|
| IT-1 | Partial | Metabee's four parts and Rokusho's four parts own ×1 in the right slot and show with the right names in the Medaparts screen (MISSILE, REVOLVER, SUBMACHINGUN, OCHITSUKA; ANTENNA, SWORD, PIPO HAMMER, TATACKER). Equipping and battle use not tested (no Medabot). |
| IT-2 | Pass | Same part again: still ×1. |
| IT-3 | Partial | Medals appear in the medal case under their own name (KABUTO Lv 0, Shoot/Strike, Next Lv 100), survive in-game save and reload. Putting one into a Medabot not tested. All received medals came in at level 0, because no medal in the case had a higher level. |
| IT-4 | Pass | Same medal again: no second copy; Kuwagata, Bat, Knight each get their own slot. |
| IT-5 | Pass | +$10, +$50, +$200; menu shows dollars and cents. |
| IT-6 | Pass | Seed A: `Found …` for own items, `Received … from Archipelago` for console items. Seed B (progression only): real seed items via `/send_location` announce the medal and part, not the pouch. Seed C: nothing announced. Note: `/send` items carry flags 0, so they never count as progression; use `/send_location` to test this mode. |
| IT-7 | Partial | The Rokusho-only Kuwagata medal sent to Metabee USA is owned and named. No seed generated with the option. |

### 6. Saves and persistence

| ID | Result | Notes |
|---|---|---|
| SV-1 | Pass | Parts, medals, money saved in-game; BizHawk closed and reopened; Continue: everything there, money not added again, no repeated messages; client reconnected to BizHawk by itself. |
| SV-2 | Pass | Older save loaded: all 4 parts and 4 medals back silently within ~4 s; money since the save (pouches and drains) not re-applied, as designed. |
| SV-3 | Pass | Same with a savestate: parts and medal back silently within ~6 s; pouch not re-added. |
| SV-4 | Pass | Client killed and restarted: nothing delivered twice. |
| SV-5 | Pass | Server stopped with `/exit` and restarted from its `.apsave` ("63 received items"): client reconnected by itself, nothing duplicated. |
| SV-6 | Partial | Items sent while the client was closed arrived once on start. The offline check half needs a location. |
| SV-7 | Pass | Soft reset mid-session: client keeps running and delivers after Continue. |

### 7. Locations

| ID | Result | Notes |
|---|---|---|
| LC-1 | Not run (reached) | Reached Nae's medal room (map 27) in natural play in chapter 0. The pedestals only describe their medal at this point ("It's a BAT Medal… compatible with Medaparts that target Air Type Medabots"); taking one needs later story beats. A savestate right before the room exists. |
| LC-2 to LC-11 | Not run | Need story progress. |

### 8. Traps

| ID | Result | Notes |
|---|---|---|
| TR-1 | Pass | Normal: $290 → $217.50, $100 → $75, $0 stays $0. Rokusho Europe: $260 → $195. |
| TR-2 | Not run | Harsh drain not tried (Seed C client was used for the goal only). |
| TR-3, TR-4 | Not run | Need an encounter area and a Medabot. |
| TR-5 | Observed | Ambush indoors: counter set to 32 and stays while walking on that map; the next map load resets it to 0. Ambush received off encounter maps is silently lost; an ambush an hour later cannot happen. Decision needed: hold the trap until the player is on an encounter map (script state + `0xC29`), or document it. |
| TR-6 | Not run | |
| TR-7 | Pass | Rusty Armor and Medal Nap: message only, no effect; the pouch after them arrives. |
| TR-8 | Partial | Money Drain sent while in the B menu waits and applies once (inside DG-13). Battle and cutscene states not tried for traps. |

### 9. Goals

| ID | Result | Notes |
|---|---|---|
| GL-1, GL-2, GL-5 | Not run | **Blocked by D1**: the goal already completes when the new game is started. |
| GL-3 | Pass | Seed B, inside the B menu: Ninja twice does not complete; Bear (second different medal) does. |
| GL-4 | Pass | Seed C: a duplicate part does not count; the third different part completes. |

### 10. Other versions

| ID | Result | Notes |
|---|---|---|
| CV-1 | Partial | Rokusho Europe: CN-5, DG-1, DG-4, IT-1, IT-3, IT-5, TR-1 pass. DG-7, TR-3 and locations not reachable. |
| CV-2 | Pass (no location) | Metabee Europe and Rokusho USA: patch, boot, connect, a part, a medal and a pouch each arrive correctly; a new game on the same slot re-asserts all earlier parts and medals. |

### 11. Robustness

| ID | Result | Notes |
|---|---|---|
| NG-1 | Not run | No hour-long connected play. The Seed A server ran about an hour with frequent console sends, several BizHawk restarts, soft resets, savestate loads and a pause, without a crash or a corrupted save. |
| NG-2 | Pass | EmuHawk killed and restarted: client reconnected; after Continue everything was re-asserted silently, money not re-added. |
| NG-3 | Partial | Server down for ~1 min: client retries ("reconnecting in 20 seconds") and rejoins by itself. The check half needs a location. |
| NG-4 | Pass | Only `shuffle_npc_gifts`: "the selected options leave no locations to randomize. Turn at least one location category on." |
| NG-5 | Pass | At 400% speed: 5 pouches and a medal arrive once each. |

Extra: the medals named "?" and "!" arrive and show as "?" and "!" in the medal list (the client writes an empty name
for them, the game displays them fine).

## Environment notes (not world defects)

* The local `host.yaml` has `generator: players: 2`, so generating from one YAML crashed with a `KeyError` on
  `weights.yaml` and then waited for Enter. Passing `--multi 1` works.
* `host.yaml`'s `emuhawk_path` pointed to a BizHawk folder that no longer exists.
* `tools/dev.sh` checks for `.venv/bin/python`, but a Windows-native venv has `.venv/Scripts/python.exe`, so on
  Windows it would try to create the venv again (read from the script, not run). PF-1 was run with the same commands
  by hand.
* With `GENERATORS: 0` the scratch WebHost logged an autolauncher error; pages were unaffected.

## How the setup was changed and restored

* `medabots_rpg.apworld` was copied into `C:\ProgramData\Archipelago\custom_worlds` for the run and removed afterwards.
* `host.yaml` (rom path added, `rom_start` off), BizHawk `config.ini`, and the original Metabee USA SaveRAM were backed
  up before the run and restored from those backups afterwards. BizHawk's own `Medabots - Metabee (USA).SaveRAM.bak`
  was rotated by one test run; both copies were blank before and after.
* Test SaveRAMs, savestates, patched ROMs, seeds and logs were kept outside the repository.

## Still to do for Step 5

1. Fix D1 and D2, then rerun DG-9, CN-7, a connected new game on two versions, and the P0 delivery cases.
2. A human playthrough on Metabee USA (Seed A) for LC-1 to LC-11, GL-1/GL-2, DG-3/6/7/8/11, TR-2 to TR-6, NG-1 and
   the location halves of SV-6 and NG-3; CV-1's locations, DG-7 and TR-3 on Rokusho Europe.
3. CN-3 with a real certificate.
4. Decide TR-5 and update the game page lines listed above.
