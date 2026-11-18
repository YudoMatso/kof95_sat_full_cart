# The King of Fighters '95 on Sega Saturn — cartridge edition

**What if the Saturn had received its Neo Geo ports on cartridge instead of CD?**

This project is a proof of concept. It takes the Japanese Saturn version of *The King of Fighters '95* and moves the whole game from the CD to a large cartridge, the way Neo Geo games are delivered. The goal is to show that the Saturn could have matched the Neo Geo on this kind of game, even though the Saturn is much harder to program than SNK's hardware for a sprite-heavy 2D fighting game.

The repository contains **no game data**. You build the cartridge image yourself from your own copies of the game.

> **Version 2.0 is the main version**: the whole game on one 48 MiB cartridge, no CD.
> Version 1.1.0 (32 MiB cartridge, music from the CD) remains as an option: see [Optional: version 1.1.0](#optional-version-110-32-mib-cartridge-and-the-cd).
> New in 2.0.0-beta.2: a launcher for Windows and Linux, and a build about 5 to 15 times faster.

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

- **Works** in the Mednafen emulator and on **MiSTer** (with a modified Saturn core, see below), checked by automated runs and played by hand.
- **Japan region only**, like the original game: the emulator or the console must be set to Japan (see [Playing](#playing)).
- **Not working yet on a real Saturn.** The image is 48 MiB, which a Wasca cartridge with 48 MiB support can hold. In the first test, on a European Saturn with the image's region changed to Europe, the game goes back to the BIOS after about 2 seconds of black screen. This is being looked into.
- **Not fully covered**: bosses, endings, 2-player mode.

## Building the cartridge image

You need your own dumps of the game:

- the disc: *The King of Fighters '95* (Japan, T-3101G), as a `.cue` file with its `.bin` tracks;
- the 2 MiB ROM cartridge sold with the game: `mpr-18811-mx.ic1`;
- the Neo Geo MVS ROM set of *The King of Fighters '95*: `kof95.zip` (MAME name `kof95`; the sound files `084-m1.m1`, `084-v1.v1`, `084-v2.v2` and `084-v3.v3` are read).

### The easy way: the launcher (Windows, Linux)

Download the archive for your system from the releases page, and unpack it anywhere:

| System | Archive |
|---|---|
| Windows 10/11, 64-bit | `kof95_cart-<version>-windows-x64.zip` |
| Linux, 64-bit (glibc 2.31 or later: Ubuntu 20.04, Debian 11 or later) | `kof95_cart-<version>-linux-x64.tar.gz` |

Start `kof95_cart_gui` (`kof95_cart_gui.exe` on Windows), choose the three files with the **Browse…** buttons or drop them on the window, and press **Start**. The launcher checks the files, shows the progress of each step, and tells you when the image is ready.

The archive holds the launcher, the build script `kof95_cart.py` and [PyPy](https://pypy.org), a fast version of Python (MIT license), so nothing has to be installed. On Linux, the file dialogs use the desktop portal (`xdg-desktop-portal`, present on the usual desktops); without it, type or drop the paths.

### From a terminal: the script alone

Everything is in one Python script, `kof95_cart.py`. It needs **Python 3.8 or later**, nothing else. With **PyPy** it runs about 15 times faster (install `pypy3` from your package manager or from pypy.org); the usual Python works too, only slower.

Linux / macOS:

```sh
pypy3 kof95_cart.py "path/to/King of Fighters '95.cue" path/to/mpr-18811-mx.ic1 path/to/kof95.zip out
```

Windows (Command Prompt or PowerShell; `py` instead of `pypy3` for the Python from python.org):

```bat
pypy3 kof95_cart.py "C:\Games\King of Fighters '95.cue" C:\Games\mpr-18811-mx.ic1 C:\Games\kof95.zip out
```

The archives above also run the script this way: `pypy/bin/pypy3 kof95_cart.py …` on Linux, `pypy\pypy3.exe kof95_cart.py …` on Windows.

Most of the time goes into rebuilding the 23 pieces of music from the arcade sound program, on all the processor's cores: **about 3 minutes with PyPy** on a recent processor (16 threads), **from about 15 minutes to 2 hours with the usual Python**. A progress bar shows each step. If the build fails, the step that failed is shown and `kof95_cart.log`, in the output folder, has the details: please attach it when you report a problem.

Tested on Linux, on Windows under Wine (Python 3.13 and PyPy 3.11), and by players on Windows. macOS should work with the script alone, but has not been tested.

You get two files in `out/`, the same 48 MiB image:

| File | For |
|---|---|
| `kof95_cart.ss` | the Mednafen emulator |
| `kof95_cart_48M.bin` | MiSTer |

The script checks the result: it prints **"OK, identical to the reference"** when your image matches the one tested by the author. If your dumps are different, it stops or reports a difference.

## Playing

**Mednafen** (tested with version 1.32.1 on Linux, with a Saturn BIOS; Mednafen on Windows should work the same way). No CD is needed. Keep the default region, Japan (`ss.region_default jp`):

```sh
mednafen out/kof95_cart.ss
```

**Other emulators**: the image is a 48 MiB ROM cartridge, which is not a standard Saturn cartridge. Only Mednafen has been tested.

**MiSTer**: the official Saturn core only reads 2 MiB of cartridge. Use the modified core [Saturn_MiSTer_Cart](https://github.com/YudoMatso/Saturn_MiSTer_Cart) (branch `rom-32m`, release v1.1.0 `Saturn_Cart_20261114` or later) in "ROM 32/48M" mode and load `kof95_cart_48M.bin` as the cartridge. No CD is needed. Set **Region** to **Japan** (the default): "Auto" takes the region from a CD, so it does not work here.

## Optional: version 1.1.0 (32 MiB cartridge and the CD)

If your setup cannot use a 48 MiB cartridge, the earlier [version 1.1.0](https://github.com/YudoMatso/kof95_sat_full_cart/releases/tag/v1.1.0) builds a 32 MiB image. The cartridge starts the game and holds all its data, with no loading screens. The CD stays in the drive and only plays the music: the Saturn release's soundtrack, with the Saturn sound effects and voices. It needs only the disc and the 2 MiB ROM (no Neo Geo set). It has no launcher: use the `kof95_cart.py` of that release from a terminal, with Python 3.8 or later; its [README](https://github.com/YudoMatso/kof95_sat_full_cart/blob/v1.1.0/README.md) explains how to build and play it (MiSTer: same core, "ROM 32M" mode, with the CD image).

## License

The code of this project (`kof95_cart.py` and the launcher, source in `gui/`) is free software under the **GNU General Public License v3.0 or later**: you can use, study, modify and share it, as long as modified versions stay under the same license. See `LICENSE`. The release archives also contain PyPy, under its own MIT license (`pypy/LICENSE`).

## Legal

Unofficial fan project, not affiliated with SNK or Sega. *The King of Fighters* is a trademark of SNK. The license above covers only the project's own code, not the game: everything from the game is read from your dumps when you run the script. Use your own dumps, and never share the images it produces.
