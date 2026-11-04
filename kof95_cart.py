#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 YudoMatso. https://github.com/YudoMatso/kof95_sat_full_cart
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY; see the LICENSE file or
# <https://www.gnu.org/licenses/>.
"""The King of Fighters '95 (Sega Saturn) - cartridge edition builder.

Builds a Saturn cartridge image holding the whole game, from your own dumps:

    python3 kof95_cart.py [variant] <disc.cue> <mpr-18811-mx.ic1> [output_dir]

    variant   pure | noloading (default: noloading)
              pure       the original game, unchanged, running from the cartridge
              noloading  no loading screens, arcade timing, music kept between rounds,
                         order-screen taunts as on the arcade version

    disc.cue           The King of Fighters '95 (Japan), T-3101G, cue sheet with its .bin tracks
    mpr-18811-mx.ic1   the 2 MiB ROM cartridge sold with the game

Writes kof95_cart_<variant>.ss (Mednafen) and kof95_cart_<variant>_32M.bin (MiSTer, "ROM 32M" core),
then checks them against the reference SHA-256. Needs Python 3.8 or later, nothing else.

This file contains only original code: the build modules and the assembled SH-2 code of the
project. No data from the game is included; everything is taken from your dumps at build time.
"""
import base64, contextlib, hashlib, importlib, io, os, sys, tempfile, zlib

VERSIONS = {}

VERSIONS['pure'] = dict(
    sha=('1dc75a62b82617dc9daa4c14a880af98f18ed368560d0c9678e5afd361c13cf5', 'ef17e95a6d5aa267be2ad8a6948d3024224c104ffa348d67181282fc31eeb7bb'),
    boot='''
eNq7yD6BW5HxIvsl9sscCWLOAkpM/b+LWC6wOGgzcP6/z8Cp2snAoeRwgoGN/WwDA4P6FQBvFQ5z
''',
    elf='''
eNrNVc1PE0EUf9st212KpmwC1nApRQgaQltb5CAm3ZSSEEsgNFGCJrtLacHYprVdGlGMHrg0PRATjh64eTGRgwcOHDhgwrFw0YOH
jX+BJqQXD/XNzmxZCRcv6Etn3vzee/Nm5n10XydTU5yLgza54BbOnCBGD5DHAATDksYgADwMgwgeosefW/A0NslAPMlGB443TH9A
fFA/3BwdTj1vCOLiKRmIJ9iw9ZdKod7jTl1udEaEmvdY0mXFr4gKNMRIV0MMyCaAV2+aLTKDJHhOPwD8AOS7wbtzyBuH8A9JS8T9
cTEOx3yk64QPLsnd8jx4TbDuJkbNFhL8p5TsqfedBLVgOF6/lg4m/AkxAdH5GmSjqLn69k7ksXJdkRQuHYz65dsP+2leIhs7Lrmb
vDH0QMsEXh7xtStHXL1XTytcv78ma2uKb4jb+lV1mdyOd1BCuYRyQaui3IVyt8kPSoMLNbdmJH1DgBIOvFrT0yLxuox3zwZDvaEH
oVyoqg0E7h/xW6L5/YtnpTyeykYbQtybGzBhpZlrZpt6c3YIvCCRumscCmJs/yJ/rAexPcFqZNa7BLsojm0wzFNs9RwBbmB7CLmh
9ROZRGqHkoVlUu8O3E97oI1vkl5w4DCe/7X9bwIwjvibA08I4lgXw+Q+CcSdDjyN72H+rLulEX9yYBXxngOvIt534GeIDxz4lSA+
Gm4/EWAT8YgD1+24+uj523a8GH5nx8tH7St2z/uo//d2vH30fR/tOmJ4z86PZZ9ZLhcLo0WYn51Rp5TJMKRnlFRKnZpOJdUZZQFS
U2p6ejFJOKohpeb05TCyasma1DKy8VwO53xOrTx5kcVVpaDn82pBf06luIPtUzO4yOiZ1axaKVtrxoqldcB70AXxmsU91NAWlfK6
xSuGbmSZLl8sPl0rAYxW1guGvoTcKFO+aq9K9DyysDyMMudEYbn+K+pjORRoDDk3+86AI3+EbrTt6PeG5GPkAruRMzuSYxfJ8/YF
drEzO5J73mDfp/N2HKtpu3x32dkCjh5m5yM9xWqbUQfGED47/Nk92P2nnTCG073zdr8BVk/8xA==
''',
    modules={
        'inventory_disc': r'''#!/usr/bin/env python3
"""List files in the first Mode 1/2352 track of a cue/bin disc image."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RAW_SECTOR_SIZE = 2352
USER_DATA_OFFSET = 16
LOGICAL_SECTOR_SIZE = 2048


class DiscError(Exception):
    pass


def read_le_be(data: bytes, offset: int, width: int) -> int:
    little = int.from_bytes(data[offset : offset + width], "little")
    big = int.from_bytes(data[offset + width : offset + width * 2], "big")
    if little != big:
        raise DiscError(f"invalid dual-endian ISO field at byte {offset}")
    return little


def parse_record(record: bytes) -> tuple[int, int, int, bytes]:
    if len(record) < 34 or record[0] < 34 or record[0] > len(record):
        raise DiscError("invalid ISO9660 directory record")
    record = record[: record[0]]
    name_length = record[32]
    if 33 + name_length > len(record):
        raise DiscError("truncated ISO9660 directory name")
    extent = read_le_be(record, 2, 4)
    size = read_le_be(record, 10, 4)
    return extent, size, record[25], record[33 : 33 + name_length]


def cue_data_track(cue_path: Path) -> Path:
    cue_text = cue_path.read_text(encoding="utf-8", errors="replace")
    current_file: str | None = None
    for line in cue_text.splitlines():
        file_match = re.match(r'\s*FILE\s+"([^"]+)"\s+\w+', line, re.IGNORECASE)
        if file_match:
            current_file = file_match.group(1)
            continue
        track_match = re.match(r"\s*TRACK\s+\d+\s+(MODE1/2352)\b", line, re.IGNORECASE)
        if track_match and current_file:
            track_path = cue_path.parent / current_file
            if not track_path.is_file():
                raise DiscError(f"data track not found: {track_path}")
            return track_path
    raise DiscError(f"no MODE1/2352 track found in {cue_path}")


class Iso9660:
    def __init__(self, track_path: Path):
        self.track_path = track_path
        self.track = track_path.open("rb")
        track_size = track_path.stat().st_size
        if track_size % RAW_SECTOR_SIZE:
            raise DiscError(f"track size is not a multiple of {RAW_SECTOR_SIZE}")
        self.sector_count = track_size // RAW_SECTOR_SIZE
        self._validate_volume()

    def close(self) -> None:
        self.track.close()

    def read_sector(self, lba: int) -> bytes:
        if lba < 0 or lba >= self.sector_count:
            raise DiscError(f"sector {lba} is outside the data track")
        self.track.seek(lba * RAW_SECTOR_SIZE + USER_DATA_OFFSET)
        data = self.track.read(LOGICAL_SECTOR_SIZE)
        if len(data) != LOGICAL_SECTOR_SIZE:
            raise DiscError(f"short read at sector {lba}")
        return data

    def read_extent(self, lba: int, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            result.extend(self.read_sector(lba))
            lba += 1
        return bytes(result[:size])

    def _validate_volume(self) -> None:
        primary = None
        for lba in range(16, min(self.sector_count, 80)):
            descriptor = self.read_sector(lba)
            if descriptor[1:6] != b"CD001" or descriptor[6] != 1:
                raise DiscError(f"invalid volume descriptor at sector {lba}")
            if descriptor[0] == 1:
                primary = descriptor
            if descriptor[0] == 255:
                break
        if primary is None:
            raise DiscError("no ISO9660 primary volume descriptor found")
        self.root = parse_record(primary[156:])[:2]

    @staticmethod
    def _display_name(raw_name: bytes) -> str:
        name = raw_name.decode("ascii", errors="replace")
        if name.endswith("."):
            name = name[:-1]
        return re.sub(r";\d+$", "", name)

    def files(self) -> list[tuple[str, int, int]]:
        result: list[tuple[str, int, int]] = []
        visited: set[tuple[int, int]] = set()

        def walk(path: str, extent: int, size: int) -> None:
            key = (extent, size)
            if key in visited:
                raise DiscError(f"directory cycle at {path or '/'}")
            visited.add(key)
            directory = self.read_extent(extent, size)
            offset = 0
            while offset < len(directory):
                record_size = directory[offset]
                if record_size == 0:
                    offset = ((offset // LOGICAL_SECTOR_SIZE) + 1) * LOGICAL_SECTOR_SIZE
                    continue
                record = directory[offset : offset + record_size]
                child_extent, child_size, flags, raw_name = parse_record(record)
                offset += record_size
                if raw_name in (b"\x00", b"\x01"):
                    continue
                name = self._display_name(raw_name)
                child_path = f"{path}/{name}" if path else name
                if flags & 0x02:
                    walk(child_path, child_extent, child_size)
                else:
                    result.append((child_path, child_size, child_extent))

        root_extent, root_size = self.root
        walk("", root_extent, root_size)
        return sorted(result, key=lambda item: item[0].casefold())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cue", type=Path, help="cue sheet containing a MODE1/2352 track")
    args = parser.parse_args()

    track_path = cue_data_track(args.cue)
    iso = Iso9660(track_path)
    try:
        print(f"Cue: {args.cue}")
        print(f"Track: {track_path} ({iso.sector_count} raw sectors)")
        print("Size (bytes)\tLBA\tPath")
        files = iso.files()
        for path, size, lba in files:
            print(f"{size}\t{lba}\t{path}")
        total = sum(size for _, size, _ in files)
        print(f"Files: {len(files)}; payload total: {total} bytes")
    finally:
        iso.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DiscError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)''',
        'build_cart': r'''#!/usr/bin/env python3
"""Build a bootable Saturn cart image (.ss) and the file -> ROM offset table.

Layout (offsets from the start of CS0, 0x22000000 cache-through):
  0x000000  boot area: IP from the disc (header + security code + area code),
            then the payload program right after the IP
  0x200000  original cart ROM (mpr-18811), 2 MiB, unchanged
  0x400000  whole data track as a 2048-byte-sector image: ROM = 0x400000 + LBA * 2048

The BIOS only boots a cart whose first 16 bytes are "SEGA SEGASATURN ", so the
original ROM ("SEGASATURN DATA ...", data from 0x100 onwards) cannot stay at 0.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

from inventory_disc import LOGICAL_SECTOR_SIZE, DiscError, Iso9660, cue_data_track

CS0_BASE = 0x22000000
BOOT_OFFSET = 0x000000
BOOT_AREA_SIZE = 0x200000
CART_ROM_OFFSET = 0x200000
CART_ROM_SIZE = 0x200000
ISO_OFFSET = 0x400000
CS0_SIZE = 0x2000000

IP_SIZE_FIELD = 0xE0
FIRST_READ_ADDR_FIELD = 0xF0
SECURITY_RANGE = (0x100, 0xE00)
# SHA-256 of the genuine security code, as checked by Mednafen (ss.cpp, IsSaturnDisc).
SECURITY_SHA256 = "96b8ea48819cfa589f24c40aa149c224c420dccf38b730f00156efe25c9bbc8f"
# Japanese area code block: "bra; nop; 'For JAPAN.'", then a jump to the first-read address.
AREA_JUMP_CODE = bytes.fromhex("d001402b00090000")
AREA_JUMP_OFFSET = 0xE20


def read_ip(iso: Iso9660) -> bytearray:
    head = iso.read_sector(0)
    if head[:16] != b"SEGA SEGASATURN ":
        raise DiscError("sector 0 is not a Saturn IP")
    ip_size = int.from_bytes(head[IP_SIZE_FIELD : IP_SIZE_FIELD + 4], "big")
    if not 0x1000 <= ip_size <= 0x8000:
        raise DiscError(f"IP size 0x{ip_size:X} outside the BIOS limits 0x1000-0x8000")
    ip = bytearray(iso.read_extent(0, ip_size))
    start, end = SECURITY_RANGE
    if hashlib.sha256(ip[start:end]).hexdigest() != SECURITY_SHA256:
        raise DiscError("IP security code does not match the genuine one")
    return ip


def retarget_area_jump(ip: bytearray, entry: int) -> int:
    """Point the area code's final jump at `entry`; return the previous target."""
    code = ip[AREA_JUMP_OFFSET : AREA_JUMP_OFFSET + len(AREA_JUMP_CODE)]
    if code != AREA_JUMP_CODE:
        raise DiscError("unexpected area code layout, cannot retarget its jump")
    literal = AREA_JUMP_OFFSET + len(AREA_JUMP_CODE)
    previous = int.from_bytes(ip[literal : literal + 4], "big")
    ip[literal : literal + 4] = entry.to_bytes(4, "big")
    return previous


def build_boot_area(ip: bytearray, payload: bytes, run_from_cart: bool) -> bytes:
    payload_offset = len(ip)
    if run_from_cart:
        retarget_area_jump(ip, CS0_BASE + BOOT_OFFSET + payload_offset)
    boot = bytes(ip) + payload
    if len(boot) > BOOT_AREA_SIZE:
        raise DiscError(f"boot area is 0x{len(boot):X} bytes, limit 0x{BOOT_AREA_SIZE:X}")
    return boot


def replace_files(image: bytearray, files: list[tuple[str, int, int]], replacements: list[str]) -> list[str]:
    """Overwrite disc files in the data-track part of the image (same size only)."""
    by_name = {name: (size, lba) for name, size, lba in files}
    log = []
    for spec in replacements:
        name, sep, source = spec.partition("=")
        if not sep or name not in by_name:
            raise DiscError(f"--replace {spec}: expected NAME=FILE with NAME a file of the disc")
        size, lba = by_name[name]
        data = Path(source).read_bytes()
        if len(data) != size:
            raise DiscError(f"--replace {name}: {len(data)} bytes, the disc file has {size}")
        offset = ISO_OFFSET + lba * LOGICAL_SECTOR_SIZE
        image[offset : offset + size] = data
        log.append(f"{name} replaced by {source} at cart 0x{CS0_BASE + offset:08X}")
    return log


def write_table(path: Path, files: list[tuple[str, int, int]]) -> None:
    with path.open("w", newline="") as out:
        writer = csv.writer(out, delimiter="\t", lineterminator="\n")
        writer.writerow(["path", "lba", "size", "rom_offset", "cs0_address"])
        for name, size, lba in sorted(files, key=lambda item: item[2]):
            offset = ISO_OFFSET + lba * LOGICAL_SECTOR_SIZE
            writer.writerow([name, lba, size, f"0x{offset:07X}", f"0x{CS0_BASE + offset:08X}"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cue", type=Path, help="cue sheet of the KOF95 disc")
    parser.add_argument("cart_rom", type=Path, help="mpr-18811 dump (2 MiB)")
    parser.add_argument("payload", type=Path, help="program placed right after the IP")
    parser.add_argument("output", type=Path, help="output .ss image")
    parser.add_argument("--table", type=Path, help="write the file -> ROM offset table (TSV)")
    parser.add_argument("--minimal", action="store_true", help="boot area only (no cart ROM, no disc data)")
    parser.add_argument(
        "--run-from-cart",
        action="store_true",
        help="make the area code jump into the payload in the cart instead of the IP first-read address",
    )
    parser.add_argument(
        "--replace",
        action="append",
        default=[],
        metavar="NAME=FILE",
        help="replace a disc file in the data-track part of the image (same size), repeatable",
    )
    args = parser.parse_args()
    if args.minimal and args.replace:
        parser.error("--replace needs the data track, not --minimal")

    iso = Iso9660(cue_data_track(args.cue))
    try:
        ip = read_ip(iso)
        boot = build_boot_area(ip, args.payload.read_bytes(), args.run_from_cart)
        if args.minimal:
            image = bytearray(boot)
        else:
            cart_rom = args.cart_rom.read_bytes()
            if len(cart_rom) != CART_ROM_SIZE:
                raise DiscError(f"cart ROM is {len(cart_rom)} bytes, expected {CART_ROM_SIZE}")
            iso_size = iso.sector_count * LOGICAL_SECTOR_SIZE
            if ISO_OFFSET + iso_size > CS0_SIZE:
                raise DiscError("disc data does not fit in CS0")
            image = bytearray(ISO_OFFSET + iso_size)
            image[BOOT_OFFSET : BOOT_OFFSET + len(boot)] = boot
            image[CART_ROM_OFFSET : CART_ROM_OFFSET + CART_ROM_SIZE] = cart_rom
            image[ISO_OFFSET:] = iso.read_extent(0, iso_size)
        files = iso.files()
        replaced = replace_files(image, files, args.replace)
        if args.table:
            write_table(args.table, files)
    finally:
        iso.close()

    # 16-bit ROM: keep the image an even number of bytes.
    if len(image) % 2:
        image.append(0)
    args.output.write_bytes(image)
    for line in replaced:
        print(line)
    entry = int.from_bytes(ip[FIRST_READ_ADDR_FIELD : FIRST_READ_ADDR_FIELD + 4], "big")
    print(f"{args.output}: {len(image)} bytes (0x{len(image):X}), IP 0x{len(ip):X} bytes, "
          f"payload at cart 0x{CS0_BASE + len(ip):08X}, IP first-read address 0x{entry:08X}"
          + (" (bypassed)" if args.run_from_cart else ""))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DiscError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
''',
        'patch_kof95': r'''#!/usr/bin/env python3
"""Patch the two KOF95 programs for the all-cart image.

  `0`     : the CD data-read primitives are overwritten by the sections of
            build/cdrom.elf (src/cdrom), each one inside the window of the
            function it replaces.
  MM.BIN  : the accesses to the original cart ROM (mpr-18811) are moved by
            +0x200000, where build_cart.py places it: 28 literal-pool words,
            a pointer split in two 16-bit literals, the ENE_MV/ENE_DT
            pointer table, two PRS pointers and the ROM build list
            (docs/phase1_step5_patch.md).

Both files are read from the disc (cue sheet) and checked by SHA-256, every
patched word is checked against its expected original value.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

from inventory_disc import DiscError, Iso9660, cue_data_track

ZERO_BASE = 0x0607CD80
MM_BASE = 0x06002040
ZERO_SHA256 = "25cf3d668ca28b766ce984049225c2558bf697a64c93d3cf60d29866b51c007a"
MM_SHA256 = "ab938524fd6f3d2012db8e99096e3da66cd51a8dbb59a57c8859a48168d3076f"

ROM_SHIFT = 0x200000
CART_ROM_START, CART_ROM_END = 0x22000000, 0x22200000
ROM_BIAS_68K = 0x21F80100  # 68k address -> ROM, (A & 0xFFFFFF) + bias

# Functions of `0` that may be overwritten: (name, start, end).
ZERO_WINDOWS = [
    ("cache lookup", 0x0607D084, 0x0607D0DC),
    ("play (Set CD Device Connection + Play Disc)", 0x060833C0, 0x0608347C),
    ("read (Get Then Delete Sector Data loop)", 0x0608347C, 0x06083558),
    ("copy from cache partition", 0x06085AF4, 0x06085B34),
]

# MM.BIN literal-pool words loaded by the code (docs/phase1_step4_code.md, 2.3).
MM_POOL_WORDS = {
    0x06002280: 0x2216D080, 0x06002304: 0x22000000, 0x06002310: 0x220000E4,
    0x06002368: 0x22000100, 0x06007844: 0x220D1488, 0x0600B2FC: 0x2208E4D0,
    0x0600BD30: 0x2208E2D0, 0x0600CD34: 0x2208D2D0, 0x0600CD38: 0x2208C2D0,
    0x0600CF60: 0x22091D30, 0x0600D174: 0x220A14F0, 0x0600D290: 0x220A16F0,
    0x0600D68C: 0x22091CF0, 0x0600D884: 0x22091CF2, 0x0600DAC0: 0x22091CF0,
    0x0600DEA0: 0x22091CF0, 0x0600E688: 0x22091CF0, 0x0600E8CC: 0x22091CF0,
    0x0600EC2C: 0x22091CF0, 0x0600F894: 0x22000180, 0x0600F898: 0x22000100,
    0x0600FB04: 0x2208E5D0, 0x0600FB90: ROM_BIAS_68K, 0x06010104: ROM_BIAS_68K,
    0x0604977C: 0x2216D080, 0x0604A2F8: 0x2216D080, 0x0604A3BC: 0x2216D080,
    0x0604A584: 0x2216D080,
}
# Pointers stored in MM.BIN data.
MM_DATA_WORDS = {
    0x060071A0: 0x220D1488,  # 003F.PRS+8, PRS decompression structure
    0x06007210: 0x22153888,  # 2009.PRS+8, idem
}
# Pointers split by the 68k translator into two 16-bit literals, each loaded by
# mov.w @(disp,PC): address of the high half -> (high, low). Only the high half moves.
MM_SPLIT_POINTERS = {
    0x0600A194: (0x220A, 0x1CF0),  # BACK.BIN, loaded at 0x0600A178/0x0600A17A
}
# Table of 234 pointers to ENE_MV.DAT / ENE_DT.DAT records (code loads
# 0x0605CE6C and 0x0605CED4 as bases).
MM_ENE_TABLE = (0x0605CE6C, 234, 0x22080100, 0x2208C2D0)
# ROM build list ("ROMHEAD.BIN" -> 0x22000000, ...), destinations of LoadFile.
MM_BUILD_LIST = {
    0x0605E214: 0x22000000, 0x0605E222: 0x22000100, 0x0605E236: 0x220CB0F0,
    0x0605E248: 0x22080100, 0x0605E25A: 0x22086900, 0x0605E274: 0x2208C2D0,
    0x0605E284: 0x22091CF0, 0x0605E294: 0x220A1CF0, 0x0605E2A6: 0x2208E5D0,
    0x0605E2B6: 0x220D1480, 0x0605E2C6: 0x22153880, 0x0605E2D6: 0x2216D080,
}


def elf_sections(path: Path) -> list[tuple[str, int, bytes]]:
    """Allocated PROGBITS sections of a 32-bit big-endian ELF: (name, address, data)."""
    elf = path.read_bytes()
    if elf[:4] != b"\x7fELF" or elf[4] != 1 or elf[5] != 2:
        raise DiscError(f"{path}: not a 32-bit big-endian ELF")
    shoff, = struct.unpack_from(">I", elf, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from(">HHH", elf, 0x2E)
    headers = [struct.unpack_from(">IIIIIIIIII", elf, shoff + i * shentsize) for i in range(shnum)]
    strtab = headers[shstrndx]
    result = []
    for name, kind, flags, addr, offset, size, *_ in headers:
        if kind == 1 and flags & 2 and size:  # SHT_PROGBITS, SHF_ALLOC
            label = elf[strtab[4] + name : elf.index(b"\0", strtab[4] + name)].decode()
            result.append((label, addr, elf[offset : offset + size]))
    return result


def patch_zero(zero: bytearray, sections: list[tuple[str, int, bytes]]) -> list[str]:
    log = []
    for name, addr, data in sections:
        window = next((w for w in ZERO_WINDOWS if w[1] <= addr and addr + len(data) <= w[2]), None)
        if window is None:
            raise DiscError(f"section {name} at 0x{addr:08X} (+0x{len(data):X}) is outside the allowed windows")
        offset = addr - ZERO_BASE
        zero[offset : offset + len(data)] = data
        log.append(f"0  0x{addr:08X} {name:9} 0x{len(data):03X}/0x{window[2] - window[1]:03X} bytes  {window[0]}")
    return log


def shift_word(mm: bytearray, addr: int, expected: int | None = None, bounds: tuple[int, int] | None = None) -> int:
    offset = addr - MM_BASE
    value, = struct.unpack_from(">I", mm, offset)
    if expected is not None and value != expected:
        raise DiscError(f"MM.BIN 0x{addr:08X}: 0x{value:08X}, expected 0x{expected:08X}")
    if bounds is not None and not bounds[0] <= value < bounds[1]:
        raise DiscError(f"MM.BIN 0x{addr:08X}: 0x{value:08X} outside 0x{bounds[0]:08X}-0x{bounds[1]:08X}")
    struct.pack_into(">I", mm, offset, value + ROM_SHIFT)
    return value


def patch_mm(mm: bytearray) -> list[str]:
    for addr, value in MM_POOL_WORDS.items():
        shift_word(mm, addr, value)
    for addr, (high, low) in MM_SPLIT_POINTERS.items():
        shift_word(mm, addr, high << 16 | low)
    for addr, value in MM_DATA_WORDS.items():
        shift_word(mm, addr, value)
    start, count, low, high = MM_ENE_TABLE
    for index in range(count):
        shift_word(mm, start + 4 * index, bounds=(low, high))
    for addr, value in MM_BUILD_LIST.items():
        shift_word(mm, addr, value)
    return [
        f"MM.BIN {len(MM_POOL_WORDS)} literal-pool words, {len(MM_SPLIT_POINTERS)} split pointer, "
        f"{len(MM_DATA_WORDS)} PRS pointers, "
        f"{count} table entries at 0x{start:08X}, {len(MM_BUILD_LIST)} build-list entries: +0x{ROM_SHIFT:X}"
    ]


def read_file(iso: Iso9660, name: str, sha256: str) -> bytearray:
    entry = next(((size, lba) for path, size, lba in iso.files() if path == name), None)
    if entry is None:
        raise DiscError(f"{name} not found on the disc")
    data = bytearray(iso.read_extent(entry[1], entry[0]))
    if hashlib.sha256(data).hexdigest() != sha256:
        raise DiscError(f"{name}: SHA-256 differs from the analysed version")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cue", type=Path, help="cue sheet of the KOF95 disc")
    parser.add_argument("elf", type=Path, help="replacement code (build/cdrom.elf)")
    parser.add_argument("out_dir", type=Path, help="directory for the patched `0` and MM.BIN")
    args = parser.parse_args()

    iso = Iso9660(cue_data_track(args.cue))
    try:
        zero = read_file(iso, "0", ZERO_SHA256)
        mm = read_file(iso, "MM.BIN", MM_SHA256)
    finally:
        iso.close()

    log = patch_zero(zero, elf_sections(args.elf)) + patch_mm(mm)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "0").write_bytes(zero)
    (args.out_dir / "MM.BIN").write_bytes(mm)
    print("\n".join(log))
    print(f"-> {args.out_dir / '0'}, {args.out_dir / 'MM.BIN'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DiscError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
''',
    },
)

