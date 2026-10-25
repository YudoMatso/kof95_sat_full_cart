#!/usr/bin/env python3
"""The King of Fighters '95 (Sega Saturn) - cartridge edition builder.

Builds a Saturn cartridge image holding the whole game, from your own dumps:

    python3 kof95_cart.py <version> <disc.cue> <mpr-18811-mx.ic1> [output_dir]

    version   pure
              pure       v1.0: the original game, unchanged, running from the cartridge

    disc.cue           The King of Fighters '95 (Japan), T-3101G, cue sheet with its .bin tracks
    mpr-18811-mx.ic1   the 2 MiB ROM cartridge sold with the game

Writes kof95_cart_<version>.ss (Mednafen) and kof95_cart_<version>_32M.bin (MiSTer, "ROM 32M" core),
then checks them against the reference SHA-256. Needs Python 3.8 or later, nothing else.

This file contains only original code: the build modules and the assembled SH-2 code of the
project. No data from the game is included; everything is taken from your dumps at build time.
"""
import base64, contextlib, hashlib, io, os, sys, tempfile, types, zlib

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


def load_modules(sources):
    for name in sources:
        sys.modules.pop(name, None)
    for name, src in sources.items():
        mod = types.ModuleType(name)
        mod.__file__ = name + '.py'
        sys.modules[name] = mod
    for name, src in sources.items():
        exec(compile(src, name + '.py', 'exec'), sys.modules[name].__dict__)
    return {n: sys.modules[n] for n in sources}

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
    m = load_modules(v['modules'])
    os.makedirs(out_dir, exist_ok=True)
    ss = os.path.join(out_dir, f'kof95_cart_{version}.ss')
    log = io.StringIO()
    with tempfile.TemporaryDirectory() as t:
        boot, elf = os.path.join(t, 'boot.bin'), os.path.join(t, 'cdrom.elf')
        open(boot, 'wb').write(zlib.decompress(base64.b64decode(v['boot'])))
        open(elf, 'wb').write(zlib.decompress(base64.b64decode(v['elf'])))
        p = os.path.join(t, 'p')
        args = [cue, rom, boot, ss, '--run-from-cart', '--replace', '0=' + os.path.join(p, '0'),
                '--replace', 'MM.BIN=' + os.path.join(p, 'MM.BIN')]
        with contextlib.redirect_stdout(log):
            if version == 'noloading':
                print('* precomputing the stage tiles with the game\'s own decompressor (about a minute)', file=sys.stderr)
                call(m['precalc_decors'], cue, os.path.join(t, 'decors'))
                call(m['voice_banks'], cue, os.path.join(t, 'voice'))
            print('* patching the game files', file=sys.stderr)
            call(m['patch_kof95'], cue, elf, p)
            if version == 'noloading':
                blobs = os.path.join(t, 'blobs.txt')
                with open(blobs, 'w') as f:
                    for d in ('decors', 'voice', 'p'):
                        f.write(open(os.path.join(t, d, 'blobs.txt')).read())
                args += ['--blobs', blobs]
            print('* building the cartridge image', file=sys.stderr)
            call(m['build_cart'], *args)
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

def main():
    if len(sys.argv) not in (4, 5) or sys.argv[1] not in VERSIONS:
        print(__doc__)
        return 1
    version, cue, rom = sys.argv[1:4]
    out = sys.argv[4] if len(sys.argv) == 5 else '.'
    try:
        ok = build(version, cue, rom, out)
    except Exception as e:
        print(f'error: {e}', file=sys.stderr)
        return 2
    return 0 if ok else 3

if __name__ == '__main__':
    sys.exit(main())
