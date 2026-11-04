# Changelog

Versions follow `major.minor.patch`: patch = fix, minor = addition that breaks nothing, major = big change.

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
