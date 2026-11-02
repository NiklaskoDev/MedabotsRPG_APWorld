"""ROM identification, the seed identity block and the patch container.

A patch file (``.apmedabots``) never contains any game data. It holds a small description of what to change, which is
applied to the player's own ROM in three steps:

1. ``verify_rom``: the ROM must be a supported version, the patch must match this world's data, and the memory the
   patch writes to must still be blank.
2. ``apply_script_rewrites``: overwrite vanilla reward instructions, but only where the expected original bytes are
   found (so story scripts can never be damaged by a wrong ROM).
3. ``apply_tokens``: write the seed identity block.
"""
from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from typing import Any

import settings
from worlds.Files import APPatchExtension, APProcedurePatch, APTokenMixin, APTokenTypes

from .constants import GAME_NAME
from .data_loader import LocationDef, RomVersion, WorldData, get_world_data
from .rom_scripts import ScriptError, locate_script_region
from .version import world_version

META_FILE = "meta.json"
TOKEN_FILE = "token_data.bin"
PATCH_FORMAT = 1
BLANK_BYTE = 0xFF

IDENTITY_MAGIC = b"APMEDABT"
IDENTITY_FORMAT = 1
_IDENTITY = struct.Struct("<8sHH16s16sBB64s")
_MAX_NAME_BYTES = 64


class PatchError(Exception):
    """A problem the player can act on. The message is shown to them as is."""


# ---------------------------------------------------------------------------------------------------------------------
# ROM identification
# ---------------------------------------------------------------------------------------------------------------------
def identify_header(header: bytes, data: WorldData) -> RomVersion:
    """Match a ROM header (the 18 bytes at the header offset) to a supported version."""
    version = data.rom.identify(header)
    if version is not None:
        return version
    if (reason := data.rom.unsupported_reason(header)) is not None:
        raise PatchError(reason)
    supported = ", ".join(v.label for v in data.rom.versions)
    raise PatchError(f"This ROM is not a supported version of Medabots. Supported versions: {supported}.")


def identify_rom(rom: bytes, data: WorldData) -> RomVersion:
    info = data.rom
    end = info.header_offset + info.header_length
    if len(rom) < end:
        raise PatchError("This file is too small to be a Game Boy Advance ROM.")
    return identify_header(rom[info.header_offset:end], data)


# ---------------------------------------------------------------------------------------------------------------------
# Seed identity block
# ---------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ApIdentity:
    """Which multiworld slot a patched ROM belongs to. Stored inside the ROM, read back by the client."""

    slot: int
    seed_digest: bytes
    data_digest: bytes
    unverified: bool
    player_name: str

    @staticmethod
    def digest_seed(seed_name: str) -> bytes:
        return hashlib.sha256(seed_name.encode("utf-8")).digest()[:16]

    @staticmethod
    def digest_data(content_hash: str) -> bytes:
        return bytes.fromhex(content_hash)[:16]

    def pack(self, size: int) -> bytes:
        name = self.player_name.encode("utf-8")
        if len(name) > _MAX_NAME_BYTES:
            raise PatchError(f"Slot name {self.player_name!r} is too long.")
        raw = _IDENTITY.pack(IDENTITY_MAGIC, IDENTITY_FORMAT, self.slot, self.seed_digest, self.data_digest,
                             int(self.unverified), len(name), name.ljust(_MAX_NAME_BYTES, b"\0"))
        return raw.ljust(size, bytes([BLANK_BYTE]))

    @classmethod
    def unpack(cls, raw: bytes) -> ApIdentity | None:
        """Parse an identity block; ``None`` when the bytes are not one (for example an unpatched ROM)."""
        if len(raw) < _IDENTITY.size:
            return None
        magic, fmt, slot, seed, data_digest, flags, name_length, name = _IDENTITY.unpack_from(raw)
        if magic != IDENTITY_MAGIC or fmt != IDENTITY_FORMAT or name_length > _MAX_NAME_BYTES:
            return None
        return cls(slot, seed, data_digest, bool(flags & 1), name[:name_length].decode("utf-8", errors="replace"))


# ---------------------------------------------------------------------------------------------------------------------
# Patch contents
# ---------------------------------------------------------------------------------------------------------------------
def collect_rewrites(locations: list[LocationDef]) -> list[dict[str, str]]:
    """Script rewrites for the given locations. Overlapping rewrites are a data bug and are refused."""
    rewrites = [dict(loc.neutralize) for loc in locations if loc.neutralize]
    spans = sorted((int(r["offset"], 0), int(r["offset"], 0) + len(bytes.fromhex(r["expect"]))) for r in rewrites)
    for (_, end), (start, _) in zip(spans, spans[1:], strict=False):
        if start < end:
            raise PatchError(f"Two script rewrites overlap at script offset 0x{start:X}. This is a data error.")
    return rewrites


