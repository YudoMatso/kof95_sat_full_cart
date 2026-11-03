#!/usr/bin/env python3
"""The King of Fighters '95 (Sega Saturn) - cartridge edition builder.

Builds a Saturn cartridge image holding the whole game, from your own dumps:

    python3 kof95_cart.py <variant> <disc.cue> <mpr-18811-mx.ic1> [output_dir]

    variant   pure | noloading
              pure       the original game, unchanged, running from the cartridge
              noloading  no loading screens, arcade timing, music kept between rounds

    disc.cue           The King of Fighters '95 (Japan), T-3101G, cue sheet with its .bin tracks
    mpr-18811-mx.ic1   the 2 MiB ROM cartridge sold with the game

Writes kof95_cart_<variant>.ss (Mednafen) and kof95_cart_<variant>_32M.bin (MiSTer, "ROM 32M" core),
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

VERSIONS['noloading'] = dict(
    sha=('883b66f687de9229a15c67cbb0d4ccdd8be29c84d9784c6751e58a7cbe5e872d', '5b786e0db4504040cf460847978b81eb9525cd80badc1882921a7fc9faa3a608'),
    boot='''
eNoBPADD/9EM0A0hAtEHkAshAdEG0gfTB2AWQxAiAo/7cgTQA0ArAAn/3yWJAAgiQMgABgfNgAAAJ9Ql/gCwFEAf8EgxE3o=
''',
    elf='''
eNrtnAtYW8ed6OccSUdHD2xJ2Bj8BIF52I6RAANp3EbiZRxjQwA7NHWiI4R4xAKEwASnbuM0iRet4hsS5ybebe5+pM3tddukZtts
1906/XBe19246YE4DUm7rWynqbvJTdw2pU6bL9z/f+YcNGbt9na7fXzfrfhGM78zc+Y9/5n5z4g7axvqBFEg8x+RrINvQZJLJ8Eu
I2RnNn1aRrLJClJIislG9CfESMQ1k9QQ4upghpjAHGD+GY9KJIca+j4zvP8JieRuRgNs1wzvf1EihdQQTCxlNP9llRLxUXPl95eN
SOQGaoCf0gznn/klifRQA/wPmuH8s1olsoeaK8efpUjkSWoAjzLD+6/YL4m3UAM8pBnOf2W9JN5GzZXLt3JcEj+fjQb4uGa491dN
SuK/+NBc+f1V05Lx4WY0wFbNcO+vzpSMj1ADrGiG939PMj42hObK5V8DcX95Gg2XNu8fk8zfpeYq/vdIZpUa4CbNcP7ZDsn8zhga
wHpmeP+cUcl8UUYDOMIMMaf8czsk8y+oAW7TDPd+7g8l8+ytaKBr9jHD++dP4hhg48DgYIb3L3pPkm+mBnizZjj/dU9I8q3UAC/R
DNc+692S3Pk5NFcYH3+yj5ofEnMrE6K61reeWNS1HeLY9Z7qOOkwqLlnicPlSB8y11hqhBq5hkytEUUl98WLvkWKK1uOi1WLjs0S
S1LIEaeW55TklKhZTsEpKNW+TJ/gFJ3i2AqnwWk4b3Zugj9j1aIp13R68a6X019JT5IcISrc5YwK7pIBY+luT9X9szFjeLYxn9iI
JW1SEJomiUWSy3wSGemW5N57JPv3iSR3R9Z+SMjak5Dx7OCktNhOmiabnoFaNRbnF5erde3iVJ2yFPJmVtI82XGTsnR0LvHBsV8S
y1mi+rNdE3nEEjI8sHfUniAPDE5XuZ2N7ok6YmnMV0pH7XEJ3lwU/UXQMNY5brUuDc22zz77MYlMPzRVrqT7ivzr2w34TC3Gupry
3JieLPSKh6QkmSpWHN9eHDT8b5GsxBJAGRYtXmS329P0eh67bqogRxirmMqxLYU07ZimuvIsyXZNrfIXja2PfmhbOrXGD/FiSYrr
inc1us8sCVXlVsaXvbI86PU7E87prHtz7l2rpE0vac/xuONWJd1jJ7f4nHFRXeKzNbqPvTUonid5JY354dmO2dAssbXPmkRyivQQ
FetQXPPMSsl86TkskWR+d0iSN50A+eKR0v7XBXCr4H5JsifJ2kuESGT4OdOsAWSaYcJw3DBpOGVQDTOGpOGC4aLhElT4KaNqnJmb
s+XJR+Rx81H5qDwhH5cn5VOyKs+Yj5jHzRPm4+ZJ8ymzap4xJ80XzBfNl2Qiy7JDzpSz5+bSNtmTJsXUbYraL0DHP2oaMx0wjc7N
2UvlerlJbpMVuVuOyiPyAeIj9SAd2kBCdZMoGZFHYYyMkjFyBCpWJg6SCXNTIfGQylQakLMPIA9HF+ZC8rEwUj3LidQkZ8uFskeu
lH3mtoUpy6PymHwE8vSvIFpkLTaHFl82xihFsWTSAfMlaRRTNqrSGI33CMYrjcse6SjGLU1g3NJxjF06JXdLKqYgzWAa5gMWhyXT
km0eky5YCi0eS6XFZx631M/NWQ6bHCaQz6Zsk8fYZKo0tpnqTU1GBeotauw2jRijxhFp1HTBdNF0SRqTYIRIRySHNC5lStnSUalQ
8kgTUqXkk+olSFtqkyYlRYK0pagEaUsHpAvQDl+F1r4IPpekU5JqxnI6zJlQukKzx1xp9pnrzU3mNrNi7rbKVoc105ptLbR6rJVW
n7Xe2mRtsyrSiLXbGrWOWEatB6yjliPWMctR6YD1iHUcynJcGpUu2I7Yxm1HbRO247bJuTloNcuUVXHlVPmKzpk9+QkJZEaRJz8u
svH/mvF102dF1YSjDISuBfrsKWnxPWTtuQPQL7uTU4Uoc1jYqbVUFhlBoohqLo4C9j3lns79sXi+sMOtuPLq4ySnyi0OGKsdKGdq
Hff/fEBh7xfvKu4sHi4+eFY6J543vyH8mDzrIWUzi8aW/sRXKG5x3P/BiPERZ+X+Rxw6qTLG3z3bNds5q0usxdkyDHwCMmvtOR/k
UXlUkstPi2ueB3fXBmnRJJEW/TspzqBj+2Dxw8VfaHSHFBjbdcHQOaIsyZYPGbpzq8ix90vs9Rb4E0ruS16fXeSTZ3Ll/9Z+0F0Y
39BzUMn2eBKXgiF1hQ/SzJYTPx9fQiwzy3oO3naw6MihFSPG9i9AyF9huLhw7NI+I4R1aGF/NSAmP8yxtC9VlvoKs68pElUb+hz7
Jkh9C3V9HWXSbbM9s92zKOWCID+UWYlsGwXjAtMH5mPimhfKyF8/f/389fPXz18//19+tHmMrlHfIC/7gyU5mXFJ9fls7enBXPV6
n21IuNFLn12nPfsIPoN5WJiQcZZh61N9jmEzMM6KxV8vfmHG81PH657gQXj/hmSNuHrAV7LyLfI2CefVOu83Ky2nfAlhPOuTxs68
8YzrIkBSZ15XXl1m1/78T46nXRfZk9eZty2zM7J+z0JbafHJyiJfji9nNBk3jJ6NG8ctm+1K3ri02R7JU/IipxsyFfsG2/rjCWHD
qbhNeVZJ88nSV7rSK04oIV9RgaCEjn3zroGtjsSxyOyeWTZXdkEZOmGerGqTSNl9Etl0VCIVaC5gPZ2dm96guGH+XZwU3OJr6x7Z
VuTCdcQ+42uFj9QVOalbHPeeI6/lzbixVh/ZHHqw9QGlNHvr6Fx8DexL5uJ2X5GyGGxBSZOXKqUpd5ZDqf4P/tWcP8b/6j4Za/uc
8Jr9kcVbLEWuLGeWKysdfN7f58A2UM240vKRRcRwQKbrrYseku0kuL/C/QDoQA5MrVeLykncMLVOLSwnCWNOrHx3xW5ovRasGZ/F
ZxlVEhVKKPuTpwyJUq1/dE7lTOccLu5oKStJkI5SaP9lObGcmDMIf1XOqrFc3B8mzU6T0zS22mlU3L4sjOmUkHi/vKGi4di5TfWQ
O1eOrT3ktiUv5lhyxAGH1534jb67UQ2Yc5mABkvAfIOuIAfUJTlRIhl9u8Eo/xM+sGf0gdnvm++7ja6XO6bCQdd0uMRxSGwqGzcn
CbSR8SxJT0/PGDckhRtLBwRwG5USeL586mYIe3OJI7Ft6uOK45QQXzTVhjs+nwx7vnZhNezOTOmuJEkXksJ4Zq6YNIyX54qjhoR5
ahu8ua3EEd+YJOMbcsUbvRCv89zN3vyECE9yIZSQyJ6qg1B1OUVNJdO12UVe2e88JJ4rCK44lycUCMv9RX7LgLWpBOv529c3ez2F
nmVx6cYSeJ4Fq1VnUswVGzPYeFLLsUYa3VDOgzPrzxoLXWoZW68GtbXqdH7I/YaxzBM3viGWeRIyjDNXi7u6qDrrDeKuKnXEbS35
sDI1nieu8pYCYINr2bS7CmNl72e8QUJu0Bmkvbw65IGQlpbcH28uvSlhenmF4vn2Yig1eUNw1eXVJ8TpzNR7xRlT5qYMWKvDftkp
QU7T2XNwLcY8434f9qNp9xLJUF0upR29HsyNoB8aInOwZzDMzUE/TEpy+CHQmfwA9qzvgF8E3M9I4tfLxDXqbcbRL3/NdN9Zk3if
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
Xh6u5fPgdcfCcP8XBuCqww==
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
            (docs/phase1_step5_patch.md); the call pointers of MM_CALLS go
            to functions of build/cdrom.elf (docs/iter3_decors.md); the
            instructions of MM_CODE_WORDS are replaced (docs/iter4_attente.md);
            the .m_* sections of the ELF overwrite the MM_WINDOWS
            (docs/iter8_a.md).
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
    ("dead asynchronous file queue (docs/iter6_ab.md)", 0x0607EE90, 0x0607EFDC),
    ("dead asynchronous file queue (0x0607F034: FsInit literal)", 0x0607F008, 0x0607F034),
    ("dead asynchronous file queue", 0x0607F038, 0x0607F0A0),
    ("dead asynchronous file queue", 0x0607F364, 0x0607F3BE),
    ("dead file queue: CD block function, unreferenced (docs/iter7_preload.md)", 0x0607F6C8, 0x0607F73C),
    ("dead file queue: LZSS decompressor, only reached through 0x0607F65E", 0x0607F770, 0x0607F8EC),
    ("file reader: LZSS header test, never taken (no LZSSV001 file)", 0x0607F65E, 0x0607F660),
    ("trapa #48 table: service 0x11 (docs/iter8_m.md)", 0x06085EAC, 0x06085EB0),
    ("trapa #48 table: service 0x15 (docs/iter9_rounds.md)", 0x06085EBC, 0x06085EC0),
]

# MM.BIN code overwritten by the .m_* sections of the ELF: (name, start, end). The
# bytes of each window are checked against the original (MM_SHA256) by the hash.
MM_WINDOWS = [
    ("loader: NOW LOADING display call 0x06007934 r1 = 2 (docs/iter8_a.md)", 0x06049718, 0x06049720),
    ("loader: literal 0x06007934, read by 0x06049718 and 0x0604972C only", 0x06049774, 0x06049778),
    ("name lookup: string compare 0x06004B12, only caller 0x06004AA0", 0x06004B10, 0x06004B3E),
    ("resets 0x06006B2E: slot table, map 0x00201100, VDP2 map 0x060CE000", 0x06006B54, 0x06006B80),
    ("name lookup 0x06004A78: first instructions (only entry; 0x06004AE6 is another function)", 0x06004A78, 0x06004A84),
    ("interrupt 0x06002880: literal of its 3rd call 0x0600672C", 0x060028F0, 0x060028F4),
    ("HU module linker 0x06004038 (bsr from 0x060040A8/0x060040DA, bsrf from 0x06004014)", 0x06004038, 0x0600408A),
    ("state 0x0602A308: braf to 0x0600D294 -> jmp (docs/iter8_d.md)", 0x0602A320, 0x0602A324),
    ("state 0x0602A308: literal of that braf, read by 0x0602A31E only", 0x0602A32C, 0x0602A330),
    ("state 0x0602A38C: next-state write 0x0602A3C2-0x0602A3CD (dead after the jmp)", 0x0602A3C2, 0x0602A3CA),
    ("state 0x0602A38C: literal 0x0502, read by 0x0602A3C2 only", 0x0602A3D4, 0x0602A3D8),
    # 0x0600AE3A/0x0600AE3C (read by 0x0600AC3A-0x0600AC4E) and 0x0600AE50 (0x0600AC8E/0x0600ACB2) stay
    ("background columns 0x0600AD34: loop 1 (entries 0x0600AD04/AD1E/AD34 only)", 0x0600AD60, 0x0600AE3A),
    ("background columns 0x0600AD34: loop 2 and its literals, up to 0x0600AF10", 0x0600AE54, 0x0600AF10),
    ("interrupt 0x06002880: NBG1 map copy call (0x060069B4 rewritten unchanged)", 0x060069AA, 0x060069B6),
    ("interrupt 0x06002880: literal 0x060F8400 of that call, read by 0x060069AA only", 0x06006A44, 0x06006A48),
    ("loader 0x0604A128: DBRA loop 0x0604A174-0x0604A184 (no branch or literal into it)", 0x0604A174, 0x0604A186),
    ("frame loop: literal 0x06006BE0, read by 0x060266D4/0x06026742/0x0602679C only (docs/iter8_m.md)", 0x06026A48, 0x06026A4C),
    ("cart check: sum routine 0x0600233C, only caller bsr 0x060022EC (docs/iter10_demarrage.md)", 0x0600233C, 0x0600235E),
    ("init: count of the fixed wait 0x0600219C-0x060021AA (mov #8,r2)", 0x0600219C, 0x0600219E),
    ("sound init 0x06025D44: wait for the slave after command 6 (bt 0x06025D78)", 0x06025D7C, 0x06025D7E),
    ("sound init 0x06025D44: frame wait of the 8-call loop (subc r14,r14; bt 0x06025DE6)", 0x06025DEC, 0x06025DF0),
    ("boot list 0x0604AB3C: NOW LOADING call 0x06007934 r1 = 1 (jsr @r0; sts.l pr,@-r15)", 0x0604ABD2, 0x0604ABD6),
    ("shared wait 0x06049652: entry (count, next state), reached as a state only", 0x06049652, 0x0604965C),
    ("music dispatcher: literal 0x0602B634, read by the 8 jsr 0x0602B6DA-0x0602B8BE only (docs/iter9_rounds.md)", 0x0602BA40, 0x0602BA44),
]

# Code run from the cart (.c_* sections, cached CS0 addresses), written as blobs for
# build_cart.py --blobs: (name, start, end). After the last background of the boot area.
CS0_CACHED = 0x02000000
CART_WINDOWS = [
    ("loader code (docs/iter8_a.md), end of the boot area", 0x021FC000, 0x02200000),
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
# Literal-pool words holding a call target, redirected to a symbol of the ELF:
# address -> (original target, symbol).
MM_CALLS = {
    0x06049B2C: (0x06007868, "decor_preload"),  # background preload, jsr at 0x06049764 and 0x0604979E
    0x0602A2E0: (0x06049652, "fight_wait"),  # next state of 0x0602A274: shared 9-frame wait (docs/iter5_attente.md)
    0x060028EC: (0x06002A2A, "snd_vbl"),  # VBlank-OUT interrupt, copy lists (docs/iter6_ab.md)
    0x0602A3D8: (0x0602A3DC, "snd_state"),  # next state of 0x0602A38C, before the first fight image
    # Not a literal originally: the 2 instructions "mov.l 0x06007A58,r10; bsr 0x06007310" (VDP2 path of the
    # background tiles), now the literal of the jmp below (docs/iter8_b.md).
    0x06007724: (0xDACCBDF3, "vdp2_group"),
}
# 16-bit instructions replaced in place: address -> (original, new) (docs/iter4_attente.md).
MM_CODE_WORDS = {
    0x0602A316: (0xE107, 0xE100),  # mov #7,r1 -> mov #0,r1: post-load countdown, 8 frames -> 1
    0x0600771C: (0x4101, 0xD001),  # shlr r1 -> mov.l @(1,PC),r0 (= vdp2_group, 0x06007724)
    0x0600771E: (0x319C, 0x402B),  # add r9,r1 -> jmp @r0
    0x06007720: (0x6112, 0x0009),  # mov.l @r1,r1 -> nop (delay slot)
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
    """Hash index of the name registry of MM.BIN for names_fast (docs/iter8_a.md), at
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
0x25C10000 (docs/iter1_chargements.md, 3.3). This tool runs the original
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

--sat (docs/compression_decors.md): the tiles are not placed. Each 00xx.SAT of
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
        for name in DECORS:
            size, lba = files[name + ".PRS"]
            prs = iso.read_extent(lba, size)
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
"""Table of the voice banks for the preload of option C (docs/iter7_preload.md).

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
