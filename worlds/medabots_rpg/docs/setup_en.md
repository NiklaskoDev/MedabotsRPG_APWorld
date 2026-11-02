# Medabots RPG Setup Guide

## Required Software

- [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.8 or later
- An English *Medabots: Metabee Version* or *Medabots: Rokusho Version* ROM for the Game Boy Advance (USA or
  Europe). The Archipelago community cannot provide this.
- [BizHawk](https://tasvideos.org/BizHawk/ReleaseHistory) 2.9 or later

### Installing the world

Download `medabots_rpg.apworld` from the [releases page](https://github.com/NiklaskoDev/MedabotsRPG_APWorld/releases)
and double-click it, or put it into the `custom_worlds` folder of your Archipelago installation. If the world is
already part of your Archipelago version you can skip this step.

### Configuring BizHawk

Once you have installed BizHawk, open `EmuHawk.exe` and change the following settings:

- Under `Config > Customize`, check the "Run in background" option to prevent disconnecting from the client while you're
  tabbed out of EmuHawk.
- Open a `.gba` file in EmuHawk and go to `Config > Controllers…` to configure your inputs. If you can't click
  `Controllers…`, load any `.gba` ROM first.
- Consider clearing keybinds in `Config > Hotkeys…` if you don't intend to use them. Select the keybind and press Esc to
  clear it.

## Generating and Patching a Game

1. Create your options file (YAML). You can make one on the
   [Medabots RPG options page](../../../games/Medabots%20RPG/player-options).
2. Follow the general Archipelago instructions for [generating a game](/tutorial/Archipelago/setup_en#generating-a-game).
   This will generate an output file for you. Your patch file will have the `.apmedabots` file extension.
3. Open `ArchipelagoLauncher.exe`.
4. Select "Open Patch" on the left side and select your patch file.
5. If this is your first time patching, you will be prompted to locate your vanilla ROM.
6. A patched `.gba` file will be created in the same place as the patch file.
7. On your first time opening a patch with BizHawk Client, you will also be asked to locate `EmuHawk.exe` in your
   BizHawk install.

The patch never contains any game data. It is applied to your own ROM, and it refuses to touch a ROM that is not one of
the four supported versions, or that has already been patched.

## Connecting to a Server

By default, opening a patch file will do steps 1-5 below for you automatically. Even so, keep them in mind in case you
have to close and reopen a window mid-game.

1. Medabots RPG uses Archipelago's BizHawk Client. If the client isn't still open from when you patched your game, you
   can re-open it from the launcher.
2. Ensure EmuHawk is running the patched ROM.
3. In EmuHawk, go to `Tools > Lua Console`. This window must stay open while playing.
4. In the Lua Console window, go to `Script > Open Script…`.
5. Navigate to your Archipelago install folder and open `data/lua/connector_bizhawk_generic.lua`.
6. The emulator and client will eventually connect to each other. The BizHawk Client window should indicate that it
   connected and recognized Medabots RPG. Your slot name is read from the ROM, so you will not be asked for it.
7. To connect the client to the server, enter your room's address into the top text field of the client and click
   Connect.

### Server addresses: `ws://` and `wss://`

Both unencrypted (`ws://`) and encrypted (`wss://`) servers are supported. Any of these work in the address field:

| You enter | What happens |
|---|---|
| `archipelago.gg:38281` | The client tries an unencrypted connection and, if the server requires encryption, automatically retries with `wss://`. |
| `ws://localhost:38281` | A plain, unencrypted connection (fine on your own computer or network). |
| `wss://example.com:38281` | An encrypted connection. The server's certificate must be valid and issued by a trusted authority. |
| `archipelago://Name:password@archipelago.gg:38281` | The same as above, including slot name and password. The WebHost's "Connect" links use this form. |

If a `wss://` connection fails with "Failed to connect to the multiworld server", the usual cause is a certificate that
is self-signed or expired. The client deliberately refuses such servers instead of ignoring the problem; ask the host
for a certificate from a public authority (for example Let's Encrypt), or use `ws://` on a network you trust.

You should now be able to receive and send items. You'll need to do these steps every time you want to reconnect. It is
perfectly safe to make progress offline; everything will re-sync when you reconnect.

## Troubleshooting

| Message | What it means and what to do |
|---|---|
| *This version of the world has not been verified against a real ROM yet…* (when generating) | This is a pre-release. Set `allow_unverified_build: true` in your YAML only if you are testing the world. |
| *This is an unpatched Medabots ROM.* | You loaded the original ROM. Open your `.apmedabots` file with the Launcher and load the patched `.gba` it creates. |
| *This ROM was patched for a different multiworld than the one on this server.* | Your ROM belongs to another seed. Connect to the right server, or patch again with the matching `.apmedabots` file. |
| *This seed was generated with a different version of the Medabots RPG world…* | Install the version of the world named in the message. |
| *The ROM already has data where the patch wants to write.* | The ROM is already patched or modified. Patch a clean, unmodified ROM. |
| *This ROM is not a supported version of Medabots.* | Use an English *Metabee* or *Rokusho* GBA ROM. Japanese ROMs and *Medabots AX* are not supported. |
| *No handler was found for this game.* | The world is not installed correctly, or you loaded a different ROM than the patched one. |

Received items appear once you are walking around freely. If nothing arrives, leave the menu or battle and wait a
moment.
