# Changelog

Versions follow `major.minor.patch`: patch = fix, minor = addition that breaks nothing, major = big change.

## 2.1.0-beta.1 - 2026-11-20

**The arcade speed, a second cartridge with the music of the disc in the drive, and a new builder.**

The game:

- **Slowdowns at the arcade level**: in CPU against CPU fights on every stage, measured on MiSTer, about 1 late frame in
  1,900 (the Neo Geo board loses about 1 frame in 1,400). The dojo, the heaviest stage, is now at the arcade level, and the
  waterfall stage is much smoother. More of the stages is drawn by the second video chip, and the busiest parts of the
  game's code run as native code.
- **Controls as fast as the arcade board**: a button press shows on screen 5 frames later, like on the Neo Geo (7 in
  2.0.0-beta.2).
- **Sound effects and voices start at the same moment as on the Neo Geo**, and no longer crackle on MiSTer when the
  action is busy.
- **Fixes of bugs present since 2.0.0-beta.1**:
  - the cutscene after Saisyu lasted 2 seconds too long;
  - the team picture in the cutscenes showed the wrong characters;
  - the team-order screen could be unreadable after a fight between two identical characters, and player 2 could appear
    as a block when joining a game;
  - display glitches: the far background one frame late, a checkerboard on the waterfall stage, missing pixels on
    MiSTer, a wrong win-pose frame and the dojo statue.
- **Closer to the arcade version** than the Saturn release: Omega Rugal's flash is blue, and the far background sits on
  the same line as on the Neo Geo.

New: the **32 MiB "CD audio" cartridge**, built when `kof95.zip` is not given:

- the same speed, controls and fixes as the 48 MiB cartridge, with the Saturn sound effects and voices;
- the music plays from the disc in the drive: the **Saturn disc** for the original soundtrack, or the **Neo Geo CD or
  PlayStation disc** of the game for the **orchestral arranged soundtrack**, recognised automatically, every piece in its
  place, seamless loops;
- **without a disc** the game runs normally, without music;
- it needs no Neo Geo ROM set and fits carts limited to 32 MiB. It replaces version 1.1.0.

The builder (the window, now `kof95_cart_builder`, formerly `kof95_cart_gui`):

- **the Neo Geo set is optional**: with it, the 48 MiB cartridge; without it, the 32 MiB cartridge;
- **checks your dumps** as soon as you choose them (CRC32): a wrong version is reported before anything is built;
- **the disc** can be a `.cue` (one or several `.bin`), its track 01 alone as a `.bin`, or an `.iso`: any Japanese
  pressing works;
- **Build button with a status line**: the next step, a file to fix, or ready, and which cartridge you will get;
- **asks before replacing** files already in the output folder;
- **a new look**: dark theme, bigger text, aligned fields, readable progress and results.

The build script `kof95_cart.py`: `kof95.zip` is optional, the same disc formats as the builder; the 32 MiB cartridge
builds in about a minute.

