# The King of Fighters '95 on Sega Saturn — cartridge edition

**What if the Saturn had received its Neo Geo ports on cartridge instead of CD?**

This project is a proof of concept. It takes the Japanese Saturn version of *The King of Fighters '95* and moves the whole game from the CD to a large cartridge, the way Neo Geo games are delivered. The goal is to show that the Saturn could have matched the Neo Geo on this kind of game, even though the Saturn is much harder to program than SNK's hardware for a sprite-heavy 2D fighting game.

The repository contains **no game data**. You build the cartridge image yourself from your own copies of the game.

> **Version 2.0 is a beta** (pre-release). The previous version, 1.1.0, is still available from the releases page.

## Why this matters

On Neo Geo, a fighting game lives on a huge cartridge: the next fight starts almost instantly. On Saturn, the same game came on CD, with a 2× drive and little memory, so you waited on a **"NOW LOADING"** screen before every fight, the music paused between rounds, and the sound was redone with the Saturn's own samples.

The limit was the medium, not necessarily the console: the Saturn's cartridge port can address 48 MiB, enough for the entire game and the arcade sound. This project puts that to the test.

## What it does

- **All the game is on the cartridge**, music included. The CD is not used at all.
- **No loading screens.** From the team screen to the fight, the game takes the same number of frames as the Neo Geo arcade board on 7 stages out of 8 (measured frame by frame against the arcade version in an emulator).
- **The arcade music**: the Neo Geo soundtrack, played from the cartridge by a music player written for the Saturn's second processor. It starts with the fight and keeps playing between rounds.
- **The arcade sound effects and voices**, **in time with the picture** as on the arcade board.
- **The sound of the Neo Geo AES console's headphone output**, for the music and the sound effects alike.
- **Controls answer one frame earlier** than on the original Saturn version.
- **All graphics stored uncompressed**, like on the Neo Geo cartridge: the game never decompresses anything while you play, so slowdowns are rarer than on the arcade board.
- **Team-order screen as on the arcade version**: the characters taunt once the order is chosen, and the one being chosen moves (the Saturn release had dropped both).
- **Same game otherwise**: same graphics, same gameplay as the Saturn release.

| | Original Saturn CD | This version | Neo Geo (arcade) |
|---|---|---|---|
| Loading before each fight | about 5 seconds of "NOW LOADING" | none (same timing as the arcade) | none |
| Music | CD soundtrack, stops between rounds | arcade soundtrack, continues | arcade soundtrack, continues |
| Sound effects and voices | Saturn versions | arcade versions | arcade versions |
| Slowdowns in fights | rare (≈ 1 frame in 300) | very rare (≈ 1 frame in 2,500) | very rare (≈ 1 frame in 1,000) |
| Team-order screen taunts | no | yes | yes |

Slowdowns are almost always a single 1/60 s frame.

## How it was done, in short

The game was not rewritten. It was **patched**: the part of the game that reads files from the CD now reads them from the cartridge, the waits that were only there because of the slow CD drive were removed or shortened, and the sound requests of the game are sent to a new player of the arcade music and sounds. Where the arcade version is faster, the Saturn version was measured against it frame by frame and tuned to match.

What made it hard: the Saturn port is the Neo Geo's 68000 program translated to the Saturn's SH-2 processors, its graphics chips cannot read the cartridge directly, and the sound chip has its own small memory. Every piece of data has to be copied to the right place at the right time. The arcade music is rebuilt on your machine from the arcade sound program, run by an emulated Z80, then converted for the Saturn's sound chip.

## Status

- **Beta.** Works in the Mednafen emulator and on **MiSTer** (with a modified Saturn core, see below), checked by automated runs and played by hand.
- **Not tested on a real Saturn**: the image is 48 MiB, and no Saturn flash cartridge of that size is known to exist.
- **Not fully covered**: bosses, endings, 2-player mode.

## Building the cartridge image

Everything is in one Python script, `kof95_cart.py`. It needs **Python 3.8 or later**, nothing else, and your own dumps of the game:

- the disc: *The King of Fighters '95* (Japan, T-3101G), as a `.cue` file with its `.bin` tracks;
- the 2 MiB ROM cartridge sold with the game: `mpr-18811-mx.ic1`;
- the Neo Geo MVS ROM set of *The King of Fighters '95*: `kof95.zip` (MAME name `kof95`; the sound files `084-m1.m1`, `084-v1.v1`, `084-v2.v2` and `084-v3.v3` are read).

Linux / macOS:

```sh
python3 kof95_cart.py "path/to/King of Fighters '95.cue" path/to/mpr-18811-mx.ic1 path/to/kof95.zip out
```

Windows (Command Prompt or PowerShell, with Python from python.org):

```bat
py kof95_cart.py "C:\Games\King of Fighters '95.cue" C:\Games\mpr-18811-mx.ic1 C:\Games\kof95.zip out
```

The script is written to work on Windows but has only been tested on Linux.

The build takes **from about 15 minutes to 2 hours** depending on the processor, and uses all its cores: most of the time goes into rebuilding the 23 pieces of music from the arcade sound program.

You get two files in `out/`, the same 48 MiB image:

| File | For |
|---|---|
| `kof95_cart.ss` | the Mednafen emulator |
| `kof95_cart_48M.bin` | MiSTer |

The script checks the result: it prints **"OK, identical to the reference"** when your image matches the one tested by the author. If your dumps are different, it stops or reports a difference.

## Playing

**Mednafen** (tested with version 1.32.1 on Linux, with a Saturn BIOS; Mednafen on Windows should work the same way). No CD is needed:

```sh
mednafen out/kof95_cart.ss
```

**Other emulators**: the image is a 48 MiB ROM cartridge, which is not a standard Saturn cartridge. Only Mednafen has been tested.

**MiSTer**: the official Saturn core only reads 2 MiB of cartridge. Use the modified core [Saturn_MiSTer_Cart](https://github.com/YudoMatso/Saturn_MiSTer_Cart) (branch `rom-32m`, release v1.1.0 `Saturn_Cart_20261114` or later) in "ROM 32/48M" mode and load `kof95_cart_48M.bin` as the cartridge. No CD is needed.

## License

The code of this project (`kof95_cart.py`) is free software under the **GNU General Public License v3.0 or later**: you can use, study, modify and share it, as long as modified versions stay under the same license. See `LICENSE`.

## Legal

Unofficial fan project, not affiliated with SNK or Sega. *The King of Fighters* is a trademark of SNK. The license above covers only the project's own code, not the game: everything from the game is read from your dumps when you run the script. Use your own dumps, and never share the images it produces.