def write_patch(
    patch: MedabotsRPGProcedurePatch,
    *,
    data: WorldData,
    seed_name: str,
    slot: int,
    player_name: str,
    allow_unverified: bool,
    locations: list[LocationDef],
) -> None:
    """Fill a patch container for one player."""
    block_offset, block_size = data.memory_map.ap_block_offset, data.memory_map.ap_block_size
    if block_offset is None or block_size is None:
        raise PatchError("The memory map does not define where to store the seed identity block.")

    identity = ApIdentity(slot, ApIdentity.digest_seed(seed_name), ApIdentity.digest_data(data.content_hash),
                          not data.is_verified, player_name)
    meta = {
        "format": PATCH_FORMAT,
        "world_version": world_version(),
        "data_hash": data.content_hash,
        "allow_unverified": allow_unverified,
        "rewrites": collect_rewrites(locations),
    }
    patch.write_token(APTokenTypes.WRITE, block_offset, identity.pack(block_size))
    patch.write_file(META_FILE, json.dumps(meta).encode("utf-8"))
    patch.write_file(TOKEN_FILE, patch.get_token_binary())


def _load_meta(caller: APProcedurePatch, meta_file: str) -> dict[str, Any]:
    meta = json.loads(caller.get_file(meta_file))
    if meta.get("format") != PATCH_FORMAT:
        raise PatchError("This patch was made by an incompatible version of the Medabots RPG world.")
    return meta


class MedabotsRPGPatchExtension(APPatchExtension):
    game = GAME_NAME

    @staticmethod
    def verify_rom(caller: APProcedurePatch, rom: bytes, meta_file: str) -> bytes:
        meta, data = _load_meta(caller, meta_file), get_world_data()
        if meta["data_hash"] != data.content_hash:
            raise PatchError(
                f"This patch was generated with Medabots RPG world version {meta['world_version']}, but version "
                f"{world_version()} is installed. Install the matching version of the world to apply it."
            )
        if not data.is_verified and not meta["allow_unverified"]:
            raise PatchError("This build of the world has not been verified against a real ROM, so it will not patch.")
        identify_rom(rom, data)

        offset, size = data.memory_map.ap_block_offset, data.memory_map.ap_block_size
        region = rom[offset:offset + size]
        if len(region) != size or any(byte != BLANK_BYTE for byte in region):
            raise PatchError(
                f"The ROM already has data where the patch wants to write (offset 0x{offset:X}). "
                "Is it already patched, or modified by another tool? Use a clean, unmodified ROM."
            )
        return rom

    @staticmethod
    def apply_script_rewrites(caller: APProcedurePatch, rom: bytes, meta_file: str) -> bytes:
        meta, data = _load_meta(caller, meta_file), get_world_data()
        if not meta["rewrites"]:
            return rom
        try:
            region = locate_script_region(rom, data.rom)
        except ScriptError as exc:
            raise PatchError(str(exc)) from exc

        patched = bytearray(rom)
        for rewrite in meta["rewrites"]:
            expect, replace = bytes.fromhex(rewrite["expect"]), bytes.fromhex(rewrite["replace"])
            relative = int(rewrite["offset"], 0)
            start = region.start + relative
            if relative < 0 or relative + len(expect) > region.length:
                raise PatchError(f"A script rewrite at 0x{relative:X} lies outside the script region.")
            if bytes(patched[start:start + len(expect)]) != expect:
                raise PatchError(
                    f"Unexpected data at script offset 0x{relative:X}. This ROM differs from the one the world "
                    "was built for, so the patch was stopped before it could damage the game."
                )
            patched[start:start + len(replace)] = replace
        return bytes(patched)


class MedabotsRPGProcedurePatch(APProcedurePatch, APTokenMixin):
    game = GAME_NAME
    hash = None  # any of the four supported ROM versions is accepted; they are told apart by their header instead
    patch_file_ending = ".apmedabots"
    result_file_ending = ".gba"

    procedure = [
        ("verify_rom", [META_FILE]),
        ("apply_script_rewrites", [META_FILE]),
        ("apply_tokens", [TOKEN_FILE]),
    ]

    @classmethod
    def get_source_data(cls) -> bytes:
        with open(settings.get_settings().medabots_rpg_settings.rom_file, "rb") as rom_file:
            return rom_file.read()