MiSTer: unchanged, core [Saturn_MiSTer_Cart](https://github.com/YudoMatso/Saturn_MiSTer_Cart) v1.1.0 or later, "ROM
32/48M" mode; for the 32 MiB cartridge, also load the disc image (Saturn, Neo Geo CD or PlayStation).

Beta: tested in Mednafen and on MiSTer (both cartridges, the three discs and no disc), by automated runs and by hand.
Not ready yet on a real Saturn.

    pypy3 kof95_cart.py "path/to/King of Fighters '95.cue" path/to/mpr-18811-mx.ic1 [path/to/kof95.zip] out

## 2.0.0-beta.2 - 2026-11-15

Same cartridge image as 2.0.0-beta.1 (identical SHA-256): this version changes only how it is built.

- **A builder with a window** for Windows and Linux (64-bit): choose the three dumps, press Start, follow the steps.
  One archive per system, with everything inside (the window, the script and PyPy): nothing to install.
- **5 to 15 times faster** with PyPy, now included in the archives and supported by the script: about 3 minutes
  instead of 12 on a 16-thread processor, and much more saved on smaller ones.
- **Progress bar**: each step and how far it is, measured from the work actually done.
- **Clearer errors**: the step that failed is shown, and `kof95_cart.log` is always written, with the details to report.
- **Ctrl-C** now stops the whole build at once (the second wave of music captures used to start anyway).
- **Fix** (archives updated on 2026-11-15): the build stopped at step 8 when the temporary folder had a space in its
  path, as `E:\Temporary Files` on Windows.
- **Windows**: the script runs in UTF-8 mode, so that system languages without the accented letters of its messages
  cannot break it.

    pypy3 kof95_cart.py "path/to/King of Fighters '95.cue" path/to/mpr-18811-mx.ic1 path/to/kof95.zip out

## 2.0.0-beta.1 - 2026-11-14

**One version only**: the Neo Geo arcade sound on the Saturn, with no loading. `kof95_cart.py` now builds a single 48 MiB
image; the 1.x variants (`noloading`, `pure`) stay available in the 1.1.0 release.

New input: your dump of the **Neo Geo MVS ROM set** `kof95.zip` (MAME name `kof95`). The music and the sound effects are
taken from it on your machine; nothing from the game is included in the script.

- **Arcade music**: the 23 pieces of the Neo Geo version, played from the cartridge by a new music player on the Saturn's
  second processor. The CD is no longer needed at all.
- **Arcade sound effects and voices** in place of the Saturn ones.
- **The sound of the AES console's headphone output**, on the music and the sound effects alike.
- **Sound in time with the picture**, as on the arcade board.
- **Controls answer one frame earlier** than on the original Saturn version.
- **Animated team-order screen**: the character being chosen moves, as on the arcade version.
- **Fix**: wrong sprites on the team-order screen of the Team Edit mode, from the second match on.
- Slowdowns in fights: about 1 frame in 2,500, as in 1.1.0.

MiSTer: needs the modified Saturn core [Saturn_MiSTer_Cart](https://github.com/YudoMatso/Saturn_MiSTer_Cart) v1.1.0 or later,
"ROM 32/48M" cartridge mode.

Beta: tested in Mednafen and on MiSTer by automated runs and by hand. 48 MiB is more than any known
Saturn flash cartridge. The build takes from about 15 minutes to 2 hours depending on the processor (the music is rebuilt
by an emulated Z80).

    python3 kof95_cart.py "path/to/King of Fighters '95.cue" path/to/mpr-18811-mx.ic1 path/to/kof95.zip out

## 1.1.0 - 2026-11-04

**`noloading`** is now built by default: no need to enter the variant in the Python command (add `pure` for the other one).

- **Team-order screen taunts are back**, as on the arcade version, without any arcade data.
- **All graphics are stored uncompressed** on the cartridge, like on the Neo Geo: nothing is decompressed during play.
- **Fewer slowdowns**: about 1 frame in 2,500 in fights (arcade: 1 in 1,000).
- **Exactly 32 MiB**: the `.ss` and MiSTer `_32M.bin` files are now identical.

## 1.0.0 - 2026-11-03

First public release. One Python script, kof95_cart.py (attached), builds two variants of the cartridge image from your own dumps of the disc and of the mpr-18811 cartridge. Python 3.8+ only.

**noloading**: the Saturn version plays like the Neo Geo arcade version:
- No more "NOW LOADING" before fights: the next fight appears as fast as on the arcade board (identical timing on 7 stages out of 8).
- The music starts with the fight and keeps playing between rounds.
- No loading screen at start-up, and a much shorter boot.
- Slowdowns in fights stay rare: about 1 frame in 100 (original CD: 1 in 300, arcade: 1 in 1,000).
- Tested in Mednafen and on MiSTer.

    python3 kof95_cart.py noloading "path/to/King of Fighters '95.cue" path/to/mpr-18811-mx.ic1 out

**pure**: the original game, untouched, running entirely from the cartridge (team screen → fight in about 1.5 s instead of about 6 s on CD). Tested in Mednafen, not on MiSTer.

    python3 kof95_cart.py pure "path/to/King of Fighters '95.cue" path/to/mpr-18811-mx.ic1 out

Each build checks its result against the reference images. The MiSTer image needs the modified "ROM 32M" core: https://github.com/YudoMatso/Saturn_MiSTer_Cart. No game data is included: the image is built on your machine from your dumps. See the README.