VERSIONS['noloading'] = dict(
    sha=('6e8e55c433accdf24612097780e1d9c8932deb0d15c7a0637bc8e52d625d2c91', '6e8e55c433accdf24612097780e1d9c8932deb0d15c7a0637bc8e52d625d2c91'),
    boot='''
eNoBPADD/9EM0A0hAtEHkAshAdEG0gfTB2AWQxAiAo/7cgTQA0ArAAn/3yWJAAgiQMgABgfNgAAAJ9Ql/gCwFEAf8EgxE3o=
''',
    elf='''
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
''',
    modules={
        'inventory_disc': r'''#!/usr/bin/env python3
"""List files in the first Mode 1/2352 track of a cue/bin disc image."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RAW_SECTOR_SIZE = 2352
USER_DATA_OFFSET = 16
LOGICAL_SECTOR_SIZE = 2048


class DiscError(Exception):
    pass


def read_le_be(data: bytes, offset: int, width: int) -> int:
    little = int.from_bytes(data[offset : offset + width], "little")
    big = int.from_bytes(data[offset + width : offset + width * 2], "big")
    if little != big:
        raise DiscError(f"invalid dual-endian ISO field at byte {offset}")
    return little


def parse_record(record: bytes) -> tuple[int, int, int, bytes]:
    if len(record) < 34 or record[0] < 34 or record[0] > len(record):
        raise DiscError("invalid ISO9660 directory record")
    record = record[: record[0]]
    name_length = record[32]
    if 33 + name_length > len(record):
        raise DiscError("truncated ISO9660 directory name")
    extent = read_le_be(record, 2, 4)
    size = read_le_be(record, 10, 4)
    return extent, size, record[25], record[33 : 33 + name_length]


def cue_data_track(cue_path: Path) -> Path:
    cue_text = cue_path.read_text(encoding="utf-8", errors="replace")
    current_file: str | None = None
    for line in cue_text.splitlines():
        file_match = re.match(r'\s*FILE\s+"([^"]+)"\s+\w+', line, re.IGNORECASE)
        if file_match:
            current_file = file_match.group(1)
            continue
        track_match = re.match(r"\s*TRACK\s+\d+\s+(MODE1/2352)\b", line, re.IGNORECASE)
        if track_match and current_file:
            track_path = cue_path.parent / current_file
            if not track_path.is_file():
                raise DiscError(f"data track not found: {track_path}")
            return track_path
    raise DiscError(f"no MODE1/2352 track found in {cue_path}")


class Iso9660:
    def __init__(self, track_path: Path):
        self.track_path = track_path
        self.track = track_path.open("rb")
        track_size = track_path.stat().st_size
        if track_size % RAW_SECTOR_SIZE:
            raise DiscError(f"track size is not a multiple of {RAW_SECTOR_SIZE}")
        self.sector_count = track_size // RAW_SECTOR_SIZE
        self._validate_volume()

    def close(self) -> None:
        self.track.close()

    def read_sector(self, lba: int) -> bytes:
        if lba < 0 or lba >= self.sector_count:
            raise DiscError(f"sector {lba} is outside the data track")
        self.track.seek(lba * RAW_SECTOR_SIZE + USER_DATA_OFFSET)
        data = self.track.read(LOGICAL_SECTOR_SIZE)
        if len(data) != LOGICAL_SECTOR_SIZE:
            raise DiscError(f"short read at sector {lba}")
        return data

    def read_extent(self, lba: int, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            result.extend(self.read_sector(lba))
            lba += 1
        return bytes(result[:size])

    def _validate_volume(self) -> None:
        primary = None
        for lba in range(16, min(self.sector_count, 80)):
            descriptor = self.read_sector(lba)
            if descriptor[1:6] != b"CD001" or descriptor[6] != 1:
                raise DiscError(f"invalid volume descriptor at sector {lba}")
            if descriptor[0] == 1:
                primary = descriptor
            if descriptor[0] == 255:
                break
        if primary is None:
            raise DiscError("no ISO9660 primary volume descriptor found")
        self.root = parse_record(primary[156:])[:2]

    @staticmethod
    def _display_name(raw_name: bytes) -> str:
        name = raw_name.decode("ascii", errors="replace")
        if name.endswith("."):
            name = name[:-1]
        return re.sub(r";\d+$", "", name)

    def files(self) -> list[tuple[str, int, int]]:
        result: list[tuple[str, int, int]] = []
        visited: set[tuple[int, int]] = set()

        def walk(path: str, extent: int, size: int) -> None:
            key = (extent, size)
            if key in visited:
                raise DiscError(f"directory cycle at {path or '/'}")
            visited.add(key)
            directory = self.read_extent(extent, size)
            offset = 0
            while offset < len(directory):
                record_size = directory[offset]
                if record_size == 0:
                    offset = ((offset // LOGICAL_SECTOR_SIZE) + 1) * LOGICAL_SECTOR_SIZE
                    continue
                record = directory[offset : offset + record_size]
                child_extent, child_size, flags, raw_name = parse_record(record)
                offset += record_size
                if raw_name in (b"\x00", b"\x01"):
                    continue
                name = self._display_name(raw_name)
                child_path = f"{path}/{name}" if path else name
                if flags & 0x02:
                    walk(child_path, child_extent, child_size)
                else:
                    result.append((child_path, child_size, child_extent))

        root_extent, root_size = self.root
        walk("", root_extent, root_size)
        return sorted(result, key=lambda item: item[0].casefold())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cue", type=Path, help="cue sheet containing a MODE1/2352 track")
    args = parser.parse_args()

    track_path = cue_data_track(args.cue)
    iso = Iso9660(track_path)
    try:
        print(f"Cue: {args.cue}")
        print(f"Track: {track_path} ({iso.sector_count} raw sectors)")
        print("Size (bytes)\tLBA\tPath")
        files = iso.files()
        for path, size, lba in files:
            print(f"{size}\t{lba}\t{path}")
        total = sum(size for _, size, _ in files)
        print(f"Files: {len(files)}; payload total: {total} bytes")
    finally:
        iso.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DiscError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)''',
        'build_cart': r'''#!/usr/bin/env python3
"""Build a bootable Saturn cart image (.ss) and the file -> ROM offset table.

Layout (offsets from the start of CS0, 0x22000000 cache-through):
  0x000000  boot area: IP from the disc (header + security code + area code),
            then the payload program right after the IP
  0x200000  original cart ROM (mpr-18811), 2 MiB, unchanged
  0x400000  whole data track as a 2048-byte-sector image: ROM = 0x400000 + LBA * 2048
  --blob    extra data in the free parts: after the boot program (up to 0x200000)
            and after the data track (up to 32 MiB), e.g. tools/precalc_decors.py

The BIOS only boots a cart whose first 16 bytes are "SEGA SEGASATURN ", so the
original ROM ("SEGASATURN DATA ...", data from 0x100 onwards) cannot stay at 0.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

from inventory_disc import LOGICAL_SECTOR_SIZE, DiscError, Iso9660, cue_data_track

CS0_BASE = 0x22000000
BOOT_OFFSET = 0x000000
BOOT_AREA_SIZE = 0x200000
CART_ROM_OFFSET = 0x200000
CART_ROM_SIZE = 0x200000
ISO_OFFSET = 0x400000
CS0_SIZE = 0x2000000

IP_SIZE_FIELD = 0xE0
FIRST_READ_ADDR_FIELD = 0xF0
SECURITY_RANGE = (0x100, 0xE00)
# SHA-256 of the genuine security code, as checked by Mednafen (ss.cpp, IsSaturnDisc).
SECURITY_SHA256 = "96b8ea48819cfa589f24c40aa149c224c420dccf38b730f00156efe25c9bbc8f"
# Japanese area code block: "bra; nop; 'For JAPAN.'", then a jump to the first-read address.
AREA_JUMP_CODE = bytes.fromhex("d001402b00090000")
AREA_JUMP_OFFSET = 0xE20


def read_ip(iso: Iso9660) -> bytearray:
    head = iso.read_sector(0)
    if head[:16] != b"SEGA SEGASATURN ":
        raise DiscError("sector 0 is not a Saturn IP")
    ip_size = int.from_bytes(head[IP_SIZE_FIELD : IP_SIZE_FIELD + 4], "big")
    if not 0x1000 <= ip_size <= 0x8000:
        raise DiscError(f"IP size 0x{ip_size:X} outside the BIOS limits 0x1000-0x8000")
    ip = bytearray(iso.read_extent(0, ip_size))
    start, end = SECURITY_RANGE
    if hashlib.sha256(ip[start:end]).hexdigest() != SECURITY_SHA256:
        raise DiscError("IP security code does not match the genuine one")
    return ip


def retarget_area_jump(ip: bytearray, entry: int) -> int:
    """Point the area code's final jump at `entry`; return the previous target."""
    code = ip[AREA_JUMP_OFFSET : AREA_JUMP_OFFSET + len(AREA_JUMP_CODE)]
    if code != AREA_JUMP_CODE:
        raise DiscError("unexpected area code layout, cannot retarget its jump")
    literal = AREA_JUMP_OFFSET + len(AREA_JUMP_CODE)
    previous = int.from_bytes(ip[literal : literal + 4], "big")
    ip[literal : literal + 4] = entry.to_bytes(4, "big")
    return previous


def build_boot_area(ip: bytearray, payload: bytes, run_from_cart: bool) -> bytes:
    payload_offset = len(ip)
    if run_from_cart:
        retarget_area_jump(ip, CS0_BASE + BOOT_OFFSET + payload_offset)
    boot = bytes(ip) + payload
    if len(boot) > BOOT_AREA_SIZE:
        raise DiscError(f"boot area is 0x{len(boot):X} bytes, limit 0x{BOOT_AREA_SIZE:X}")
    return boot


def replace_files(image: bytearray, files: list[tuple[str, int, int]], replacements: list[str]) -> list[str]:
    """Overwrite disc files in the data-track part of the image (same size only)."""
    by_name = {name: (size, lba) for name, size, lba in files}
    log = []
    for spec in replacements:
        name, sep, source = spec.partition("=")
        if not sep or name not in by_name:
            raise DiscError(f"--replace {spec}: expected NAME=FILE with NAME a file of the disc")
        size, lba = by_name[name]
        data = Path(source).read_bytes()
        if len(data) != size:
            raise DiscError(f"--replace {name}: {len(data)} bytes, the disc file has {size}")
        offset = ISO_OFFSET + lba * LOGICAL_SECTOR_SIZE
        image[offset : offset + size] = data
        log.append(f"{name} replaced by {source} at cart 0x{CS0_BASE + offset:08X}")
    return log


def add_blobs(image: bytearray, boot_size: int, specs: list[str]) -> list[str]:
    """Place `OFFSET=FILE` blobs in the free parts of CS0 (no overlap allowed)."""
    iso_end = len(image)
    free = [(boot_size, BOOT_AREA_SIZE), (iso_end, CS0_SIZE)]
    used: list[tuple[int, int]] = []
    log = []
    for spec in specs:
        offset_text, sep, source = spec.partition("=")
        if not sep:
            raise DiscError(f"--blob {spec}: expected OFFSET=FILE")
        offset = int(offset_text, 0)
        data = Path(source).read_bytes()
        end = offset + len(data)
        if not any(lo <= offset and end <= hi for lo, hi in free):
            raise DiscError(f"--blob {spec}: 0x{offset:X}-0x{end:X} is outside the free parts of CS0")
        if any(offset < e and s < end for s, e in used):
            raise DiscError(f"--blob {spec}: overlaps another blob")
        used.append((offset, end))
        if end > len(image):
            image.extend(bytes(end - len(image)))
        image[offset:end] = data
        log.append(f"{source} at cart 0x{CS0_BASE + offset:08X} (0x{len(data):X} bytes)")
    return log


def write_table(path: Path, files: list[tuple[str, int, int]]) -> None:
    with path.open("w", newline="") as out:
        writer = csv.writer(out, delimiter="\t", lineterminator="\n")
        writer.writerow(["path", "lba", "size", "rom_offset", "cs0_address"])
        for name, size, lba in sorted(files, key=lambda item: item[2]):
            offset = ISO_OFFSET + lba * LOGICAL_SECTOR_SIZE
            writer.writerow([name, lba, size, f"0x{offset:07X}", f"0x{CS0_BASE + offset:08X}"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cue", type=Path, help="cue sheet of the KOF95 disc")
    parser.add_argument("cart_rom", type=Path, help="mpr-18811 dump (2 MiB)")
    parser.add_argument("payload", type=Path, help="program placed right after the IP")
    parser.add_argument("output", type=Path, help="output .ss image")
    parser.add_argument("--table", type=Path, help="write the file -> ROM offset table (TSV)")
    parser.add_argument("--minimal", action="store_true", help="boot area only (no cart ROM, no disc data)")
    parser.add_argument(
        "--run-from-cart",
        action="store_true",
        help="make the area code jump into the payload in the cart instead of the IP first-read address",
    )
    parser.add_argument(
        "--replace",
        action="append",
        default=[],
        metavar="NAME=FILE",
        help="replace a disc file in the data-track part of the image (same size), repeatable",
    )
    parser.add_argument(
        "--blob",
        action="append",
        default=[],
        metavar="OFFSET=FILE",
        help="place FILE at OFFSET of CS0, in the free parts only; repeatable",
    )
    parser.add_argument("--blobs", type=Path, help="file of OFFSET=FILE lines, as --blob")
    args = parser.parse_args()
    if args.blobs:
        args.blob += [line.strip() for line in args.blobs.read_text().splitlines() if line.strip()]
    if args.minimal and (args.replace or args.blob):
        parser.error("--replace and --blob need the data track, not --minimal")

    iso = Iso9660(cue_data_track(args.cue))
    try:
        ip = read_ip(iso)
        boot = build_boot_area(ip, args.payload.read_bytes(), args.run_from_cart)
        if args.minimal:
            image = bytearray(boot)
        else:
            cart_rom = args.cart_rom.read_bytes()
            if len(cart_rom) != CART_ROM_SIZE:
                raise DiscError(f"cart ROM is {len(cart_rom)} bytes, expected {CART_ROM_SIZE}")
            iso_size = iso.sector_count * LOGICAL_SECTOR_SIZE
            if ISO_OFFSET + iso_size > CS0_SIZE:
                raise DiscError("disc data does not fit in CS0")
            image = bytearray(ISO_OFFSET + iso_size)
            image[BOOT_OFFSET : BOOT_OFFSET + len(boot)] = boot
            image[CART_ROM_OFFSET : CART_ROM_OFFSET + CART_ROM_SIZE] = cart_rom
            image[ISO_OFFSET:] = iso.read_extent(0, iso_size)
        files = iso.files()
        replaced = replace_files(image, files, args.replace)
        if not args.minimal:
            replaced += add_blobs(image, len(boot), args.blob)
        if args.table:
            write_table(args.table, files)
    finally:
        iso.close()

    # 16-bit ROM: keep the image an even number of bytes.
    if len(image) % 2:
        image.append(0)
    args.output.write_bytes(image)
    for line in replaced:
        print(line)
    entry = int.from_bytes(ip[FIRST_READ_ADDR_FIELD : FIRST_READ_ADDR_FIELD + 4], "big")
    print(f"{args.output}: {len(image)} bytes (0x{len(image):X}), IP 0x{len(ip):X} bytes, "
          f"payload at cart 0x{CS0_BASE + len(ip):08X}, IP first-read address 0x{entry:08X}"
          + (" (bypassed)" if args.run_from_cart else ""))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DiscError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
''',
        'patch_kof95': r'''#!/usr/bin/env python3
"""Patch the two KOF95 programs for the all-cart image.

  `0`     : the CD data-read primitives are overwritten by the sections of
            build/cdrom.elf (src/cdrom), each one inside the window of the
            function it replaces.
  MM.BIN  : the accesses to the original cart ROM (mpr-18811) are moved by
            +0x200000, where build_cart.py places it: 28 literal-pool words,
            a pointer split in two 16-bit literals, the ENE_MV/ENE_DT
            pointer table, two PRS pointers and the ROM build list
            (docs/archive/phase1_step5_patch.md); the call pointers of MM_CALLS go
            to functions of build/cdrom.elf (docs/archive/iter3_decors.md); the
            instructions of MM_CODE_WORDS are replaced (docs/archive/iter4_attente.md);
            the .m_* sections of the ELF overwrite the MM_WINDOWS
            (docs/archive/iter8_a.md).
  cart    : the .c_* sections (code run from the cart) are written to
            <out_dir>/cart_*.bin, listed in <out_dir>/blobs.txt for
            build_cart.py --blobs.

Both files are read from the disc (cue sheet) and checked by SHA-256, every
patched word is checked against its expected original value.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

from inventory_disc import DiscError, Iso9660, cue_data_track

ZERO_BASE = 0x0607CD80
MM_BASE = 0x06002040
ZERO_SHA256 = "25cf3d668ca28b766ce984049225c2558bf697a64c93d3cf60d29866b51c007a"
MM_SHA256 = "ab938524fd6f3d2012db8e99096e3da66cd51a8dbb59a57c8859a48168d3076f"

ROM_SHIFT = 0x200000
CART_ROM_START, CART_ROM_END = 0x22000000, 0x22200000
ROM_BIAS_68K = 0x21F80100  # 68k address -> ROM, (A & 0xFFFFFF) + bias

# Functions of `0` that may be overwritten: (name, start, end).
ZERO_WINDOWS = [
    ("cache lookup", 0x0607D084, 0x0607D0DC),
    ("play (Set CD Device Connection + Play Disc)", 0x060833C0, 0x0608347C),
    ("read (Get Then Delete Sector Data loop)", 0x0608347C, 0x06083558),
    ("copy from cache partition", 0x06085AF4, 0x06085B34),
    ("LoadPac + streaming helpers (only caller: 0x0607D02A)", 0x0607F0A0, 0x0607F23C),
    ("list loader: trapa #48 0x13 before each file", 0x0607CF72, 0x0607CF76),
    ("dead helpers of the original read (only callers: 0x060834CA, 0x0608347C)", 0x06083558, 0x060836E4),
    ("trapa #48 0x17: stray push of r2 (never popped)", 0x060866A2, 0x060866A4),
    ("dead asynchronous file queue (docs/archive/iter6_ab.md)", 0x0607EE90, 0x0607EFDC),
    ("dead asynchronous file queue (0x0607F034: FsInit literal)", 0x0607F008, 0x0607F034),
    ("dead asynchronous file queue", 0x0607F038, 0x0607F0A0),
    ("dead asynchronous file queue", 0x0607F364, 0x0607F3BE),
    ("dead file queue: CD block function, unreferenced (docs/archive/iter7_preload.md)", 0x0607F6C8, 0x0607F73C),
    ("dead file queue: LZSS decompressor, only reached through 0x0607F65E", 0x0607F770, 0x0607F8EC),
    ("file reader: LZSS header test, never taken (no LZSSV001 file)", 0x0607F65E, 0x0607F660),
    ("trapa #48 table: service 0x11 (docs/archive/iter8_m.md)", 0x06085EAC, 0x06085EB0),
    ("trapa #48 table: service 0x15 (docs/archive/iter9_rounds.md)", 0x06085EBC, 0x06085EC0),
]

# MM.BIN code overwritten by the .m_* sections of the ELF: (name, start, end). The
# bytes of each window are checked against the original (MM_SHA256) by the hash.
MM_WINDOWS = [
    ("loader: NOW LOADING display call 0x06007934 r1 = 2 (docs/archive/iter8_a.md)", 0x06049718, 0x06049720),
    ("loader: literal 0x06007934, read by 0x06049718 and 0x0604972C only", 0x06049774, 0x06049778),
    ("name lookup: string compare 0x06004B12, only caller 0x06004AA0", 0x06004B10, 0x06004B3E),
    ("resets 0x06006B2E: slot table, map 0x00201100, VDP2 map 0x060CE000", 0x06006B54, 0x06006B80),
    ("name lookup 0x06004A78: first instructions (only entry; 0x06004AE6 is another function)", 0x06004A78, 0x06004A84),
    ("interrupt 0x06002880: literal of its 3rd call 0x0600672C", 0x060028F0, 0x060028F4),
    ("HU module linker 0x06004038 (bsr from 0x060040A8/0x060040DA, bsrf from 0x06004014)", 0x06004038, 0x0600408A),
    ("state 0x0602A308: braf to 0x0600D294 -> jmp (docs/archive/iter8_d.md)", 0x0602A320, 0x0602A324),
    ("state 0x0602A308: literal of that braf, read by 0x0602A31E only", 0x0602A32C, 0x0602A330),
    ("state 0x0602A38C: next-state write 0x0602A3C2-0x0602A3CD (dead after the jmp)", 0x0602A3C2, 0x0602A3CA),
    ("state 0x0602A38C: literal 0x0502, read by 0x0602A3C2 only", 0x0602A3D4, 0x0602A3D8),
    # 0x0600AE3A/0x0600AE3C (read by 0x0600AC3A-0x0600AC4E) and 0x0600AE50 (0x0600AC8E/0x0600ACB2) stay
    ("background columns 0x0600AD34: loop 1 (entries 0x0600AD04/AD1E/AD34 only)", 0x0600AD60, 0x0600AE3A),
    ("background columns 0x0600AD34: loop 2 and its literals, up to 0x0600AF10", 0x0600AE54, 0x0600AF10),
    ("interrupt 0x06002880: NBG1 map copy call (0x060069B4 rewritten unchanged)", 0x060069AA, 0x060069B6),
    ("interrupt 0x06002880: literal 0x060F8400 of that call, read by 0x060069AA only", 0x06006A44, 0x06006A48),
    ("loader 0x0604A128: DBRA loop 0x0604A174-0x0604A184 (no branch or literal into it)", 0x0604A174, 0x0604A186),
    ("frame loop: literal 0x06006BE0, read by 0x060266D4/0x06026742/0x0602679C only (docs/archive/iter8_m.md)", 0x06026A48, 0x06026A4C),
    ("cart check: sum routine 0x0600233C, only caller bsr 0x060022EC (docs/archive/iter10_demarrage.md)", 0x0600233C, 0x0600235E),
    ("init: count of the fixed wait 0x0600219C-0x060021AA (mov #8,r2)", 0x0600219C, 0x0600219E),
    ("sound init 0x06025D44: wait for the slave after command 6 (bt 0x06025D78)", 0x06025D7C, 0x06025D7E),
    ("sound init 0x06025D44: frame wait of the 8-call loop (subc r14,r14; bt 0x06025DE6)", 0x06025DEC, 0x06025DF0),
    ("boot list 0x0604AB3C: NOW LOADING call 0x06007934 r1 = 1 (jsr @r0; sts.l pr,@-r15)", 0x0604ABD2, 0x0604ABD6),
    ("shared wait 0x06049652: entry (count, next state), reached as a state only", 0x06049652, 0x0604965C),
    ("music dispatcher: literal 0x0602B634, read by the 8 jsr 0x0602B6DA-0x0602B8BE only (docs/archive/iter9_rounds.md)", 0x0602BA40, 0x0602BA44),
]

# Code run from the cart (.c_* sections, cached CS0 addresses), written as blobs for
# build_cart.py --blobs: (name, start, end). After the last background of the boot area.
CS0_CACHED = 0x02000000
CART_WINDOWS = [
    ("loader code (docs/archive/iter8_a.md), end of the boot area", 0x021FC000, 0x02200000),
]

# MM.BIN literal-pool words loaded by the code (docs/archive/phase1_step4_code.md, 2.3).
MM_POOL_WORDS = {
    0x06002280: 0x2216D080, 0x06002304: 0x22000000, 0x06002310: 0x220000E4,
    0x06002368: 0x22000100, 0x06007844: 0x220D1488, 0x0600B2FC: 0x2208E4D0,
    0x0600BD30: 0x2208E2D0, 0x0600CD34: 0x2208D2D0, 0x0600CD38: 0x2208C2D0,
    0x0600CF60: 0x22091D30, 0x0600D174: 0x220A14F0, 0x0600D290: 0x220A16F0,
    0x0600D68C: 0x22091CF0, 0x0600D884: 0x22091CF2, 0x0600DAC0: 0x22091CF0,
    0x0600DEA0: 0x22091CF0, 0x0600E688: 0x22091CF0, 0x0600E8CC: 0x22091CF0,
    0x0600EC2C: 0x22091CF0, 0x0600F894: 0x22000180, 0x0600F898: 0x22000100,
    0x0600FB04: 0x2208E5D0, 0x0600FB90: ROM_BIAS_68K, 0x06010104: ROM_BIAS_68K,
    0x0604977C: 0x2216D080, 0x0604A2F8: 0x2216D080, 0x0604A3BC: 0x2216D080,
    0x0604A584: 0x2216D080,
}
# Pointers stored in MM.BIN data.
MM_DATA_WORDS = {
    0x060071A0: 0x220D1488,  # 003F.PRS+8, PRS decompression structure
    0x06007210: 0x22153888,  # 2009.PRS+8, idem
}
# Pointers split by the 68k translator into two 16-bit literals, each loaded by
# mov.w @(disp,PC): address of the high half -> (high, low). Only the high half moves.
MM_SPLIT_POINTERS = {
    0x0600A194: (0x220A, 0x1CF0),  # BACK.BIN, loaded at 0x0600A178/0x0600A17A
}
# Table of 234 pointers to ENE_MV.DAT / ENE_DT.DAT records (code loads
# 0x0605CE6C and 0x0605CED4 as bases).
MM_ENE_TABLE = (0x0605CE6C, 234, 0x22080100, 0x2208C2D0)
# Literal-pool words holding a call target, redirected to a symbol of the ELF:
# address -> (original target, symbol).
MM_CALLS = {
    0x06049B2C: (0x06007868, "decor_preload"),  # background preload, jsr at 0x06049764 and 0x0604979E
    0x0602A2E0: (0x06049652, "fight_wait"),  # next state of 0x0602A274: shared 9-frame wait (docs/archive/iter5_attente.md)
    0x060028EC: (0x06002A2A, "snd_vbl"),  # VBlank-OUT interrupt, copy lists (docs/archive/iter6_ab.md)
    0x0602A3D8: (0x0602A3DC, "snd_state"),  # next state of 0x0602A38C, before the first fight image
    # Not a literal originally: the 2 instructions "mov.l 0x06007A58,r10; bsr 0x06007310" (VDP2 path of the
    # background tiles), now the literal of the jmp below (docs/archive/iter8_b.md).
    0x06007724: (0xDACCBDF3, "vdp2_group"),
}
# 16-bit instructions replaced in place: address -> (original, new) (docs/archive/iter4_attente.md).
MM_CODE_WORDS = {
    0x0602A316: (0xE107, 0xE100),  # mov #7,r1 -> mov #0,r1: post-load countdown, 8 frames -> 1
    0x0600771C: (0x4101, 0xD001),  # shlr r1 -> mov.l @(1,PC),r0 (= vdp2_group, 0x06007724)
    0x0600771E: (0x319C, 0x402B),  # add r9,r1 -> jmp @r0
    0x06007720: (0x6112, 0x0009),  # mov.l @r1,r1 -> nop (delay slot)
}
# Optional detours, applied only if the ELF defines the symbol (option off = image unchanged):
# symbol -> (literal address, original long, {address: (original, new) 16-bit words}).
MM_OPT_DETOURS = {
    # CHAR_RAW: group handler 0x060072D0 of the tile cache -> char_raw (docs/archive/motifs_bruts.md).
    # "mov #-4,r0; mov.l @(r0,r10),r0; cmp/ge r0,r1; bt 0x06007274; shlr r1; add r10,r1" becomes
    # "mov.l @(1,PC),r0; jmp @r0; nop; nop; .long char_raw"; char_raw returns to 0x060072DC.
    "char_raw": (0x060072D8, 0x410131AC, {
        0x060072D0: (0xE0FC, 0xD001), 0x060072D2: (0x00AE, 0x402B),
        0x060072D4: (0x3103, 0x0009), 0x060072D6: (0x89CD, 0x0009),
    }),
    # MENU_RAW: decompression of 8 groups of 003F.PRS in 0x060077A8 (menus) -> menu_raw (docs/archive/menage.md);
    # menu_raw returns to 0x060077E0.
    "menu_raw": (0x060077D8, 0x396CDA9F, {
        0x060077D0: (0xD91C, 0xD001), 0x060077D2: (0x4601, 0x402B),
        0x060077D4: (0x369C, 0x0009), 0x060077D6: (0x6662, 0x0009),
        0x060077DC: (0xBD98, 0x0009), 0x060077DE: (0x4F22, 0x0009),
    }),
}
# Optional 16-bit words, applied only if the ELF defines the symbol: symbol -> {address: (original, new)}, new =
# "hi"/"lo" for the halves of the symbol's value.
MM_OPT_WORDS = {
    # TAUNT (docs/archive/manques_mvs.md): wait of the order screen 20 -> 120 frames (mov #20,r1 -> mov #120,r1), and
    # the target of the trapa #62 at 0x06034E38 (inline long 0x0600F35E, two words) -> taunt_stub.
    "taunt_stub": {0x0603432A: (0xE114, 0xE178), 0x06034E3A: (0x0600, "hi"), 0x06034E3C: (0xF35E, "lo")},
}
# ROM build list ("ROMHEAD.BIN" -> 0x22000000, ...), destinations of LoadFile.
MM_BUILD_LIST = {
    0x0605E214: 0x22000000, 0x0605E222: 0x22000100, 0x0605E236: 0x220CB0F0,
    0x0605E248: 0x22080100, 0x0605E25A: 0x22086900, 0x0605E274: 0x2208C2D0,
    0x0605E284: 0x22091CF0, 0x0605E294: 0x220A1CF0, 0x0605E2A6: 0x2208E5D0,
    0x0605E2B6: 0x220D1480, 0x0605E2C6: 0x22153880, 0x0605E2D6: 0x2216D080,
}


def elf_sections(path: Path) -> list[tuple[str, int, bytes]]:
    """Allocated PROGBITS sections of a 32-bit big-endian ELF: (name, address, data)."""
    elf = path.read_bytes()
    if elf[:4] != b"\x7fELF" or elf[4] != 1 or elf[5] != 2:
        raise DiscError(f"{path}: not a 32-bit big-endian ELF")
    shoff, = struct.unpack_from(">I", elf, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from(">HHH", elf, 0x2E)
    headers = [struct.unpack_from(">IIIIIIIIII", elf, shoff + i * shentsize) for i in range(shnum)]
    strtab = headers[shstrndx]
    result = []
    for name, kind, flags, addr, offset, size, *_ in headers:
        if kind == 1 and flags & 2 and size:  # SHT_PROGBITS, SHF_ALLOC
            label = elf[strtab[4] + name : elf.index(b"\0", strtab[4] + name)].decode()
            result.append((label, addr, elf[offset : offset + size]))
    return result


def elf_symbols(path: Path) -> dict[str, int]:
    """Values of the symbols of a 32-bit big-endian ELF."""
    elf = path.read_bytes()
    shoff, = struct.unpack_from(">I", elf, 0x20)
    shentsize, shnum = struct.unpack_from(">HH", elf, 0x2E)
    headers = [struct.unpack_from(">IIIIIIIIII", elf, shoff + i * shentsize) for i in range(shnum)]
    result = {}
    for _, kind, _, _, offset, size, link, _, _, entsize in headers:
        if kind != 2:  # SHT_SYMTAB
            continue
        strings = headers[link][4]
        for pos in range(offset, offset + size, entsize):
            name, value = struct.unpack_from(">II", elf, pos)
            if name:
                result[elf[strings + name : elf.index(b"\0", strings + name)].decode()] = value
    return result


def patch_sections(image: bytearray, base: int, label: str, windows: list[tuple[str, int, int]],
                   sections: list[tuple[str, int, bytes]]) -> list[str]:
    log = []
    for name, addr, data in sections:
        window = next((w for w in windows if w[1] <= addr and addr + len(data) <= w[2]), None)
        if window is None:
            raise DiscError(f"section {name} at 0x{addr:08X} (+0x{len(data):X}) is outside the allowed windows")
        offset = addr - base
        image[offset : offset + len(data)] = data
        log.append(f"{label} 0x{addr:08X} {name:9} 0x{len(data):03X}/0x{window[2] - window[1]:03X} bytes  {window[0]}")
    return log


def shift_word(mm: bytearray, addr: int, expected: int | None = None, bounds: tuple[int, int] | None = None) -> int:
    offset = addr - MM_BASE
    value, = struct.unpack_from(">I", mm, offset)
    if expected is not None and value != expected:
        raise DiscError(f"MM.BIN 0x{addr:08X}: 0x{value:08X}, expected 0x{expected:08X}")
    if bounds is not None and not bounds[0] <= value < bounds[1]:
        raise DiscError(f"MM.BIN 0x{addr:08X}: 0x{value:08X} outside 0x{bounds[0]:08X}-0x{bounds[1]:08X}")
    struct.pack_into(">I", mm, offset, value + ROM_SHIFT)
    return value


def patch_mm(mm: bytearray, symbols: dict[str, int]) -> list[str]:
    for addr, value in MM_POOL_WORDS.items():
        shift_word(mm, addr, value)
    for addr, (high, low) in MM_SPLIT_POINTERS.items():
        shift_word(mm, addr, high << 16 | low)
    for addr, value in MM_DATA_WORDS.items():
        shift_word(mm, addr, value)
    start, count, low, high = MM_ENE_TABLE
    for index in range(count):
        shift_word(mm, start + 4 * index, bounds=(low, high))
    for addr, value in MM_BUILD_LIST.items():
        shift_word(mm, addr, value)
    calls = []
    for addr, (target, symbol) in MM_CALLS.items():
        value, = struct.unpack_from(">I", mm, addr - MM_BASE)
        if value != target:
            raise DiscError(f"MM.BIN 0x{addr:08X}: 0x{value:08X}, expected 0x{target:08X}")
        if symbol not in symbols:
            raise DiscError(f"symbol {symbol} missing from the ELF")
        struct.pack_into(">I", mm, addr - MM_BASE, symbols[symbol])
        calls.append(f"MM.BIN 0x{addr:08X} call 0x{target:08X} -> {symbol} 0x{symbols[symbol]:08X}")
    for addr, (original, new) in MM_CODE_WORDS.items():
        value, = struct.unpack_from(">H", mm, addr - MM_BASE)
        if value != original:
            raise DiscError(f"MM.BIN 0x{addr:08X}: 0x{value:04X}, expected 0x{original:04X}")
        struct.pack_into(">H", mm, addr - MM_BASE, new)
        calls.append(f"MM.BIN 0x{addr:08X} code 0x{original:04X} -> 0x{new:04X}")
    for symbol, (literal, original, words) in MM_OPT_DETOURS.items():
        if symbol not in symbols:
            continue
        for addr, (old, new) in words.items():
            value, = struct.unpack_from(">H", mm, addr - MM_BASE)
            if value != old:
                raise DiscError(f"MM.BIN 0x{addr:08X}: 0x{value:04X}, expected 0x{old:04X}")
            struct.pack_into(">H", mm, addr - MM_BASE, new)
        value, = struct.unpack_from(">I", mm, literal - MM_BASE)
        if value != original:
            raise DiscError(f"MM.BIN 0x{literal:08X}: 0x{value:08X}, expected 0x{original:08X}")
        struct.pack_into(">I", mm, literal - MM_BASE, symbols[symbol])
        calls.append(f"MM.BIN 0x{min(words):08X} detour -> {symbol} 0x{symbols[symbol]:08X} (literal 0x{literal:08X})")
    for symbol, words in MM_OPT_WORDS.items():
        if symbol not in symbols:
            continue
        for addr, (old, new) in words.items():
            value, = struct.unpack_from(">H", mm, addr - MM_BASE)
            if value != old:
                raise DiscError(f"MM.BIN 0x{addr:08X}: 0x{value:04X}, expected 0x{old:04X}")
            if new == "hi":
                new = symbols[symbol] >> 16
            elif new == "lo":
                new = symbols[symbol] & 0xFFFF
            struct.pack_into(">H", mm, addr - MM_BASE, new)
            calls.append(f"MM.BIN 0x{addr:08X} code 0x{old:04X} -> 0x{new:04X} ({symbol})")
    return calls + [
        f"MM.BIN {len(MM_POOL_WORDS)} literal-pool words, {len(MM_SPLIT_POINTERS)} split pointer, "
        f"{len(MM_DATA_WORDS)} PRS pointers, "
        f"{count} table entries at 0x{start:08X}, {len(MM_BUILD_LIST)} build-list entries: +0x{ROM_SHIFT:X}"
    ]


NAMES_REGISTRY = 0x06004B88   # 0x06004A78: {slots, names, -} entries up to slots = 0
NAMES_BUCKETS = 64


def names_hash(name: bytes) -> int:
    """Bucket of a name, as names_fast computes it (signed bytes, h = h * 2 + c)."""
    h = 0
    for c in name:
        h = (h * 2 + (c - 256 if c > 127 else c)) & 0xFFFFFFFF
    return ((h >> 5) + h) & (NAMES_BUCKETS - 1)


def names_index(mm: bytes, addr: int, size: int) -> tuple[bytes, int]:
    """Hash index of the name registry of MM.BIN for names_fast (docs/archive/iter8_a.md), at
    addr: NAMES_BUCKETS chain pointers, then chains of {name, slot} ended by 0. A name
    keeps its first entry, as the walk of 0x06004A78 does."""
    word = lambda a: struct.unpack_from(">I", mm, a - MM_BASE)[0]
    chains: list[list[tuple[int, int]]] = [[] for _ in range(NAMES_BUCKETS)]
    seen = set()
    entry = NAMES_REGISTRY
    while word(entry):
        slots, names = word(entry), word(entry + 4)
        k = 0
        while word(names + 4 * k):
            ptr = word(names + 4 * k)
            text = bytes(mm[ptr - MM_BASE : mm.index(b"\0", ptr - MM_BASE)])
            if text not in seen:
                seen.add(text)
                chains[names_hash(text)].append((ptr, slots + 4 * k))
            k += 1
        entry += 12
    out = bytearray(4 * NAMES_BUCKETS)
    for b, chain in enumerate(chains):
        struct.pack_into(">I", out, 4 * b, addr + len(out))
        for ptr, slot in chain:
            out += struct.pack(">II", ptr, slot)
        out += bytes(4)
    if len(out) > size:
        raise DiscError(f"names index: 0x{len(out):X} bytes, 0x{size:X} reserved")
    return bytes(out), len(seen)


def read_file(iso: Iso9660, name: str, sha256: str) -> bytearray:
    entry = next(((size, lba) for path, size, lba in iso.files() if path == name), None)
    if entry is None:
        raise DiscError(f"{name} not found on the disc")
    data = bytearray(iso.read_extent(entry[1], entry[0]))
    if hashlib.sha256(data).hexdigest() != sha256:
        raise DiscError(f"{name}: SHA-256 differs from the analysed version")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cue", type=Path, help="cue sheet of the KOF95 disc")
    parser.add_argument("elf", type=Path, help="replacement code (build/cdrom.elf)")
    parser.add_argument("out_dir", type=Path, help="directory for the patched `0` and MM.BIN")
    args = parser.parse_args()

    iso = Iso9660(cue_data_track(args.cue))
    try:
        zero = read_file(iso, "0", ZERO_SHA256)
        mm = read_file(iso, "MM.BIN", MM_SHA256)
    finally:
        iso.close()

    sections = elf_sections(args.elf)
    log = patch_sections(zero, ZERO_BASE, "0", ZERO_WINDOWS, [s for s in sections if not s[0].startswith((".m_", ".c_"))])
    log += patch_mm(mm, elf_symbols(args.elf))
    log += patch_sections(mm, MM_BASE, "MM.BIN", MM_WINDOWS, [s for s in sections if s[0].startswith(".m_")])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    blobs = []
    symbols = elf_symbols(args.elf)
    for name, addr, data in sections:
        if not name.startswith(".c_"):
            continue
        idx = symbols.get("names_idx")
        if idx is not None and addr <= idx < addr + len(data):
            size = symbols["names_idx_end"] - idx
            table, count = names_index(mm, idx, size)
            data = data[: idx - addr] + table + data[idx - addr + len(table) :]
            log.append(f"cart 0x{idx:08X} names_idx 0x{len(table):03X}/0x{size:03X} bytes  {count} names, {NAMES_BUCKETS} buckets")
        window = next((w for w in CART_WINDOWS if w[1] <= addr and addr + len(data) <= w[2]), None)
        if window is None:
            raise DiscError(f"section {name} at 0x{addr:08X} (+0x{len(data):X}) is outside the cart windows")
        path = args.out_dir / f"cart_{addr:08X}.bin"
        path.write_bytes(data)
        blobs.append(f"0x{addr - CS0_CACHED:07X}={path}")
        log.append(f"cart 0x{addr:08X} {name:9} 0x{len(data):03X}/0x{window[2] - window[1]:03X} bytes  {window[0]}")
    (args.out_dir / "blobs.txt").write_text("".join(line + "\n" for line in blobs))
    (args.out_dir / "0").write_bytes(zero)
    (args.out_dir / "MM.BIN").write_bytes(mm)
    print("\n".join(log))
    print(f"-> {args.out_dir / '0'}, {args.out_dir / 'MM.BIN'}, {args.out_dir / 'blobs.txt'} ({len(blobs)} cart blobs)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DiscError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
''',
        'sh2_interp': r'''"""Minimal SH-2 interpreter (integer subset, no interrupts).

Enough to run small self-contained routines found in the game files, such as
the yzb2 decompressor of the YZB hack (tools/yzb_compare.py), and the translated
68k code of MM.BIN (GBR forms, trapa/rte through self.vbr, tools/decor_native_check.py).
Unknown opcodes raise RuntimeError, so a routine either runs exactly or stops loudly.
SR is kept as self.sr_rest (all bits but T) and self.t; rte restores SR before its
delay slot runs.
"""

from __future__ import annotations

import struct

M32 = 0xFFFFFFFF


def s8(v): return v - 0x100 if v & 0x80 else v
def s12(v): return v - 0x1000 if v & 0x800 else v
def s16(v): return v - 0x10000 if v & 0x8000 else v
def s32(v): return v - (1 << 32) if v & 0x80000000 else v


class Mem:
    def __init__(self):
        self.regions: list[tuple[int, bytearray]] = []

    def map(self, base, size, data=b""):
        buf = bytearray(size)
        buf[:len(data)] = data
        self.regions.append((base, buf))
        return buf

    def _loc(self, a, n):
        a &= 0x1FFFFFFF  # cache-through alias
        for base, buf in self.regions:
            if base & 0x1FFFFFFF <= a and a + n <= (base & 0x1FFFFFFF) + len(buf):
                return buf, a - (base & 0x1FFFFFFF)
        raise RuntimeError(f"unmapped access at 0x{a:08X}")

    def r8(self, a): b, o = self._loc(a, 1); return b[o]
    def r16(self, a): b, o = self._loc(a, 2); return struct.unpack_from(">H", b, o)[0]
    def r32(self, a): b, o = self._loc(a, 4); return struct.unpack_from(">I", b, o)[0]
    def w8(self, a, v): b, o = self._loc(a, 1); b[o] = v & 0xFF
    def w16(self, a, v): b, o = self._loc(a, 2); struct.pack_into(">H", b, o, v & 0xFFFF)
    def w32(self, a, v): b, o = self._loc(a, 4); struct.pack_into(">I", b, o, v & M32)


class SH2:
    def __init__(self, mem):
        self.m, self.r, self.t, self.pr, self.gbr = mem, [0] * 16, 0, 0, 0
        self.vbr, self.sr_rest, self.mach, self.macl = 0, 0xF0, 0, 0
        self.steps = 0

    def call(self, pc, ret=0xDEAD0000, limit=500_000_000):
        self.pr, self.pc = ret, pc
        while self.pc != ret:
            self.step()
            if self.steps > limit:
                raise RuntimeError("instruction limit reached")

    def step(self, delay=False):
        m, r = self.m, self.r
        pc = self.pc
        op = m.r16(pc)
        self.steps += 1
        n, mm_, d8 = (op >> 8) & 15, (op >> 4) & 15, op & 0xFF
        nxt = pc + 2
        jump = None
        top, low4 = op >> 12, op & 15
        if op == 0x0009: pass                                              # nop
        elif op == 0x000B: jump = self.pr                                  # rts
        elif op == 0x0008: self.t = 0                                      # clrt
        elif op == 0x0018: self.t = 1                                      # sett
        elif op == 0x002B:                                                 # rte
            jump = m.r32(r[15]); sr = m.r32(r[15] + 4); r[15] = (r[15] + 8) & M32
            self.sr_rest, self.t = sr & 0x3F2, sr & 1
        elif op & 0xFF00 == 0xC300:                                        # trapa
            if delay: raise RuntimeError("trapa in a delay slot")
            r[15] = (r[15] - 4) & M32; m.w32(r[15], self.sr_rest | self.t)
            r[15] = (r[15] - 4) & M32; m.w32(r[15], pc + 2)
            self.pc = m.r32(self.vbr + d8 * 4); return
        elif top == 0xC and (op >> 8) & 15 in (0, 1, 2, 4, 5, 6, 0xC, 0xD, 0xE, 0xF):  # GBR forms
            k = (op >> 8) & 15
            if k == 0: m.w8(self.gbr + d8, r[0])
            elif k == 1: m.w16(self.gbr + d8 * 2, r[0])
            elif k == 2: m.w32(self.gbr + d8 * 4, r[0])
            elif k == 4: r[0] = s8(m.r8(self.gbr + d8)) & M32
            elif k == 5: r[0] = s16(m.r16(self.gbr + d8 * 2)) & M32
            elif k == 6: r[0] = m.r32(self.gbr + d8 * 4)
            else:
                a = (self.gbr + r[0]) & M32; v = m.r8(a)
                if k == 0xC: self.t = int(v & d8 == 0)
                elif k == 0xD: m.w8(a, v & d8)
                elif k == 0xE: m.w8(a, v ^ d8)
                else: m.w8(a, v | d8)
        elif op & 0xFF00 == 0xCA00: r[0] ^= d8                             # xor #imm
        elif op & 0xF0FF == 0x001A: r[n] = self.macl                       # sts macl
        elif op & 0xF0FF == 0x000A: r[n] = self.mach                       # sts mach
        elif op & 0xF00F == 0x0007: self.macl = (r[n] * r[mm_]) & M32      # mul.l
        elif top == 0xE: r[n] = s8(d8) & M32                               # mov #imm
        elif top == 0x9: r[n] = s16(m.r16(pc + 4 + d8 * 2)) & M32          # mov.w @(disp,pc)
        elif top == 0xD: r[n] = m.r32(((pc + 4) & ~3) + d8 * 4)            # mov.l @(disp,pc)
        elif op & 0xFF00 == 0xC700: r[0] = ((pc + 4) & ~3) + d8 * 4        # mova
        elif top == 0x7: r[n] = (r[n] + s8(d8)) & M32                      # add #imm
        elif top == 0xA: jump = (pc + 4 + s12(op & 0xFFF) * 2) & M32       # bra
        elif top == 0xB: self.pr = pc + 4; jump = (pc + 4 + s12(op & 0xFFF) * 2) & M32  # bsr
        elif op & 0xFF00 == 0x8900:                                        # bt
            if self.t: self.pc = pc + 4 + s8(d8) * 2; return
        elif op & 0xFF00 == 0x8B00:                                        # bf
            if not self.t: self.pc = pc + 4 + s8(d8) * 2; return
        elif op & 0xFF00 == 0x8D00:                                        # bt/s
            if self.t: jump = pc + 4 + s8(d8) * 2
        elif op & 0xFF00 == 0x8F00:                                        # bf/s
            if not self.t: jump = pc + 4 + s8(d8) * 2
        elif op & 0xFF00 == 0x8800: self.t = int(r[0] == s8(d8) & M32)     # cmp/eq #imm
        elif op & 0xFF00 == 0xC800: self.t = int((r[0] & d8) == 0)         # tst #imm
        elif op & 0xFF00 == 0xC900: r[0] &= d8                             # and #imm
        elif op & 0xFF00 == 0xCB00: r[0] |= d8                             # or #imm
        elif op & 0xFF00 == 0x8500: r[0] = s16(m.r16(r[mm_] + low4 * 2)) & M32  # mov.w @(d,Rm),r0
        elif op & 0xFF00 == 0x8400: r[0] = s8(m.r8(r[mm_] + low4)) & M32   # mov.b @(d,Rm),r0
        elif op & 0xFF00 == 0x8100: m.w16(r[mm_] + low4 * 2, r[0])         # mov.w r0,@(d,Rn)
        elif op & 0xFF00 == 0x8000: m.w8(r[mm_] + low4, r[0])              # mov.b r0,@(d,Rn)
        elif top == 0x0 and low4 in (4, 5, 6, 0xC, 0xD, 0xE):             # @(r0,Rx) forms
            if low4 == 4: m.w8(r[0] + r[n], r[mm_])
            elif low4 == 5: m.w16(r[0] + r[n], r[mm_])
            elif low4 == 6: m.w32(r[0] + r[n], r[mm_])
            elif low4 == 0xC: r[n] = s8(m.r8(r[0] + r[mm_])) & M32
            elif low4 == 0xD: r[n] = s16(m.r16(r[0] + r[mm_])) & M32
            else: r[n] = m.r32(r[0] + r[mm_])
        elif top == 0x5: r[n] = m.r32(r[mm_] + low4 * 4)                   # mov.l @(d,Rm)
        elif top == 0x1: m.w32(r[n] + low4 * 4, r[mm_])                    # mov.l Rm,@(d,Rn)
        elif top == 0x6:
            a = r[mm_]
            if low4 == 0: r[n] = s8(m.r8(a)) & M32
            elif low4 == 1: r[n] = s16(m.r16(a)) & M32
            elif low4 == 2: r[n] = m.r32(a)
            elif low4 == 3: r[n] = a
            elif low4 == 4: r[n] = s8(m.r8(a)) & M32; r[mm_] = (a + 1) & M32 if n != mm_ else r[n]
            elif low4 == 5: r[n] = s16(m.r16(a)) & M32; r[mm_] = (a + 2) & M32 if n != mm_ else r[n]
            elif low4 == 6: v = m.r32(a); r[mm_] = (a + 4) & M32; r[n] = v
            elif low4 == 7: r[n] = ~a & M32
            elif low4 == 8: r[n] = ((a >> 8) & 0xFF) | ((a & 0xFF) << 8) | (a & 0xFFFF0000)
            elif low4 == 9: r[n] = ((a >> 16) | (a << 16)) & M32
            elif low4 == 0xB: r[n] = (-a) & M32
            elif low4 == 0xC: r[n] = a & 0xFF
            elif low4 == 0xD: r[n] = a & 0xFFFF
            elif low4 == 0xE: r[n] = s8(a & 0xFF) & M32
            elif low4 == 0xF: r[n] = s16(a & 0xFFFF) & M32
            else: raise RuntimeError(f"op {op:04X} @ {pc:08X}")
        elif top == 0x2:
            a, b = r[n], r[mm_]
            if low4 == 0: m.w8(a, b)
            elif low4 == 1: m.w16(a, b)
            elif low4 == 2: m.w32(a, b)
            elif low4 == 4: r[n] = (a - 1) & M32; m.w8(r[n], b)
            elif low4 == 5: r[n] = (a - 2) & M32; m.w16(r[n], b)
            elif low4 == 6: r[n] = (a - 4) & M32; m.w32(r[n], b)
            elif low4 == 8: self.t = int(a & b == 0)
            elif low4 == 9: r[n] = a & b
            elif low4 == 0xA: r[n] = a ^ b
            elif low4 == 0xB: r[n] = a | b
            elif low4 == 0xD: r[n] = ((a >> 16) | (b << 16)) & M32
            elif low4 == 0xE: self.macl = (a & 0xFFFF) * (b & 0xFFFF)              # mulu.w
            elif low4 == 0xF: self.macl = (s16(a & 0xFFFF) * s16(b & 0xFFFF)) & M32  # muls.w
            else: raise RuntimeError(f"op {op:04X} @ {pc:08X}")
        elif top == 0x3:
            a, b = r[n], r[mm_]
            if low4 == 0: self.t = int(a == b)
            elif low4 == 2: self.t = int(a >= b)
            elif low4 == 3: self.t = int(s32(a) >= s32(b))
            elif low4 == 6: self.t = int(a > b)
            elif low4 == 7: self.t = int(s32(a) > s32(b))
            elif low4 == 8: r[n] = (a - b) & M32
            elif low4 == 0xC: r[n] = (a + b) & M32
            elif low4 == 0xA: v = a - b - self.t; r[n] = v & M32; self.t = int(v < 0)       # subc
            elif low4 == 0xE: v = a + b + self.t; r[n] = v & M32; self.t = v >> 32          # addc
            elif low4 == 0xB: v = s32(a) - s32(b); r[n] = v & M32; self.t = int(not -2**31 <= v < 2**31)  # subv
            elif low4 == 0xF: v = s32(a) + s32(b); r[n] = v & M32; self.t = int(not -2**31 <= v < 2**31)  # addv
            else: raise RuntimeError(f"op {op:04X} @ {pc:08X}")
        elif top == 0x4:
            a, lo = r[n], op & 0xFF
            if lo == 0x00: self.t = a >> 31; r[n] = (a << 1) & M32
            elif lo == 0x01: self.t = a & 1; r[n] = a >> 1
            elif lo == 0x08: r[n] = (a << 2) & M32
            elif lo == 0x09: r[n] = a >> 2
            elif lo == 0x18: r[n] = (a << 8) & M32
            elif lo == 0x19: r[n] = a >> 8
            elif lo == 0x28: r[n] = (a << 16) & M32
            elif lo == 0x29: r[n] = a >> 16
            elif lo == 0x10: r[n] = (a - 1) & M32; self.t = int(r[n] == 0)
            elif lo == 0x11: self.t = int(s32(a) >= 0)
            elif lo == 0x15: self.t = int(s32(a) > 0)
            elif lo == 0x20: self.t = a >> 31; r[n] = (a << 1) & M32
            elif lo == 0x21: self.t = a & 1; r[n] = (s32(a) >> 1) & M32
            elif lo == 0x04: self.t = a >> 31; r[n] = ((a << 1) | self.t) & M32       # rotl
            elif lo == 0x05: self.t = a & 1; r[n] = (a >> 1) | (self.t << 31)         # rotr
            elif lo == 0x24: t = a >> 31; r[n] = ((a << 1) | self.t) & M32; self.t = t  # rotcl
            elif lo == 0x25: t = a & 1; r[n] = (a >> 1) | (self.t << 31); self.t = t    # rotcr
            elif lo == 0x22: r[15] = (r[15] - 4) & M32; m.w32(r[15], self.pr)
            elif lo == 0x26: self.pr = m.r32(a); r[n] = (a + 4) & M32
            elif lo == 0x0B: self.pr = pc + 4; jump = a                    # jsr
            elif lo == 0x0E: self.sr_rest, self.t = a & 0x3F2, a & 1       # ldc Rm,sr
            elif lo == 0x1E: self.gbr = a                                  # ldc Rm,gbr
            elif lo == 0x2B: jump = a                                      # jmp
            else: raise RuntimeError(f"op {op:04X} @ {pc:08X}")
        else:
            raise RuntimeError(f"op {op:04X} @ {pc:08X}")
        if jump is not None:
            if delay: raise RuntimeError("branch in a delay slot")
            self.pc = nxt
            self.step(delay=True)
            self.pc = jump
        else:
            self.pc = nxt

''',
        'precalc_decors': r'''#!/usr/bin/env python3
"""Precompute the stage backgrounds (decors) for the all-cart image.

The game loads the background of a stage (00xx.PRS) at 0x06086D80, then
0x06007868 decompresses its first min(count, 0xDC0) tiles, 8 tiles (1 KiB) per
group, with the decompressor 0x06007310 and copies them to VDP1 VRAM
0x25C10000 (docs/archive/iter1_chargements.md, 3.3). This tool runs the original
decompressor of MM.BIN in tools/sh2_interp.py, exactly as 0x06007868 calls it,
and lays the results out in the free parts of CS0:

  0x002000             table read by src/cdrom (DECOR_TABLE), 12-byte entries
                       {ROM address of the .PRS, ROM address of the tiles,
                       tile count}, ended by a zero long
  0x002100-0x1FFFFF    tiles (boot area, after the IP and the boot program)
  end of image-0x1FFFFFF  tiles (after the data track)

The decompressed groups are cached in <out_dir>/<name>.bin (checked against
the SHA-256 of their source file). Output: <out_dir>/blobs.txt, one
"offset=file" per line, for build_cart.py --blob.

--sat (docs/archive/compression_decors.md): the tiles are not placed. Each 00xx.SAT of
the data track is exactly the first `count` tiles of this output (Sega's own
decompressed background, never loaded by the game), and the rounding tail of
the last group (zero) falls in the zero padding of its last sector. The table
points to the .SAT, so every read of the tiles returns the same bytes; this
tool only checks both facts.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

from build_cart import CS0_BASE, CS0_SIZE, ISO_OFFSET
from inventory_disc import LOGICAL_SECTOR_SIZE, DiscError, Iso9660, cue_data_track
from sh2_interp import SH2, Mem

MM_BASE = 0x06002040
MM_SHA256 = "ab938524fd6f3d2012db8e99096e3da66cd51a8dbb59a57c8859a48168d3076f"
DECOMPRESS = 0x06007310
GROUP_BUF = 0x060CDB10  # 0x06007868 decompresses every group there
FILE_ADDR = 0x06086D88  # file + 8, as in RAM
MAX_TILES = 0xDC0       # 0x06007868 preloads at most this many tiles
GROUP_SIZE = 1024

# The files loaded at 0x06086D80: load-list entries MM.BIN 0x0605DA64-0x0605DAF4
# (name, then destination 0x06086D80 in the next long), seen in LoadFile (r9).
# 003D/003E go to 0x0021D000 (title screen) and are not preloaded.
DECORS = ["0034", "0035", "0036", "0037", "0038", "0039", "003A", "003B", "003C"]

TABLE_OFFSET = 0x002000
ZONE_A = (0x002100, 0x200000)


def preload_tiles(mm: bytes, prs: bytes) -> bytes:
    """What 0x06007868 writes to VRAM 0x25C10000 for this file."""
    count = min(struct.unpack_from(">I", prs, 4)[0], MAX_TILES)
    mem = Mem()
    high = mem.map(0x06000000, 0x100000)
    high[MM_BASE - 0x06000000 : MM_BASE - 0x06000000 + len(mm)] = mm
    high[FILE_ADDR - 8 - 0x06000000 : FILE_ADDR - 8 - 0x06000000 + len(prs)] = prs
    stack, ret = 0x060FF000, 0xDEAD0000
    cpu = SH2(mem)
    out = bytearray()
    for tile in range(0, count, 8):
        offset = struct.unpack_from(">I", prs, 8 + tile // 2)[0]
        # bsr 0x06007310 / sts.l pr,@-r15 (delay slot): the routine pops pr itself.
        mem.w32(stack - 4, ret)
        cpu.r[9], cpu.r[10], cpu.r[15] = FILE_ADDR + offset, GROUP_BUF, stack - 4
        cpu.call(DECOMPRESS, ret)
        if cpu.r[15] != stack:
            raise RuntimeError(f"tile {tile}: stack not balanced after 0x{DECOMPRESS:08X}")
        start = GROUP_BUF - 0x06000000
        out += high[start : start + GROUP_SIZE]
    return bytes(out)


def place(blocks: list[tuple[str, int]], zones: list[list[int]]) -> dict[str, int]:
    """First fit, largest first; offsets 0x100-aligned."""
    where = {}
    for name, size in sorted(blocks, key=lambda b: -b[1]):
        for zone in zones:
            if zone[0] + size <= zone[1]:
                where[name] = zone[0]
                zone[0] = (zone[0] + size + 0xFF) & ~0xFF
                break
        else:
            raise DiscError(f"{name}: {size} bytes do not fit in the free parts of CS0")
    return where


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cue", type=Path, help="cue sheet of the KOF95 disc")
    parser.add_argument("out_dir", type=Path, help="directory for the tiles, the table and blobs.txt")
    parser.add_argument("--sat", action="store_true", help="point the table to the .SAT files (no tile blob)")
    parser.add_argument("--source", type=Path, help="disc cue to read the compressed .PRS from (compact track "
                        "with --strip: tools/compact_track.py); the table still uses the positions of <cue>")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    iso = Iso9660(cue_data_track(args.cue))
    try:
        files = {name: (size, lba) for name, size, lba in iso.files()}
        image_end = ISO_OFFSET + iso.sector_count * LOGICAL_SECTOR_SIZE
        size, lba = files["MM.BIN"]
        mm = iso.read_extent(lba, size)
        if hashlib.sha256(mm).hexdigest() != MM_SHA256:
            raise DiscError("MM.BIN: SHA-256 differs from the analysed version")
        tiles = {}
        where_sat = {}
        source = Iso9660(cue_data_track(args.source)) if args.source else iso
        src_files = {name: (size, lba) for name, size, lba in source.files()}
        for name in DECORS:
            size, lba = src_files[name + ".PRS"]
            prs = source.read_extent(lba, size)
            size, lba = files[name + ".PRS"]
            if iso.read_extent(lba, min(size, 16)) != prs[:min(size, 16)]:
                raise DiscError(f"{name}.PRS: header differs from the source disc")
            cache = args.out_dir / f"{name}.bin"
            stamp = args.out_dir / f"{name}.sha256"
            digest = hashlib.sha256(prs).hexdigest()
            if not (cache.exists() and stamp.exists() and stamp.read_text().strip() == digest):
                cache.write_bytes(preload_tiles(mm, prs))
                stamp.write_text(digest + "\n")
            tiles[name] = (lba, min(struct.unpack_from(">I", prs, 4)[0], MAX_TILES), cache)
            if args.sat:
                size, lba = files[name + ".SAT"]
                pre = cache.read_bytes()
                end = ((size + LOGICAL_SECTOR_SIZE - 1) // LOGICAL_SECTOR_SIZE) * LOGICAL_SECTOR_SIZE
                sat = iso.read_extent(lba, end)
                if sat[:size] != pre[:size] or size != tiles[name][1] * 128:
                    raise DiscError(f"{name}.SAT differs from the decompressed tiles")
                if len(pre) > end or any(sat[size:len(pre)]) or any(pre[size:]):
                    raise DiscError(f"{name}.SAT: rounding tail not covered by zero sector padding")
                where_sat[name] = ISO_OFFSET + lba * LOGICAL_SECTOR_SIZE
        if source is not iso:
            source.close()
    finally:
        iso.close()

    zone_b = [(image_end + 0xFF) & ~0xFF, CS0_SIZE]
    if args.sat:
        where = where_sat
    else:
        where = place([(n, t[2].stat().st_size) for n, t in tiles.items()], [list(ZONE_A), zone_b])
    table = bytearray()
    lines = []
    for name in DECORS:
        lba, count, cache = tiles[name]
        table += struct.pack(">III", CS0_BASE + ISO_OFFSET + lba * LOGICAL_SECTOR_SIZE, CS0_BASE + where[name], count)
        if not args.sat:
            lines.append(f"0x{where[name]:07X}={cache}")
        print(f"{name}.PRS  {count:4d} tiles  0x{cache.stat().st_size:06X} bytes  -> cart 0x{CS0_BASE + where[name]:08X}")
    table += bytes(4)
    if TABLE_OFFSET + len(table) > ZONE_A[0]:
        raise DiscError("decor table overflows into the tiles")
    (args.out_dir / "table.bin").write_bytes(table)
    lines.insert(0, f"0x{TABLE_OFFSET:07X}={args.out_dir / 'table.bin'}")
    (args.out_dir / "blobs.txt").write_text("\n".join(lines) + "\n")
    print(f"-> {args.out_dir / 'blobs.txt'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DiscError, OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
''',
        'voice_banks': r'''#!/usr/bin/env python3
"""Table of the voice banks for the preload of option C (docs/archive/iter7_preload.md).

Each character k (0x00-0x19) has a file Ckk.PAC (name table MM.BIN 0x0605E334).
LoadPac (src/cdrom/cdrom.s, pac_load) walks its PACK header: chunks are
contiguous from the offset of the first one, sizes rounded down to a multiple
of 4. Chunk 1 is the voice bank, copied to sound RAM (side A 0x05A0AC00, side B
0x05A45600). This tool computes, for each k, the cart address and the size of
chunk 1 exactly as pac_load does, and writes the table read by vs_preload:

  8-byte entries {cart address of chunk 1, bytes}, index = character k

Output: <out_dir>/voice_table.bin and <out_dir>/blobs.txt ("offset=file", for
build_cart.py --blob), at VOICE_TABLE_OFFSET (free part of the boot area, below
the decor table at 0x002000).
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from build_cart import CS0_BASE, ISO_OFFSET
from inventory_disc import LOGICAL_SECTOR_SIZE, DiscError, Iso9660, cue_data_track

VOICE_TABLE_OFFSET = 0x001C00   # cart 0x22001C00 (VOICE_TABLE in src/cdrom/cdrom.s)
CHARACTERS = 0x1A
PACK = b"PACK"


def bank_chunk(pac: bytes) -> tuple[int, int]:
    """(offset in the file, bytes) of chunk 1, as pac_load walks the header."""
    stream = struct.unpack_from(">I", pac, 8)[0]
    for k in range(2):
        magic, size = pac[16 * k : 16 * k + 4], struct.unpack_from(">I", pac, 16 * k + 12)[0]
        if magic != PACK:
            raise DiscError(f"no PACK entry {k}")
        size &= ~3
        if k == 1:
            return stream, size
        stream += size
    raise AssertionError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cue", type=Path, help="cue sheet of the KOF95 disc")
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()
    iso = Iso9660(cue_data_track(args.cue))
    try:
        files = {name.upper(): (size, lba) for name, size, lba in iso.files()}
        table = bytearray()
        for k in range(CHARACTERS):
            name = f"C{k:02X}.PAC"
            size, lba = files[name]
            pac = iso.read_extent(lba, size)
            offset, nbytes = bank_chunk(pac)
            n = struct.unpack_from(">I", pac, offset)[0]
            if not 4 + 8 * n < nbytes <= 0x3AA00:   # directory, then data; fits in side B
                raise DiscError(f"{name}: chunk 1 is not a voice bank ({n} entries, {nbytes} bytes)")
            address = CS0_BASE + ISO_OFFSET + lba * LOGICAL_SECTOR_SIZE + offset
            table += struct.pack(">II", address, nbytes)
            print(f"{name}  chunk 1 at +0x{offset:05X}  {nbytes:6d} bytes  {n:2d} sounds  -> 0x{address:08X}")
    finally:
        iso.close()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "voice_table.bin").write_bytes(table)
    (args.out_dir / "blobs.txt").write_text(f"0x{VOICE_TABLE_OFFSET:07X}={args.out_dir / 'voice_table.bin'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
''',
        'compact_track': r'''#!/usr/bin/env python3
"""Compact data track (docs/archive/menage.md): the same ISO9660 volume without its duplicates.

    compact_track.py <disc.cue> <cart_rom> <out_dir> [--strip]

Writes <out_dir>/track01.bin (Mode 1/2352) and <out_dir>/compact.cue (data track only). The tools that read
the disc (patch_kof95.py, precalc_decors.py, voice_banks.py, build_cart.py) take this cue instead of the
disc's: the rule ROM = 0x400000 + LBA * 2048 and the game's file layer do not change, only the directory.
The CD in the drive stays the original disc (music).

- Sectors 0-24 (IP, volume descriptors, path tables, root directory at LBA 20-24) are kept in place; the file
  records of the root directory get their new extent and size, the primary descriptor its new volume size.
- Files follow in their original order, each from a sector boundary; the 150 empty sectors at the end go.
- Ckk.PAC / Ckk.APM: the APM is chunk 1 of the PAC, byte for byte. Chunk 0 of the PAC gets padding (its
  size field grows, later offsets move) so that chunk 1 starts on a sector; the APM record points there.
  pac_load walks the chunks from the first offset with the size fields, so the padding is never read.
- Files that are byte copies of a part of the cart ROM (mpr-18811, at 0x200000 in the cart) get an empty
  record (extent 0, size 0): the game reads them in the cart; their only reader by name is the ROM build list
  of MM.BIN, whose destinations are cart addresses (docs/archive/menage.md 1.4).
- Files with the same content share one extent.

--strip (clean image, the tiles are all raw in the cart: tools/char_raw.py) also removes what nothing reads any
more (docs/archive/menage.md 1):
- chunk 0 of the Ckk.PAC (compressed character tiles) keeps its 8-byte header (tile count, read by pac_load and
  0x060498C8), then the padding up to chunk 1;
- the tile files 001A-003E.PRS keep their first 16 bytes: the header (tile count at +4) and the 8 bytes that
  char_raw compares for a character side;
- the .PCM files (skipped by the list loader of `0`) get an empty record.
The tools that decompress (precalc_decors.py, char_raw.py) then read the tiles from the original disc (--source).

The ECC/EDC of the sectors stay zero: only these tools read the track.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from inventory_disc import LOGICAL_SECTOR_SIZE, RAW_SECTOR_SIZE, DiscError, Iso9660, cue_data_track

SECTOR = LOGICAL_SECTOR_SIZE
ROOT_LBA, ROOT_SECTORS = 20, 5
FIRST_FILE_LBA = 25
PVD_LBA, VOLUME_SIZE_FIELD = 16, 80
PACK = b"PACK"


def le_be32(value: int) -> bytes:
    return struct.pack("<I", value) + struct.pack(">I", value)


def pac_chunks(pac: bytes) -> list[tuple[int, int]]:
    """(offset, size field) of each PACK entry; offsets as pac_load walks them."""
    chunks, k = [], 0
    stream = struct.unpack_from(">I", pac, 8)[0]
    while pac[16 * k:16 * k + 4] == PACK:
        size = struct.unpack_from(">I", pac, 16 * k + 12)[0]
        chunks.append((stream, size))
        stream += size & ~3
        k += 1
    return chunks


def align_chunk1(pac: bytes, strip: bool = False) -> tuple[bytes, int]:
    """PAC whose chunk 1 starts on a sector (chunk 0 padded, or with strip cut to its 8-byte header and padded);
    returns (pac, offset of chunk 1)."""
    chunks = pac_chunks(pac)
    (o0, s0), (o1, _) = chunks[0], chunks[1]
    if s0 & 3 or o0 + s0 != o1:
        raise DiscError("chunk 0 is not followed directly by chunk 1")
    keep = 8 if strip else s0
    new_o1 = o0 + keep + (-(o0 + keep) % SECTOR)
    shift = new_o1 - o1
    out = bytearray(pac[:o0 + keep]) + bytes(new_o1 - o0 - keep) + pac[o1:]
    struct.pack_into(">I", out, 12, new_o1 - o0)
    for k in range(1, len(chunks)):
        offset = struct.unpack_from(">I", out, 16 * k + 8)[0]
        struct.pack_into(">I", out, 16 * k + 8, offset + shift)
    if pac_chunks(bytes(out))[1][0] != new_o1:
        raise DiscError("padded PACK header is inconsistent")
    return bytes(out), new_o1


def mode1_sector(lba: int, data: bytes) -> bytes:
    m, s, f = (lba + 150) // 4500, (lba + 150) // 75 % 60, (lba + 150) % 75
    bcd = lambda v: (v // 10) << 4 | v % 10
    head = b"\x00" + b"\xff" * 10 + b"\x00" + bytes((bcd(m), bcd(s), bcd(f), 1))
    return head + data + bytes(RAW_SECTOR_SIZE - 16 - SECTOR)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cue", type=Path)
    p.add_argument("cart_rom", type=Path)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--strip", action="store_true", help="also remove the compressed tiles and the .PCM files")
    a = p.parse_args()
    rom = a.cart_rom.read_bytes()
    iso = Iso9660(cue_data_track(a.cue))
    try:
        head = bytearray(iso.read_extent(0, FIRST_FILE_LBA * SECTOR))
        entries = sorted(iso.files(), key=lambda e: e[2])          # (name, size, lba), disc order
        if any("/" in n for n, _, _ in entries) or iso.root != (ROOT_LBA, ROOT_SECTORS * SECTOR):
            raise DiscError("expected a single root directory at LBA 20-24")
        data = {n: iso.read_extent(lba, size) for n, size, lba in entries}
    finally:
        iso.close()

    log, new_data, alias = [], {}, {}            # alias: name -> (owner, byte offset) or None (empty)
    for n, _, _ in entries:
        if len(data[n]) >= 64 and rom.find(data[n]) >= 0:
            alias[n] = None
            log.append(f"{n:13} empty record: copy of the cart ROM at +0x{rom.find(data[n]):06X}")
    if a.strip:
        for n, _, _ in entries:
            if n.endswith(".PCM"):
                alias[n] = None
                log.append(f"{n:13} empty record: never loaded (the list loader skips .pcm)")
            elif n.endswith(".PRS") and 0x1A <= int(n[:4], 16) <= 0x3E and n not in alias:
                new_data[n] = data[n][:16]
                log.append(f"{n:13} cut to 16 bytes (raw tiles in the cart)")
    for n, _, _ in entries:
        apm = n[:-4] + ".APM"
        if n.startswith("C") and n.endswith(".PAC") and apm in data:
            pac, o1 = align_chunk1(data[n], a.strip)
            if pac[o1:o1 + len(data[apm])] != data[apm]:
                raise DiscError(f"{apm} is not chunk 1 of {n}")
            new_data[n] = pac
            alias[apm] = (n, o1)
            log.append(f"{apm:13} -> {n} +0x{o1:X} (chunk 0: {o1 - pac_chunks(data[n])[0][0]} bytes, "
                       f"{'header and padding' if a.strip else 'padded'})")
    first = {}
    for n, _, _ in entries:
        if n not in alias and n not in new_data:
            twin = first.setdefault(data[n], n)
            if twin != n:
                alias[n] = (twin, 0)
                log.append(f"{n:13} -> {twin} (same content)")

    out = bytearray(head)
    where = {}                                    # name -> (lba, size)
    for n, _, _ in entries:
        if n in alias:
            continue
        body = new_data.get(n, data[n])
        where[n] = (len(out) // SECTOR, len(body))
        out += body + bytes(-len(body) % SECTOR)
    for n, target in alias.items():
        if target is None:
            where[n] = (0, 0)
        else:
            owner, offset = target
            where[n] = (where[owner][0] + offset // SECTOR, len(data[n]))
    sectors = len(out) // SECTOR

    # Root directory records, in place (same lengths).
    root = ROOT_LBA * SECTOR
    pos, seen = root, 0
    while pos < root + ROOT_SECTORS * SECTOR:
        length = out[pos]
        if length == 0:
            pos = (pos // SECTOR + 1) * SECTOR
            continue
        name = out[pos + 33:pos + 33 + out[pos + 32]].decode("ascii")
        name = name.split(";")[0].rstrip(".")
        if name in where:
            lba, size = where[name]
            out[pos + 2:pos + 10] = le_be32(lba)
            out[pos + 10:pos + 18] = le_be32(size)
            seen += 1
        pos += length
    if seen != len(where):
        raise DiscError(f"{seen} records rewritten, {len(where)} files")
    out[PVD_LBA * SECTOR + VOLUME_SIZE_FIELD:PVD_LBA * SECTOR + VOLUME_SIZE_FIELD + 8] = le_be32(sectors)

    a.out_dir.mkdir(parents=True, exist_ok=True)
    with (a.out_dir / "track01.bin").open("wb") as f:
        for lba in range(sectors):
            f.write(mode1_sector(lba, out[lba * SECTOR:(lba + 1) * SECTOR]))
    (a.out_dir / "compact.cue").write_text('FILE "track01.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n')

    # Check: every file reads back as before (PACs: padded copy).
    check = Iso9660(a.out_dir / "track01.bin")
    try:
        for n, size, lba in check.files():
            expect = b"" if alias.get(n, 0) is None else new_data.get(n, data[n])
            if check.read_extent(lba, size) != expect:
                raise DiscError(f"{n}: content differs after compaction")
    finally:
        check.close()
    old = len(head) // SECTOR + sum(-(-len(d) // SECTOR) for d in data.values())
    for line in log:
        print(line)
    print(f"{len(where)} files, {sectors} sectors ({sectors * SECTOR / 2**20:.2f} MiB; files of the disc: "
          f"{old} sectors) -> {a.out_dir / 'compact.cue'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (DiscError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)
''',
        'char_raw': r'''#!/usr/bin/env python3
"""CHAR_RAW test image (docs/archive/motifs_bruts.md): tile groups already decompressed in the ROM.

    char_raw.py <image.ss> <file_table.tsv> <cdrom.elf> <out.ss> [--log FILE]

<image.ss> is built with --defsym CHAR_RAW=1 (tools/build_c2.sh), DECOR_SAT=1 for room. The tiles of chunk 0 of the 26
C*.PAC, of 003F.PRS, 2009.PRS and of the small 001A-0033.PRS are decompressed here by the original decompressor 0x06007310 (sh2_interp),
placed in the free end of CS0, then in CS1 (Mednafen only: images over 32 MiB put the rest in CS1),
and the table char_raw_tab of the cart code gets the pairs {compressed source as the tile cache sees
it, raw tiles}. The output is 48 MiB; the end of CS1 stays 0xFF (cart ID byte 0x24FFFFFF). When everything fits
in CS0 (compact track, docs/archive/menage.md), the output is 32 MiB.
"""
from __future__ import annotations

import argparse
import struct
import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_kof95 import elf_symbols  # noqa: E402
from sh2_interp import SH2, Mem  # noqa: E402

CS0_BASE, CS0_SIZE, CS1_SIZE = 0x22000000, 0x2000000, 0x1000000
CS0_CACHED = 0x02000000
ID_KEEP = 0x10000                       # end of CS1 left 0xFF
BOOT_AREA, BOOT_USED = 0x200000, 0x2000  # boot area; IP (0x1800) + boot program below BOOT_USED
DECOMPRESS, GROUP_BUF, MM_BASE = 0x06007310, 0x060CDB10, 0x06002040
SRC = 0x06200008
HOOK = 0x060072D0                       # group handler, detoured by patch_kof95.py
PRS_003F_KEY = 0x222D1488               # entry 0x06007194 source: 003F.PRS + 8 in the relocated mpr-18811
PRS_2009_KEY = 0x22353888               # entry 0x06007204 source: 2009.PRS + 8 in the relocated mpr-18811


def decompress(body_with_header: bytes, mm: bytes) -> bytes:
    """All the groups of a tile file (8-byte header, then group offsets), as 0x060072D0 would."""
    data = body_with_header
    mem = Mem()
    high = mem.map(0x06000000, 0x100000)
    high[MM_BASE - 0x06000000: MM_BASE - 0x06000000 + len(mm)] = mm
    mem.map(SRC - 8, len(data) + 0x1000, data)
    cpu = SH2(mem)
    stack, ret = 0x060FF000, 0xDEAD0000
    out = bytearray()
    groups = struct.unpack_from(">I", data, 8)[0] // 4
    for g in range(groups):
        offset = struct.unpack_from(">I", data, 8 + 4 * g)[0]
        mem.w32(stack - 4, ret)
        cpu.r[9], cpu.r[10], cpu.r[15] = SRC + offset, GROUP_BUF, stack - 4
        cpu.call(DECOMPRESS, ret)
        assert cpu.r[15] == stack
        s = GROUP_BUF - 0x06000000
        out += high[s:s + 1024]
    count = struct.unpack_from(">I", data, 4)[0]
    assert len(out) >= count * 128, (len(out), count)
    return bytes(out)


def job(args):
    name, key, data, mm = args
    return name, key, decompress(data, mm)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image", type=Path)
    p.add_argument("table", type=Path)
    p.add_argument("elf", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--blobs", type=Path, help="blobs.txt of the build: the rest of the boot area is free too")
    p.add_argument("--dedup", action="store_true", help="each distinct 1 KiB group once; char_raw_tab gives a "
                   "table of group addresses per file (needs RAW_DEDUP=1)")
    p.add_argument("--free-mpr", action="store_true", help="clear the compressed bodies of 003F.PRS and 2009.PRS in "
                   "the relocated mpr-18811 (first 16 bytes kept) and use that room (needs MENU_RAW=1)")
    p.add_argument("--source", type=Path, help="disc cue to read the compressed tiles from (image built on a compact "
                   "track with --strip, tools/compact_track.py); the keys still come from the image")
    a = p.parse_args()
    source = {}
    if a.source:
        from inventory_disc import Iso9660, cue_data_track
        iso = Iso9660(cue_data_track(a.source))
        try:
            source = {n: iso.read_extent(lba, size) for n, size, lba in iso.files()
                      if n.endswith(".PAC") or n.endswith(".PRS")}
        finally:
            iso.close()

    img = bytearray(a.image.read_bytes())
    files = {}
    for line in a.table.read_text().splitlines()[1:]:
        path, _lba, size, off, _ = line.split("\t")
        files[path] = (int(off, 16), int(size))
    sym = elf_symbols(a.elf)
    tab, tab_end = sym["char_raw_tab"], sym["char_raw_tab_end"]

    mo, mz = files["MM.BIN"]
    mm = bytes(img[mo:mo + mz])
    word = struct.unpack_from(">H", mm, HOOK - MM_BASE)[0]
    if word != 0xD001:
        raise SystemExit(f"MM.BIN 0x{HOOK:08X} = 0x{word:04X}: image not built with CHAR_RAW=1")

    jobs = []
    for i in range(0x1A):
        name = f"C{i:02X}.PAC"
        off, size = files[name]
        head = img[off:off + 16]
        assert head[:4] == b"PACK"
        c_off, c_size = struct.unpack_from(">II", head, 8)
        # pac_load: chunk 0 starts at file + offset of the first chunk; the cache source is +8.
        chunk0 = bytes(img[off + c_off:off + c_off + c_size])
        if name in source:
            o, z = struct.unpack_from(">II", source[name], 8)
            if source[name][o:o + 8] != chunk0[:8]:
                raise SystemExit(f"{name}: chunk 0 header differs from the source disc")
            chunk0 = source[name][o:o + z]
        jobs.append((name, CS0_BASE + off + c_off + 8, chunk0, mm))
    # Tile files read in place in the relocated mpr-18811 (entries 0x06007194, 0x06007204).
    for name, key in (("003F.PRS", PRS_003F_KEY), ("2009.PRS", PRS_2009_KEY)):
        off, size = files[name]
        rel = key - 8 - CS0_BASE
        if name in source:
            prs = source[name]
            if img[rel:rel + len(prs)] != prs:
                raise SystemExit(f"{name} of the source disc differs from its mpr-18811 copy")
        elif size == 0:
            # Compact track (tools/compact_track.py): empty record, the file is only in mpr-18811 (which ends at
            # 0x400000); the decompressor reads only what its group table needs.
            prs = bytes(img[rel:0x400000])
        else:
            prs = bytes(img[off:off + size])
            if img[rel:rel + size] != prs:
                raise SystemExit(f"{name} of the track differs from its mpr-18811 copy")
        jobs.append((name, key, prs, mm))
    # Small .PRS copied to the low-RAM slots by cache_copy from the track (slot_copy keys);
    # 003D/003E.PRS: loaded whole by LoadFile to a character side in the menus (decor_read keys).
    for name in [f"{i:04X}.PRS" for i in range(0x1A, 0x34)] + ["003D.PRS", "003E.PRS"]:
        off, size = files[name]
        prs = bytes(img[off:off + size])
        if name in source:
            if source[name][:len(prs)] != prs:
                raise SystemExit(f"{name}: differs from the source disc")
            prs = source[name]
        jobs.append((name, CS0_BASE + off + 8, prs, mm))

    with Pool(min(16, len(jobs))) as pool:
        blocks = sorted(pool.map(job, jobs), key=lambda b: -len(b[2]))

    # Free areas: end of CS0 (after the image), CS1 except its end.
    start = (len(img) + 0x3FF) & ~0x3FF
    img.extend(b"\xFF" * (CS0_SIZE + CS1_SIZE - len(img)))
    free = [[start, CS0_SIZE], [CS0_SIZE, CS0_SIZE + CS1_SIZE - ID_KEEP]]
    if a.blobs:
        # Boot area 0x000000-0x200000: IP and boot program below BOOT_USED, then the blobs of the build.
        used = [(0, BOOT_USED)]
        for line in a.blobs.read_text().split():
            off, _, path = line.partition("=")
            off = int(off, 0)
            if off < BOOT_AREA:
                used.append((off, off + Path(path).stat().st_size))
        lo = 0
        for s_, e_ in sorted(used) + [(BOOT_AREA, BOOT_AREA)]:
            s_ &= ~0x3FF
            if s_ - lo >= 0x400:
                if any(img[lo:s_]):
                    raise SystemExit(f"boot area 0x{lo:X}-0x{s_:X} is not empty")
                free.insert(0, [lo, s_])
            lo = max(lo, (e_ + 0x3FF) & ~0x3FF)
    if a.free_mpr:
        if "menu_raw" not in sym:
            raise SystemExit("--free-mpr needs an image built with MENU_RAW=1 (003F.PRS is read by 0x060077A8)")
        # Bodies in the relocated mpr-18811 (cart 0x200000): 003F.PRS 0x0D1480 (533474 bytes), 2009.PRS 0x153880
        # (104406 bytes). Their first 16 bytes stay (header, tile count read at key - 4 by the original path).
        for start, size in ((0x2D1480, 533474), (0x353880, 104406)):
            img[start + 16:start + size] = bytes(size - 16)
            free.insert(0, [(start + 16 + 0x3FF) & ~0x3FF, (start + size) & ~0x3FF])
    if a.dedup != ("raw_dedup" in sym):
        raise SystemExit("--dedup and RAW_DEDUP=1 go together (char_raw_tab holds group tables, not raw tiles)")

    def take(n, align=0x400):
        area = next((f for f in free if f[1] - ((f[0] + align - 1) & -align) >= n), None)
        if area is None:
            raise SystemExit(f"no room left for {n} bytes")
        at = (area[0] + align - 1) & -align
        area[0] = at + n
        return at

    pairs, log = [], []
    if a.dedup:
        where, unique = {}, 0
        for name, key, raw in blocks:
            table = bytearray()
            for g in range(0, len(raw), 0x400):
                group = raw[g:g + 0x400]
                if group not in where:
                    at = take(0x400)
                    img[at:at + 0x400] = group
                    where[group] = CS0_BASE + at
                    unique += 1
                table += struct.pack(">I", where[group])
            at = take(len(table), 4)
            img[at:at + len(table)] = table
            pairs.append((key, CS0_BASE + at))
            log.append(f"{name}: source 0x{key:08X} -> group table 0x{CS0_BASE + at:08X} ({len(raw) // 0x400} groups)")
        total = sum(len(b[2]) // 0x400 for b in blocks)
        log.append(f"dedup: {total} groups, {unique} distinct ({(total - unique) * 0x400} bytes saved)")
    for name, key, raw in ([] if a.dedup else blocks):
        area = next((f for f in free if f[1] - f[0] >= len(raw)), None)
        if area is None:
            log.append(f"{name}: {len(raw)} bytes, no room left (original path)")
            continue
        at = area[0]
        area[0] = (at + len(raw) + 0x3FF) & ~0x3FF
        img[at:at + len(raw)] = raw
        pairs.append((key, CS0_BASE + at))
        log.append(f"{name}: source 0x{key:08X} -> raw 0x{CS0_BASE + at:08X} ({len(raw)} bytes)")
    if 8 * len(pairs) + 4 > tab_end - tab:
        raise SystemExit("char_raw_tab too small")
    t = tab - CS0_CACHED
    if any(img[t:tab_end - CS0_CACHED]):
        raise SystemExit(f"char_raw_tab at 0x{tab:08X} is not empty in the image")
    for i, (key, raw) in enumerate(sorted(pairs)):
        struct.pack_into(">II", img, t + 8 * i, key, raw)
    if img.count(0xFF, CS0_SIZE) == len(img) - CS0_SIZE:
        del img[CS0_SIZE:]          # nothing in CS1: a 32 MiB image (CS0 only, MiSTer core "ROM 32M")
    a.out.write_bytes(img)
    used = sum(len(b[2]) for b in blocks)
    print("\n".join(log))
    left = ", ".join(f"0x{CS0_BASE + lo:08X}+0x{hi - lo:X}" for lo, hi in free)
    print(f"{len(pairs)}/{len(blocks)} files, {used} raw bytes; left {left}; table 0x{tab:08X}; -> {a.out} ({len(img)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
        'taunt': r'''#!/usr/bin/env python3
"""TAUNT data (docs/archive/manques_mvs.md): the provocations of the order screen, built from the Saturn data only.

    taunt.py <image.ss> <cdrom.elf> <char_raw.log> <out.ss>

<image.ss> is the clean image (tools/build_clean.sh, CHAR_RAW + RAW_DEDUP, char_raw.py --dedup) assembled with
TAUNT=1. For each character k (bank k, 0-0x19), its combat taunt (animation 0x5E, in the relocated mpr-18811) is
copied as animation 0xB0 + k of bank 0x1A (the order-screen bank, tile base 0):
  - its pieces are copied to free entries of the piece table of bank 0x1A (no animation of the bank uses them),
    tile field renumbered into a range of the tile cache from FIRST;
  - the range has a group table (char_raw_tab entry, key = its own address): each 8-tile group points to the raw
    group already in the image (group table of the C*.PAC, 2009.PRS past C09 for character 9). No tile is copied;
  - records, images, pieces and group table go to the system area of the data track (sectors 2-15, never read),
    within reach of the 24-bit image addresses of the records (68k address A -> cart 0x22180100 + A);
  - taunt_par = {FIRST, group count * 8, key}.
Every word written is checked: anim list entries 0xB0-0xC9 must hold the filler of the bank, piece entries must be
unused, the system area and taunt_par must be zero.
"""
from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_kof95 import elf_symbols  # noqa: E402

CS0 = 0x22000000
BIAS = 0x180100                 # cart offset = 68k address + BIAS (relocated mpr-18811)
ANIM_MAP = 0x28E5D0             # cart offset of the animation -> entry tables (MM.BIN 0x0600FB04: 0x2228E5D0)
BANK, TAUNT, NEW = 0x1A, 0x5E, 0xB0
FIRST = 0x5400                  # after side A (0x3FA0 + 0x13A4) on the order screen
AREA = (0x401000, 0x408000)     # data track sectors 2-15 (0x400000 + LBA * 2048)


class Img:
    def __init__(self, data: bytearray):
        self.d = data

    def l(self, a: int) -> int:           # 68k address
        return struct.unpack_from(">I", self.d, a + BIAS)[0]

    def w(self, a: int) -> int:
        return struct.unpack_from(">H", self.d, a + BIAS)[0]

    def b(self, a: int) -> int:
        return self.d[a + BIAS]


def anim_entry(img: Img, k: int, anim: int) -> int:
    off = struct.unpack_from(">I", img.d, ANIM_MAP + 4 * k)[0]
    return img.d[ANIM_MAP + off + 2 * anim + 1]


def records(img: Img, a: int) -> list[bytes]:
    out = []
    for _ in range(400):
        r = bytes(img.d[a + BIAS:a + BIAS + 6])
        out.append(r)
        if r[0] in (0xFE, 0xFF):
            return out
        a += 6
    raise SystemExit(f"animation at ${a:06X}: no end")


def image_entries(img: Img, f: int) -> list[bytes]:
    out = []
    for _ in range(40):
        e = bytes(img.d[f + BIAS:f + BIAS + 6])
        out.append(e)
        if not struct.unpack_from(">H", e, 4)[0] & 0x2000:
            return out
        f += 6
    raise SystemExit(f"image at ${f:06X}: no end")


def mask_width(dims: int) -> int:
    """Bytes per column mask: one up to 8 rows, a 16-bit word past 8 rows (pieces 0x95, 0xA5...)."""
    return 2 if dims >> 4 > 8 else 1


def piece_bytes(img: Img, p: int) -> bytes:
    dims = img.b(p)
    n = 4 + (dims & 0xF) * mask_width(dims)
    return bytes(img.d[p + BIAS:p + BIAS + n + (n & 1)])


def piece_tiles(pc: bytes) -> tuple[int, int]:
    first = struct.unpack_from(">H", pc, 2)[0]
    n = (pc[0] & 0xF) * mask_width(pc[0])
    return first, sum(bin(x).count("1") for x in pc[4:4 + n])


def used_pieces(img: Img, k: int) -> set[int]:
    lst = img.l(0x80000 + 4 * k)
    used = set()
    for a in {img.l(lst + 4 * i) for i in range(256)}:
        for _ in range(300):
            if not 0x80000 <= a < 0x280000:
                break
            c = img.b(a)
            if c in (0xFE, 0xFF):
                break
            if c < 0xFA:
                f = img.l(a) & 0xFFFFFF
                for _ in range(40):
                    if not 0x80000 <= f < 0x280000:
                        break
                    wd = img.w(f + 4)
                    used.add(wd & 0x1FF)
                    if not wd & 0x2000:
                        break
                    f += 6
            a += 6
    return used


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image", type=Path)
    p.add_argument("elf", type=Path)
    p.add_argument("log", type=Path, help="char_raw.log of the clean build (group tables of the tile files)")
    p.add_argument("out", type=Path)
    a = p.parse_args()
    data = bytearray(a.image.read_bytes())
    img = Img(data)
    sym = elf_symbols(a.elf)
    for s in ("taunt_stub", "taunt_par", "char_raw_tab", "raw_dedup"):
        if s not in sym:
            raise SystemExit(f"symbol {s} missing: image not built with TAUNT=1 and RAW_DEDUP=1")
    gtab = {}
    for line in a.log.read_text().splitlines():
        m = re.match(r"(\S+): source 0x(\w+) -> group table 0x(\w+) \((\d+) groups\)", line)
        if m:
            gtab[m[1]] = (int(m[3], 16) - CS0, int(m[4]))

    def group_addr(name: str, g: int) -> int:
        off, n = gtab[name]
        if g >= n:
            raise SystemExit(f"{name}: group {g} beyond its {n} groups")
        return struct.unpack_from(">I", data, off + 4 * g)[0]

    # Bank 0x1A: identity animation map, filler entries, free pieces.
    lst1a, pt1a = img.l(0x80000 + 4 * BANK), img.l(0x80080 + 4 * BANK)
    filler = img.l(lst1a + 4 * 0xFF)
    free = sorted(set(range(0x200)) - used_pieces(img, BANK))
    log = [f"bank 0x1A: list ${lst1a:06X}, pieces ${pt1a:06X}, {len(free)} free pieces, filler ${filler:06X}"]

    chars = []
    for k in range(0x1A):
        if anim_entry(img, BANK, NEW + k) != NEW + k:
            raise SystemExit(f"bank 0x1A: animation 0x{NEW + k:02X} is not mapped to its own entry")
        if img.l(lst1a + 4 * (NEW + k)) != filler:
            raise SystemExit(f"bank 0x1A: entry 0x{NEW + k:02X} is not the filler")
        lst, pt = img.l(0x80000 + 4 * k), img.l(0x80080 + 4 * k)
        recs = records(img, img.l(lst + 4 * anim_entry(img, k, TAUNT)))
        frames = list(dict.fromkeys(struct.unpack(">I", r[:4])[0] & 0xFFFFFF for r in recs if r[0] < 0xFA))
        imgs = {f: image_entries(img, f) for f in frames}
        pieces = {}
        for ents in imgs.values():
            for e in ents:
                idx = struct.unpack_from(">H", e, 4)[0] & 0x1FF
                pieces.setdefault(idx, piece_bytes(img, img.l(pt + 4 * idx)))
        groups = sorted({t // 8 for pc in pieces.values() for t in
                         range(piece_tiles(pc)[0] - 0x1000, sum(piece_tiles(pc)) - 0x1000)})
        chars.append((k, recs, frames, imgs, pieces, groups))

    # Tile range: per character, its groups in order (a piece's consecutive tiles stay consecutive).
    table, number = [], {}
    for k, *_, groups in chars:
        name = f"C{k:02X}.PAC"
        n = gtab[name][1]
        for g in groups:
            number[k, g] = FIRST + 8 * len(table)
            table.append(group_addr(name, g) if g < n else group_addr("2009.PRS", g - n))
    if FIRST + 8 * len(table) > 0x8000:
        raise SystemExit("tile range beyond 0x8000")

    out = bytearray()
    at = AREA[0]

    def put(blob: bytes) -> int:
        nonlocal out
        while len(out) & 3:
            out += b"\0"
        pos = AREA[0] + len(out)
        out += blob
        return pos

    gt = put(b"".join(struct.pack(">I", x) for x in table))
    slots = iter(free)
    n_pieces = n_entries = 0
    for k, recs, frames, imgs, pieces, groups in chars:
        new_slot = {}
        for idx, pc in pieces.items():
            first, cnt = piece_tiles(pc)
            t = first - 0x1000
            g, r = divmod(t, 8)
            new_first = number[k, g] + r
            # the whole run must be consecutive in the range
            last_g = (t + cnt - 1) // 8
            if cnt and number[k, last_g] - number[k, g] != 8 * (last_g - g):
                raise SystemExit(f"bank {k:X} piece {idx:X}: tiles not consecutive")
            pcn = bytearray(pc)
            struct.pack_into(">H", pcn, 2, new_first)
            try:
                slot = next(slots)
            except StopIteration:
                raise SystemExit("bank 0x1A: no free piece left")
            pa = put(bytes(pcn)) - BIAS
            off = pt1a + 4 * slot + BIAS
            struct.pack_into(">I", data, off, pa)
            new_slot[idx] = slot
            n_pieces += 1
        new_frame = {}
        for f in frames:
            ents = bytearray()
            for e in imgs[f]:
                wd = struct.unpack_from(">H", e, 4)[0]
                ents += e[:4] + struct.pack(">H", (wd & 0xFE00) | new_slot[wd & 0x1FF])
                n_entries += 1
            new_frame[f] = put(bytes(ents)) - BIAS
            if new_frame[f] >> 24:
                raise SystemExit("image beyond the 24-bit reach")
        rs = bytearray()
        for r in recs:
            if r[0] < 0xFA:
                f = struct.unpack(">I", r[:4])[0] & 0xFFFFFF
                rs += struct.pack(">I", (r[0] << 24) | new_frame[f]) + r[4:]
            else:
                rs += r
        ra = put(bytes(rs)) - BIAS
        struct.pack_into(">I", data, lst1a + 4 * (NEW + k) + BIAS, ra)
        log.append(f"character {k:2X}: {len(recs)} records, {len(frames)} images, {len(pieces)} pieces, "
                   f"{len(groups)} groups, animation 0x{NEW + k:02X} at ${ra:06X}")
    if AREA[0] + len(out) > AREA[1]:
        raise SystemExit(f"system area full: {len(out)} bytes")
    if any(data[AREA[0]:AREA[0] + len(out)]):
        raise SystemExit("system area of the track is not empty")
    data[AREA[0]:AREA[0] + len(out)] = out

    # char_raw_tab: append {key, group table} (linear search up to a zero key); taunt_par.
    tab = sym["char_raw_tab"] - 0x02000000
    end = sym["char_raw_tab_end"] - 0x02000000
    i = tab
    while struct.unpack_from(">I", data, i)[0]:
        i += 8
    if i + 12 > end:
        raise SystemExit("char_raw_tab full")
    key = CS0 + gt
    struct.pack_into(">II", data, i, key, CS0 + gt)
    par = sym["taunt_par"] - 0x02000000
    if any(data[par:par + 12]):
        raise SystemExit("taunt_par is not empty")
    struct.pack_into(">III", data, par, FIRST, 8 * len(table), key)
    a.out.write_bytes(data)
    print("\n".join(log))
    print(f"{n_pieces} pieces, {n_entries} image entries, {len(table)} groups: tiles 0x{FIRST:04X}-0x"
          f"{FIRST + 8 * len(table) - 1:04X}; {len(out)} bytes at 0x{CS0 + AREA[0]:08X}; key 0x{key:08X}; "
          f"{len(free) - n_pieces} free pieces left -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
    },
)


def load_modules(sources, folder):
    """Write the modules to a folder and import them (real files: the worker processes can import them too)."""
    for name, src in sources.items():
        sys.modules.pop(name, None)
        with open(os.path.join(folder, name + '.py'), 'w', encoding='utf-8') as f:
            f.write(src)
    sys.path.insert(0, folder)
    importlib.invalidate_caches()
    return {n: importlib.import_module(n) for n in sources}

def call(mod, *argv):
    """Run a module's command-line entry point, its output going to the log."""
    old = sys.argv
    sys.argv = [mod.__name__ + '.py', *argv]
    try:
        r = mod.main()
    finally:
        sys.argv = old
    if r:
        raise RuntimeError(f'{mod.__name__} failed ({r})')

def build(version, cue, rom, out_dir):
    v = VERSIONS[version]
    os.makedirs(out_dir, exist_ok=True)
    ss = os.path.join(out_dir, f'kof95_cart_{version}.ss')
    log = io.StringIO()
    with tempfile.TemporaryDirectory() as t:
        mods = os.path.join(t, 'modules')
        os.makedirs(mods)
        m = load_modules(v['modules'], mods)
        boot, elf = os.path.join(t, 'boot.bin'), os.path.join(t, 'cdrom.elf')
        open(boot, 'wb').write(zlib.decompress(base64.b64decode(v['boot'])))
        open(elf, 'wb').write(zlib.decompress(base64.b64decode(v['elf'])))
        p = os.path.join(t, 'p')
        disc = cue
        if version == 'noloading':
            # Clean image: data track without duplicates, compressed tiles and .PCM; every tile stored raw.
            cue = os.path.join(t, 'compact', 'compact.cue')
            ss_c2 = os.path.join(t, 'c2.ss')
        args = [cue, rom, boot, ss_c2 if version == 'noloading' else ss, '--run-from-cart',
                '--replace', '0=' + os.path.join(p, '0'), '--replace', 'MM.BIN=' + os.path.join(p, 'MM.BIN')]
        with contextlib.redirect_stdout(log):
            if version == 'noloading':
                print('* compacting the data track', file=sys.stderr)
                call(m['compact_track'], disc, rom, os.path.join(t, 'compact'), '--strip')
                print('* preparing the stage tiles and the voice table', file=sys.stderr)
                call(m['precalc_decors'], '--sat', '--source', disc, cue, os.path.join(t, 'decors'))
                call(m['voice_banks'], cue, os.path.join(t, 'voice'))
            print('* patching the game files', file=sys.stderr)
            call(m['patch_kof95'], cue, elf, p)
            if version == 'noloading':
                blobs = os.path.join(t, 'blobs.txt')
                with open(blobs, 'w') as f:
                    for d in ('decors', 'voice', 'p'):
                        f.write(open(os.path.join(t, d, 'blobs.txt')).read())
                args += ['--blobs', blobs, '--table', os.path.join(t, 'file_table.tsv')]
            print('* building the cartridge image', file=sys.stderr)
            call(m['build_cart'], *args)
            if version == 'noloading':
                print('* decompressing every tile with the game\'s own decompressor (about a minute)', file=sys.stderr)
                raw_log = io.StringIO()
                with contextlib.redirect_stdout(raw_log):
                    call(m['char_raw'], ss_c2, os.path.join(t, 'file_table.tsv'), elf, os.path.join(t, 'raw.ss'),
                         '--blobs', blobs, '--source', disc, '--free-mpr', '--dedup')
                log.write(raw_log.getvalue())
                with open(os.path.join(t, 'char_raw.log'), 'w') as f:
                    f.write(raw_log.getvalue())
                print('* adding the order-screen taunts', file=sys.stderr)
                call(m['taunt'], os.path.join(t, 'raw.ss'), elf, os.path.join(t, 'char_raw.log'), ss)
        sys.path.remove(mods)
    data = open(ss, 'rb').read()
    mister = os.path.join(out_dir, f'kof95_cart_{version}_32M.bin')
    open(mister, 'wb').write(data + b'\xff' * (32 * 1024 * 1024 - len(data)))
    open(os.path.join(out_dir, f'kof95_cart_{version}.log'), 'w').write(log.getvalue())
    ok = True
    for path, ref in zip((ss, mister), v['sha']):
        h = hashlib.sha256(open(path, 'rb').read()).hexdigest()
        good = h == ref
        ok &= good
        print(f'{path}: {"OK, identical to the reference" if good else "DIFFERENT from the reference " + ref[:16]}')
    return ok

DEFAULT = 'noloading' if 'noloading' in VERSIONS else next(iter(VERSIONS))

def main():
    args = sys.argv[1:]
    version = args.pop(0) if args and args[0] in VERSIONS else DEFAULT
    if len(args) not in (2, 3):
        print(__doc__)
        return 1
    cue, rom = args[:2]
    out = args[2] if len(args) == 3 else '.'
    try:
        ok = build(version, cue, rom, out)
    except Exception as e:
        print(f'error: {e}', file=sys.stderr)
        return 2
    return 0 if ok else 3

if __name__ == '__main__':
    sys.exit(main())
