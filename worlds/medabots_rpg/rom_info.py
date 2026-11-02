"""Identifying a Medabots ROM. Free of Archipelago imports so the developer tools can use it on their own."""
from __future__ import annotations

from .data_loader import RomVersion, WorldData


class RomError(Exception):
    """A problem with a ROM or a patch that the player can act on. The message is shown to them as is."""


def identify_header(header: bytes, data: WorldData) -> RomVersion:
    """Match a ROM header (the 18 bytes at the header offset) to a supported version."""
    version = data.rom.identify(header)
    if version is not None:
        return version
    if (reason := data.rom.unsupported_reason(header)) is not None:
        raise RomError(reason)
    supported = ", ".join(v.label for v in data.rom.versions)
    raise RomError(f"This ROM is not a supported version of Medabots. Supported versions: {supported}.")


def identify_rom(rom: bytes, data: WorldData) -> RomVersion:
    info = data.rom
    end = info.header_offset + info.header_length
    if len(rom) < end:
        raise RomError("This file is too small to be a Game Boy Advance ROM.")
    return identify_header(rom[info.header_offset:end], data)
