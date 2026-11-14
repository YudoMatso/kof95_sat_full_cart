# Changelog

Versions follow `major.minor.patch`: patch = fix, minor = addition that breaks nothing, major = big change.

## 2.0.0-beta.1 — 2026-11-14 (pre-release)

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

## 1.1.0 — 2026-11-04

**`noloading`** is now built by default: no need to enter the variant in the Python command (add `pure` for the other one).

- **Team-order screen taunts are back**, as on the arcade version, without any arcade data.
- **All graphics are stored uncompressed** on the cartridge, like on the Neo Geo: nothing is decompressed during play.
- **Fewer slowdowns**: about 1 frame in 2,500 in fights (arcade: 1 in 1,000).
- **Exactly 32 MiB**: the `.ss` and MiSTer `_32M.bin` files are now identical.

## 1.0.0 — 2026-11-03

First public release. One Python script, kof95_cart.py (attached), builds two variants of the cartridge image from your own dumps of the disc and of the mpr-18811 cartridge. Python 3.8+ only.

**noloading** — the Saturn version plays like the Neo Geo arcade version:
- No more "NOW LOADING" before fights: the next fight appears as fast as on the arcade board (identical timing on 7 stages out of 8).
- The music starts with the fight and keeps playing between rounds.
- No loading screen at start-up, and a much shorter boot.
- Slowdowns in fights stay rare: about 1 frame in 100 (original CD: 1 in 300, arcade: 1 in 1,000).
- Tested in Mednafen and on MiSTer.

    python3 kof95_cart.py noloading "path/to/King of Fighters '95.cue" path/to/mpr-18811-mx.ic1 out

**pure** — the original game, untouched, running entirely from the cartridge (team screen → fight in about 1.5 s instead of about 6 s on CD). Tested in Mednafen, not on MiSTer.

    python3 kof95_cart.py pure "path/to/King of Fighters '95.cue" path/to/mpr-18811-mx.ic1 out

Each build checks its result against the reference images. The MiSTer image needs the modified "ROM 32M" core: https://github.com/YudoMatso/Saturn_MiSTer_Cart. No game data is included: the image is built on your machine from your dumps. See the README.
