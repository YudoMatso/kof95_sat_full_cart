# The King of Fighters '95 Full Cart (Sega Saturn)

**What if the Saturn had received its Neo Geo ports on cartridge instead of CD?**

This project takes the Japanese Saturn version of *The King of Fighters '95* and moves the whole game from the CD to a big cartridge, the way Neo Geo games are delivered. No loading screens, the arcade speed, and the sound you choose:

- a **48 MiB cartridge** with the Neo Geo arcade music, sound effects and voices built in: no CD at all;
- a **32 MiB cartridge** that plays its music from the disc in the drive: the Saturn soundtrack, or the **orchestral arranged soundtrack** of the Neo Geo CD and PlayStation versions.

**From the VS screen to the fight: 4.5 seconds on the original Saturn CD, 0.6 seconds on the cartridge.**

The repository contains **no game data**. You build the cartridge image yourself from your own copies of the game.

> **New in 2.1.0-beta.1**: the game runs as smoothly and answers the controls as fast as the Neo Geo board, the new 32 MiB "CD audio" cartridge with the arranged soundtrack of the Neo Geo CD and PlayStation discs, and a new builder. See the [changelog](CHANGELOG.md).

## Quick start

1. Download the builder for your system (Windows or Linux) from the [releases page](https://github.com/YudoMatso/kof95_sat_full_cart/releases) and unpack it.
2. Start `kof95_cart_builder` and choose your own dumps: the Japanese disc, the 2 MiB ROM cartridge, and optionally the Neo Geo `kof95.zip`. The line next to **Build** tells you which cartridge you will get. Press **Build**.
3. Play the result in Mednafen or on MiSTer, with the region set to Japan (see [Playing](#playing)).

## What it does

- **All the game is on the cartridge.** No loading screens: from the team screen to the fight, the game takes the same number of frames as the Neo Geo arcade board on 7 stages out of 8.
- **The arcade speed**: slowdowns as rare as on the Neo Geo board (measured in CPU against CPU fights on every stage), and the dojo, the heaviest stage, at the arcade level.
- **Controls as fast as the arcade board**: a button press shows on screen 5 frames later, like on the Neo Geo.
- **All graphics stored uncompressed**, like on the Neo Geo cartridge: the game never decompresses anything while you play.
- **Closer to the arcade version** than the Saturn release: the team-order screen with its taunts and moving characters, Omega Rugal's blue flash, the far background on the same line as on the Neo Geo.
- **Same game otherwise**: same graphics, same gameplay as the Saturn release.

### The two cartridges

| | 48 MiB cartridge | 32 MiB "CD audio" cartridge |
|---|---|---|
| Music | the Neo Geo arcade soundtrack, from the cartridge | from the disc in the drive (see below) |
| Sound effects and voices | arcade versions, in time with the picture | Saturn versions |
| CD needed to play | no | yes, for the music (the game also runs without a disc, with no music) |
| Dumps needed to build it | disc, ROM cartridge, Neo Geo `kof95.zip` | disc, ROM cartridge |
| Files | `kof95_cart.ss`, `kof95_cart_48M.bin` | `kof95_cart_cd_audio.ss`, `kof95_cart_cd_audio_32M.bin` |

Both have the same speed, controls and fixes. With the 48 MiB cartridge, the music and sounds go through the sound of the Neo Geo AES console's headphone output.

The disc in the drive decides the music of the 32 MiB cartridge:

- **the Saturn disc** of the game: the original Saturn soundtrack;
- **the Neo Geo CD or PlayStation disc** of *The King of Fighters '95*: the orchestral arranged soundtrack, recognised by the cartridge, with every piece in its place and seamless loops. The PlayStation versions of the pieces differ a little from the Neo Geo CD ones;
- **no disc**: the game runs normally, without music.

### Against the original

| | Original Saturn CD | Full Cart | Neo Geo (arcade) |
|---|---|---|---|
| Loading before each fight | about 5 seconds of "NOW LOADING" | none (same timing as the arcade) | none |
| Music between rounds | stops | continues | continues |
| Slowdowns in fights | ≈ 1 frame in 300 | ≈ 1 frame in 1,900 | ≈ 1 frame in 1,400 |
| Button press to screen | 8 frames | 5 frames | 5 frames |
| Team-order screen taunts | no | yes | yes |

Slowdowns: the Full Cart measured on MiSTer, the arcade version in MAME, the Saturn CD in Mednafen. They are almost always a single 1/60 s frame.

## Status

- **Works** in the Mednafen emulator and on **MiSTer** (with a modified Saturn core, see below), both cartridges, checked by automated runs and played by hand, with the Saturn, Neo Geo CD and PlayStation discs and with no disc.
- **Japan region only**, like the original game: the emulator or the console must be set to Japan (see [Playing](#playing)).
- **Real Saturn: not ready yet.** The 48 MiB image boots on a Wasca cartridge once its cartridge bus timing is patched, with some defects left; the 32 MiB cartridge has not been tried on real hardware. This is being worked on.
- **Not fully covered**: bosses, endings, 2-player mode.

## Building the cartridge image

You need your own dumps of the game:

- the disc: *The King of Fighters '95* (Japan, T-3101G), any Japanese pressing: its `.cue` file with its `.bin` tracks (one or several), or its track 01 alone as a `.bin`, or an `.iso` (only the data track is used);
- the 2 MiB ROM cartridge sold with the game: `mpr-18811-mx.ic1`;
- optional, for the 48 MiB cartridge: the Neo Geo MVS ROM set of *The King of Fighters '95*, `kof95.zip` (MAME name `kof95`; the sound files `084-m1.m1`, `084-v1.v1`, `084-v2.v2` and `084-v3.v3` are read).

To play the music of the 32 MiB cartridge you also need the disc in the drive: the Saturn disc, or the Neo Geo CD or PlayStation disc of the game.

### The easy way: the builder (Windows, Linux)

Download the archive for your system from the releases page, and unpack it anywhere:

| System | Archive |
|---|---|
| Windows 10/11, 64-bit | `kof95_cart-<version>-windows-x64.zip` |
| Linux, 64-bit (glibc 2.31 or later: Ubuntu 20.04, Debian 11 or later) | `kof95_cart-<version>-linux-x64.tar.gz` |

Start `kof95_cart_builder` (`kof95_cart_builder.exe` on Windows), choose the files with the **Browse…** buttons or drop them on the window, and press **Build**. The builder checks each dump as soon as you choose it (a wrong version is reported before anything is built), tells you which cartridge the files give, asks before replacing files already in the output folder, and shows the progress of each step.

The archive holds the builder, the build script `kof95_cart.py` and [PyPy](https://pypy.org), a fast version of Python (MIT license), so nothing has to be installed. On Linux, the file dialogs use the desktop portal (`xdg-desktop-portal`, present on the usual desktops); without it, type or drop the paths.

### From a terminal: the script alone

Everything is in one Python script, `kof95_cart.py`. It needs **Python 3.8 or later**, nothing else. With **PyPy** it runs about 15 times faster (install `pypy3` from your package manager or from pypy.org); the usual Python works too, only slower.

    pypy3 kof95_cart.py <disc> <mpr-18811-mx.ic1> [kof95.zip] [output_folder]

With `kof95.zip` you get the 48 MiB cartridge, without it the 32 MiB "CD audio" one. Linux / macOS:

```sh
pypy3 kof95_cart.py "path/to/King of Fighters '95.cue" path/to/mpr-18811-mx.ic1 path/to/kof95.zip out
```

Windows (Command Prompt or PowerShell; `py` instead of `pypy3` for the Python from python.org):

```bat
pypy3 kof95_cart.py "C:\Games\King of Fighters '95.cue" C:\Games\mpr-18811-mx.ic1 C:\Games\kof95.zip out
```

The archives above also run the script this way: `pypy/bin/pypy3 kof95_cart.py …` on Linux, `pypy\pypy3.exe kof95_cart.py …` on Windows.

For the 48 MiB cartridge, most of the time goes into rebuilding the 23 pieces of music from the arcade sound program, on all the processor's cores: **about 3 minutes with PyPy** on a recent processor (16 threads), **from about 15 minutes to 2 hours with the usual Python**. The 32 MiB cartridge takes about a minute. A progress bar shows each step. If the build fails, the step that failed is shown and `kof95_cart.log`, in the output folder, has the details: please attach it when you report a problem.

Tested on Linux, on Windows under Wine (Python 3.13 and PyPy 3.11), and by players on Windows. macOS should work with the script alone, but has not been tested.

The script checks the result: it prints **"OK, identical to the reference"** when your image matches the one tested by the author. If your dumps are different, it stops or reports a difference.

## Playing

**Mednafen** (tested with version 1.32.1 on Linux, with a Saturn BIOS; Mednafen on Windows should work the same way). Keep the default region, Japan (`ss.region_default jp`).

48 MiB cartridge, no CD needed:

```sh
mednafen out/kof95_cart.ss
```

32 MiB cartridge, with the disc for the music (the `.cue` of the Saturn, Neo Geo CD or PlayStation disc):

```sh
mednafen -ss.dbg_exe_cdpath "/absolute/path/to/the.cue" out/kof95_cart_cd_audio.ss
```

**Other emulators**: the images are big ROM cartridges, which are not standard Saturn cartridges. Only Mednafen works so far: Ymir and Beetle Saturn (RetroArch) only take the official 2 MiB cartridges.

**MiSTer**: the official Saturn core only reads 2 MiB of cartridge. Use the modified core [Saturn_MiSTer_Cart](https://github.com/YudoMatso/Saturn_MiSTer_Cart) (branch `rom-32m`, release v1.1.0 `Saturn_Cart_20261114` or later) in "ROM 32/48M" mode and load the `.bin` as the cartridge: `kof95_cart_48M.bin` (no CD needed), or `kof95_cart_cd_audio_32M.bin` with the disc image of your choice loaded as the CD. Set **Region** to **Japan** (the default): "Auto" takes the region from a CD, so it does not work here.

## Older versions

The earlier releases stay on the releases page: [version 1.1.0](https://github.com/YudoMatso/kof95_sat_full_cart/releases/tag/v1.1.0) (32 MiB cartridge with the music from the CD, Saturn sound) is now replaced by the 32 MiB "CD audio" cartridge of this version, which is faster and also takes the Neo Geo CD and PlayStation discs.

## How it was done, in short

On Neo Geo, the game lived on a huge cartridge. On Saturn, it came on CD, with a 2× drive and little memory: a "NOW LOADING" screen before every fight, the music paused between rounds, and the sound redone with the Saturn's own samples. The limit was the medium, not necessarily the console: the Saturn's cartridge port can address 48 MiB, enough for the whole game and the arcade sound. This project is a proof of concept of that.

The game was not rewritten, it was **patched**. The part of the game that reads files from the CD now reads them from the cartridge, the waits that were only there for the slow CD drive were removed, and the sound requests of the game go to a new player of the arcade music and sounds, running on the Saturn's second processor. Where the arcade version is faster, the Saturn version was measured against it frame by frame and tuned to match: more of the stages is drawn by the second video chip, and the busiest parts of the game's code run as native code.

The hard part: the Saturn port is the Neo Geo's 68000 program translated to the Saturn's SH-2 processors, its graphics chips cannot read the cartridge directly, and the sound chip has its own small memory, so every piece of data has to be copied to the right place at the right time. The arcade music is rebuilt on your machine from the arcade sound program, run by an emulated Z80, then converted for the Saturn's sound chip. For the 32 MiB cartridge, the arranged soundtrack is matched to the game's music through the Neo Geo CD version's own table of tracks.

## Thanks

- hitomi2500, for testing on real hardware with the Wasca cartridge;
- srg320 and the MiSTer Saturn core developers ([Saturn_MiSTer](https://github.com/MiSTer-devel/Saturn_MiSTer)), on which the modified core is based;
- the Mednafen authors.

## License

The code of this project (`kof95_cart.py` and the builder, source in `builder/`) is free software under the **GNU General Public License v3.0 or later**: you can use, study, modify and share it, as long as modified versions stay under the same license. See `LICENSE`. The release archives also contain PyPy, under its own MIT license (`pypy/LICENSE`).

## Legal

Unofficial fan project, not affiliated with SNK or Sega. *The King of Fighters* is a trademark of SNK. The license above covers only the project's own code, not the game: everything from the game is read from your dumps when you run the script. Use your own dumps, and never share the images it produces.
