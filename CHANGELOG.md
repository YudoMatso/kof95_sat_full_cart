# Changelog

Versions follow `major.minor.patch`: patch = fix, minor = addition that breaks nothing, major = big change.

## 1.1.0 — 2026-11-04

**`noloading`** gets closer to the arcade version, and is now built differently. `pure` is unchanged.

- **Team-order screen taunts, as on the arcade version.** When a team has chosen its fighting order, its three characters now do their taunt animation, then go back to their stance. The Saturn release had dropped them. The wait on that screen is now the same length as on the arcade version, and the music and the start of the fight are still in sync. No data from the arcade version is used: the animations were still in the Saturn game files, and only about 7 KiB were added to point to them.
- **All the graphics are now stored uncompressed on the cartridge, like on the Neo Geo.** The game never has to decompress anything while you play. The original Saturn game unpacked its graphics with the CPU, and that work was the main cause of the slowdowns that were left.
- **Fewer slowdowns**: about 1 frame lost in 2,500 in fights (1.0.0: 1 in 100; original CD: 1 in 300; arcade: 1 in 1,000), measured in an emulator.
- **The image is exactly 32 MiB**, the most the Saturn's cartridge port can address in one go. Repeated data and data the game never reads (duplicate files, unused sound samples) were removed to make room. The `.ss` file and the MiSTer `_32M.bin` file are now identical.
- The build takes about a minute and uses several CPU cores.
- **`noloading` is now the default variant**: `python3 kof95_cart.py <disc.cue> <mpr-18811-mx.ic1> [output_dir]` builds it. Add `pure` before the disc for the pure variant; the 1.0.0 commands still work.
- Tested in Mednafen and on MiSTer.

## 1.0.0 — 2026-11-03

First public release. `kof95_cart.py` builds two variants of the cartridge image from your own dumps, and checks each result against the reference images.

**`noloading`**: the Saturn version plays like the Neo Geo arcade version.

- **No more "NOW LOADING" before fights.** The next fight appears as fast as on the arcade board (identical timing on 7 stages out of 8).
- **The music starts with the fight** and **keeps playing between rounds**, instead of stopping and restarting.
- **No loading screen at start-up**, and a much shorter boot.
- Data that the original game prepared on the fly (stage graphics, voice samples) is now prepared in advance and stored on the cartridge, or loaded in the background while the "VS" screen is shown.
- Slowdowns in fights stay rare: about 1 frame in 100 (original CD: 1 in 300, arcade: 1 in 1,000), almost always a single 1/60 s frame.
- Tested in Mednafen and on MiSTer.

**`pure`**: the original Saturn game, untouched, running entirely from the cartridge.

- The whole game is on the cartridge; the CD is only used for the music.
- Going from the team screen to the fight takes about 1.5 seconds instead of about 6 seconds on CD.
- Everything else is the original game: same menus, same timing, same waits.
- Tested in Mednafen. Not tested on MiSTer.
