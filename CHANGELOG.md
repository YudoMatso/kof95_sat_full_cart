# Changelog

## v2.0 — No loading (2026-11-03)

The full result of the project: the Saturn version plays like the Neo Geo arcade version.

- **No more "NOW LOADING" before fights.** The next fight appears as fast as on the arcade board (identical timing on 7 stages out of 8).
- **The music starts with the fight** and **keeps playing between rounds**, instead of stopping and restarting.
- **No loading screen at start-up**, and a much shorter boot.
- Data that the original game prepared on the fly (stage graphics, voice samples) is now prepared in advance and stored on the cartridge, or loaded in the background while the "VS" screen is shown.
- Measured: slowdowns in fights stay rare, about 1 frame in 100 (original CD: 1 in 300, arcade: 1 in 1,000), almost always a single 1/60 s frame.
- Tested in Mednafen and on MiSTer.

## v1.0 — Pure (2026-10-25)

The original Saturn game, untouched, but running entirely from a cartridge.

- **The whole game is on the cartridge**; the CD is only used for the music.
- The game reads its files from the cartridge instead of the CD drive: going from the team screen to the fight takes about 1.5 seconds instead of about 6 seconds on CD.
- Everything else is the original game: same menus, same timing, same waits.
- Tested in Mednafen (attract mode and played matches). Not tested on MiSTer.
