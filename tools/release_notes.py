#!/usr/bin/env python3
"""Release helper for the Tag and Release workflows.

    python tools/release_notes.py --derive-tag [--suffix rc.1]
    python tools/release_notes.py --tag v0.1.0 --notes-out notes.md

``--derive-tag`` prints the tag to create, ``v<world_version>`` with an optional ``-suffix`` such as ``-rc.1``. The
version always comes from the manifest, so a tag can never disagree with the world it releases.

``--tag`` checks a tag against the manifest, takes the matching section from CHANGELOG.md (a missing section is an
error, so a release can never go out without notes), and prints ``prerelease=true|false``. Versions below 1.0.0 and
tags with a suffix are pre-releases.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUFFIX = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.]*$")
TAG = re.compile(r"^v(?P<version>(?P<major>\d+)\.\d+\.\d+)(?P<suffix>-[0-9A-Za-z][0-9A-Za-z.]*)?$")

PRERELEASE_NOTICE = (
    "> **Pre-release.** Generation, the patcher and the client are implemented and tested, but the game's memory "
    "layout and check locations have not been verified against a real ROM yet. Generating a seed requires "
    "`allow_unverified_build: true`."
)


class ReleaseError(Exception):
    """The release cannot be made; the message says why."""


@dataclass(frozen=True)
class Release:
    version: str
    prerelease: bool
    notes: str


def parse_tag(tag: str) -> tuple[str, str, bool]:
    """Return (version, suffix, is_pre_1_0) of a tag, or raise if it is not a version tag."""
    match = TAG.match(tag)
    if not match:
        raise ReleaseError(f"'{tag}' is not a version tag. Use v<major>.<minor>.<patch>, e.g. v0.1.0 or v0.2.0-rc.1.")
    return match["version"], match["suffix"] or "", match["major"] == "0"


def derive_tag(manifest: dict, suffix: str = "") -> str:
    """The tag that releases the manifest's version, e.g. ``v0.1.0`` or ``v0.1.0-rc.1``."""
    suffix = suffix.strip().removeprefix("-")
    if suffix and not SUFFIX.match(suffix):
        raise ReleaseError(f"'{suffix}' is not a valid suffix. Use letters, digits and dots, e.g. rc.1.")
    tag = f"v{manifest['world_version']}" + (f"-{suffix}" if suffix else "")
    parse_tag(tag)  # also proves that world_version itself is a plain major.minor.patch
    return tag


def read_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"Cannot read {path}: {exc}") from exc


def changelog_section(changelog: str, version: str) -> str | None:
    """The text under ``## [version]`` up to the next second-level heading, or ``None`` if there is none."""
    heading = re.compile(rf"^## \[{re.escape(version)}\].*$", re.MULTILINE)
    start = heading.search(changelog)
    if not start:
        return None
    following = re.search(r"^## ", changelog[start.end():], re.MULTILINE)
    end = start.end() + following.start() if following else len(changelog)
    return changelog[start.end():end].strip()


def prepare_release(tag: str, manifest: dict, changelog: str) -> Release:
    version, suffix, pre_one_point_zero = parse_tag(tag)
    if version != manifest["world_version"]:
        raise ReleaseError(
            f"Tag {tag} does not match world_version {manifest['world_version']} in archipelago.json. "
            f"Either tag v{manifest['world_version']} or update the manifest."
        )
    section = changelog_section(changelog, version)
    if not section:
        raise ReleaseError(
            f"CHANGELOG.md has no (or an empty) '## [{version}]' section. Write the release notes first."
        )

    prerelease = pre_one_point_zero or bool(suffix)
    parts = [section]
    if prerelease:
        parts.append(PRERELEASE_NOTICE)
    parts.append(
        "**Install:** download `medabots_rpg.apworld` and double-click it (or put it in the `custom_worlds` folder of "
        f"your Archipelago installation). Requires Archipelago {manifest['minimum_ap_version']} or later. "
        "`SHA256SUMS.txt` lists the checksum of the file."
    )
    return Release(version, prerelease, "\n\n".join(parts) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--tag", help="check this tag and prepare its release notes, e.g. v0.1.0")
    mode.add_argument("--derive-tag", action="store_true", help="print the tag that releases the manifest's version")
    parser.add_argument("--suffix", default="", help="with --derive-tag: a pre-release suffix such as rc.1")
    parser.add_argument("--manifest", type=Path, default=ROOT / "worlds/medabots_rpg/archipelago.json")
    parser.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md")
    parser.add_argument("--notes-out", type=Path, help="with --tag: where to write the release notes")
    args = parser.parse_args(argv)

    try:
        manifest = read_manifest(args.manifest)
        if args.derive_tag:
            print(f"tag={derive_tag(manifest, args.suffix)}")
            return 0
        release = prepare_release(args.tag, manifest, args.changelog.read_text(encoding="utf-8"))
    except (ReleaseError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.notes_out:
        args.notes_out.write_text(release.notes, encoding="utf-8")
    print(f"version={release.version}")
    print(f"prerelease={'true' if release.prerelease else 'false'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
