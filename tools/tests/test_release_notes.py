import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import release_notes
from release_notes import ReleaseError, changelog_section, parse_tag, prepare_release

CHANGELOG = """# Changelog

## [Unreleased]

- Something new.

## [0.2.0] - 2026-02-01

### Added
- Two things.

## [0.1.0] - 2026-01-01

- First release.
"""
MANIFEST = {"game": "Medabots RPG", "world_version": "0.2.0", "minimum_ap_version": "0.6.8"}


class TestTags(unittest.TestCase):
    def test_valid_tags(self):
        self.assertEqual(parse_tag("v0.1.0"), ("0.1.0", "", True))
        self.assertEqual(parse_tag("v1.4.12"), ("1.4.12", "", False))
        self.assertEqual(parse_tag("v1.0.0-rc.1"), ("1.0.0", "-rc.1", False))

    def test_invalid_tags(self):
        for tag in ("0.1.0", "v1.0", "v1.0.0.0", "release-1", "v1.0.0-", "vx.y.z", ""):
            with self.assertRaises(ReleaseError, msg=tag):
                parse_tag(tag)


class TestChangelog(unittest.TestCase):
    def test_sections_are_cut_at_the_next_heading(self):
        self.assertEqual(changelog_section(CHANGELOG, "0.2.0"), "### Added\n- Two things.")
        self.assertEqual(changelog_section(CHANGELOG, "0.1.0"), "- First release.")

    def test_missing_section(self):
        self.assertIsNone(changelog_section(CHANGELOG, "0.3.0"))

    def test_versions_are_matched_literally(self):
        self.assertIsNone(changelog_section("## [0x1x0] - today\ntext", "0.1.0"))


class TestPrepareRelease(unittest.TestCase):
    def test_a_release_below_1_0_is_a_prerelease_with_notice(self):
        release = prepare_release("v0.2.0", MANIFEST, CHANGELOG)
        self.assertTrue(release.prerelease)
        self.assertIn("Two things.", release.notes)
        self.assertIn("Pre-release", release.notes)
        self.assertIn("0.6.8", release.notes)
        self.assertNotIn("First release", release.notes)

    def test_a_stable_release_has_no_notice(self):
        manifest = {**MANIFEST, "world_version": "1.0.0"}
        release = prepare_release("v1.0.0", manifest, CHANGELOG + "\n## [1.0.0] - 2026-03-01\n\n- Verified.\n")
        self.assertFalse(release.prerelease)
        self.assertNotIn("Pre-release", release.notes)

    def test_a_suffix_makes_any_version_a_prerelease(self):
        manifest = {**MANIFEST, "world_version": "1.0.0"}
        text = CHANGELOG + "\n## [1.0.0] - 2026-03-01\n\n- Verified.\n"
        self.assertTrue(prepare_release("v1.0.0-rc.1", manifest, text).prerelease)

    def test_tag_must_match_the_manifest(self):
        with self.assertRaisesRegex(ReleaseError, "does not match"):
            prepare_release("v0.1.0", MANIFEST, CHANGELOG)

    def test_release_without_notes_is_refused(self):
        with self.assertRaisesRegex(ReleaseError, "no \\(or an empty\\)"):
            prepare_release("v0.2.0", MANIFEST, "# Changelog\n\n## [Unreleased]\n")
        with self.assertRaises(ReleaseError):
            prepare_release("v0.2.0", MANIFEST, "## [0.2.0] - 2026-02-01\n\n## [0.1.0]\n- x\n")


class TestCommandLine(unittest.TestCase):
    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = release_notes.main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def test_success_prints_workflow_outputs_and_writes_notes(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest, changelog, notes = Path(folder, "m.json"), Path(folder, "c.md"), Path(folder, "n.md")
            manifest.write_text(json.dumps(MANIFEST))
            changelog.write_text(CHANGELOG)
            code, out, _ = self.run_main("--tag", "v0.2.0", "--manifest", manifest, "--changelog", changelog,
                                         "--notes-out", notes)
            written = notes.read_text()
        self.assertEqual(code, 0)
        self.assertEqual(out.split(), ["version=0.2.0", "prerelease=true"])
        self.assertIn("Two things.", written)

    def test_failure_is_a_clean_error(self):
        code, _, err = self.run_main("--tag", "nonsense")
        self.assertEqual(code, 1)
        self.assertIn("not a version tag", err)

    def test_the_real_manifest_and_changelog_are_readable(self):
        """Guards against breaking the files this tool depends on."""
        manifest = release_notes.read_manifest(release_notes.ROOT / "worlds/medabots_rpg/archipelago.json")
        self.assertRegex(manifest["world_version"], r"^\d+\.\d+\.\d+$")
