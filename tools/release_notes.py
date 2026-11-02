#!/usr/bin/env python3
"""Release helper for the Release workflow: validates a version tag and prepares the GitHub release notes.

    python tools/release_notes.py --tag v0.1.0 --notes-out notes.md

It checks that the tag is ``v<world_version>`` (optionally with a ``-suffix`` such as ``-rc.1``), takes the matching
section from CHANGELOG.md (a missing section is an error, so a release can never go out without notes), and prints
``prerelease=true|false`` for the workflow. Versions below 1.0.0 and tags with a suffix are pre-releases.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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
    parser.add_argument("--tag", required=True, help="the git tag being released, e.g. v0.1.0")
    parser.add_argument("--manifest", type=Path, default=ROOT / "worlds/medabots_rpg/archipelago.json")
    parser.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md")
    parser.add_argument("--notes-out", type=Path, help="where to write the release notes")
    args = parser.parse_args(argv)

    try:
        release = prepare_release(args.tag, read_manifest(args.manifest), args.changelog.read_text(encoding="utf-8"))
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
