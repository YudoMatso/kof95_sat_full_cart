# The King of Fighters '95 on Sega Saturn — cartridge edition (v1.0 "Pure")

**What if the Saturn had received its Neo Geo ports on cartridge instead of CD?**

This project is a proof of concept. It takes the Japanese Saturn version of *The King of Fighters '95* and moves the whole game from the CD to a large cartridge, the way Neo Geo games are delivered. The aim is to show that the Saturn could have matched the Neo Geo on this kind of game, even though the Saturn is much harder to program than SNK's hardware for a sprite-heavy 2D fighting game.

The repository contains **no game data**. You build the cartridge image yourself from your own copy of the game.

## This version: "Pure"

The original Saturn game, unchanged, running entirely from the cartridge:

- All the game data is on the cartridge; the CD only plays the music.
- The game reads its files from the cartridge instead of the CD drive, so going from the team screen to the fight takes about 1.5 seconds instead of about 6 seconds on CD.
- Nothing else is changed: same menus, same timing, same waits as the Saturn release.

The next version removes the loading screens entirely and matches the arcade timing.

## How it works, in short

The Saturn's cartridge port can address 32 MiB, enough for the entire game. The cartridge image holds a small start-up program, the original 2 MiB ROM cartridge sold with the game, and the full content of the CD's data track. The game is patched so that the part that read files from the CD now copies them from the cartridge. The CD music commands are untouched.

## Building the cartridge image

Everything is in one Python script, `kof95_cart.py`. It needs **Python 3.8 or later**, nothing else, and your own dumps of the game:

- the disc: *The King of Fighters '95* (Japan, T-3101G), as a `.cue` file with its `.bin` tracks;
- the 2 MiB ROM cartridge sold with the game: `mpr-18811-mx.ic1`.

```sh
python3 kof95_cart.py pure "path/to/King of Fighters '95.cue" path/to/mpr-18811-mx.ic1 out
```

You get `out/kof95_cart_pure.ss` (Mednafen) and `out/kof95_cart_pure_32M.bin` (MiSTer). The script checks the result and prints **"OK, identical to the reference"** when your image matches the one tested by the author.

## Playing

**Mednafen** (tested with version 1.32.1 and a Saturn BIOS). Give it the CD too, for the music:

```sh
mednafen -ss.dbg_exe_cdpath "/absolute/path/to/the.cue" out/kof95_cart_pure.ss
```

**MiSTer** (not tested with this version): the official Saturn core only reads 2 MiB of cartridge. Use the modified core [Saturn_MiSTer_Cart](https://github.com/YudoMatso/Saturn_MiSTer_Cart) (branch `rom-32m`) in "ROM 32M" mode with `kof95_cart_pure_32M.bin`.

## Legal

Unofficial fan project, not affiliated with SNK or Sega. *The King of Fighters* is a trademark of SNK. `kof95_cart.py` contains only the project's own code; everything from the game is read from your dumps when you run it. Use your own dumps, and never share the images it produces.
