# The King of Fighters '95 on Sega Saturn — cartridge edition

**What if the Saturn had received its Neo Geo ports on cartridge instead of CD?**

This project is a proof of concept. It takes the Japanese Saturn version of *The King of Fighters '95* and moves the whole game from the CD to a large cartridge, the way Neo Geo games are delivered. The goal is to show that the Saturn could have matched the Neo Geo on this kind of game, even though the Saturn is much harder to program than SNK's hardware for a sprite-heavy 2D fighting game.

The repository contains **no game data**. You build the cartridge image yourself from your own copy of the game.

## Why this matters

On Neo Geo, a fighting game lives on a huge cartridge: the next fight starts almost instantly. On Saturn, the same game came on CD, with a 2× drive and little memory, so you waited on a **"NOW LOADING"** screen before every fight, and the music paused between rounds.

The limit was the medium, not necessarily the console: the Saturn's cartridge port can address 32 MiB, enough for the entire game. This project puts that to the test.

## What it does

- **All the game data is on the cartridge.** The CD is only used to play the music tracks.
- **No loading screens.** From the team screen to the fight, the game takes the same number of frames as the Neo Geo arcade board on 7 stages out of 8 (measured frame by frame against the arcade version in an emulator).
- **Music starts with the fight and keeps playing between rounds**, instead of stopping and restarting.
- **Faster start-up**: the "NOW LOADING" screen at boot is gone.
- **Same game otherwise**: same graphics, same voices, same CD soundtrack as the Saturn release.

| | Original Saturn CD | This version | Neo Geo (arcade) |
|---|---|---|---|
| Loading before each fight | about 5 seconds of "NOW LOADING" | none (same timing as the arcade) | none |
| Music between rounds | stops, then restarts | continues | continues |
| Slowdowns in fights | rare (≈ 1 frame in 300) | rare (≈ 1 frame in 100) | very rare (≈ 1 frame in 1,000) |

Slowdowns are almost always a single 1/60 s frame, and the only noticeable one happens on all three versions at the same moment.

## How it was done, in short

The game was not rewritten. It was **patched**: the part of the game that reads files from the CD now reads them from the cartridge, and the waits that were only there because of the slow CD drive were removed or shortened. Where the arcade version is faster, the Saturn version was measured against it frame by frame and tuned to match.

What made it hard: the Saturn port is the Neo Geo's 68000 program translated to the Saturn's SH-2 processors, its graphics chips cannot read the cartridge directly, and the sound chip has its own small memory. Every piece of data has to be copied to the right place at the right time.

## Status

- **Works** in the Mednafen emulator and on **MiSTer** (with a modified Saturn core, see below), played by hand.
- **Not tested on a real Saturn**: no 32 MiB Saturn flash cartridge is known to exist.
- **Not fully covered**: bosses, endings, 2-player mode.
- The project is complete. Any later update is listed in `CHANGELOG.md`.

## Variants

The script builds two variants of the cartridge image:

- **`noloading`**: the full result described above.
- **`pure`**: the original game, unchanged, simply running from the cartridge. Going from the team screen to the fight already takes about 1.5 seconds instead of about 6 on CD, but the original loading screens are still there.

Releases follow the usual `major.minor.patch` numbering; see `CHANGELOG.md`.

## Building the cartridge image

Everything is in one Python script, `kof95_cart.py`. It needs **Python 3.8 or later**, nothing else, and your own dumps of the game:

- the disc: *The King of Fighters '95* (Japan, T-3101G), as a `.cue` file with its `.bin` tracks;
- the 2 MiB ROM cartridge sold with the game: `mpr-18811-mx.ic1`.

```sh
python3 kof95_cart.py noloading "path/to/King of Fighters '95.cue" path/to/mpr-18811-mx.ic1 out
```

Use `pure` instead of `noloading` for the pure variant. The "no loading" build takes about a minute: it prepares the stage graphics in advance with the game's own code.

You get two files in `out/`:

| File | For |
|---|---|
| `kof95_cart_noloading.ss` | the Mednafen emulator |
| `kof95_cart_noloading_32M.bin` | MiSTer |

The script checks the result: it prints **"OK, identical to the reference"** when your image matches the one tested by the author. If your dump is different, it stops or reports a difference.

## Playing

**Mednafen** (tested with version 1.32.1 and a Saturn BIOS). Give it the CD too, for the music:

```sh
mednafen -ss.dbg_exe_cdpath "/absolute/path/to/the.cue" out/kof95_cart_noloading.ss
```

**MiSTer**: the official Saturn core only reads 2 MiB of cartridge. Use the modified core [Saturn_MiSTer_Cart](https://github.com/YudoMatso/Saturn_MiSTer_Cart) (branch `rom-32m`) in "ROM 32M" mode, load `kof95_cart_noloading_32M.bin` as the cartridge and the CD image as usual.

## Legal

Unofficial fan project, not affiliated with SNK or Sega. *The King of Fighters* is a trademark of SNK. `kof95_cart.py` contains only the project's own code; everything from the game is read from your dumps when you run it. Use your own dumps, and never share the images it produces.
