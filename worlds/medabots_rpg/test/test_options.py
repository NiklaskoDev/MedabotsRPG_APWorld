"""Everything a player sees on the options page must be complete and valid."""
import dataclasses
import re
import unittest

from Options import Option, PerGameCommonOptions

from .. import MedabotsRPGWorld
from ..options import OPTION_GROUPS, OPTION_PRESETS, MedabotsOptions, TrapWeights
from .support import make_options

OWN_OPTIONS = {name: cls for name, cls in MedabotsOptions.type_hints.items()
               if name not in {f.name for f in dataclasses.fields(PerGameCommonOptions)}}


class TestOptionDefinitions(unittest.TestCase):
    def test_every_option_has_a_display_name_and_documentation(self):
        for name, option in OWN_OPTIONS.items():
            self.assertTrue(option.display_name, name)
            doc = (option.__doc__ or "").strip()
            self.assertGreater(len(doc), 20, f"{name} needs a description")
            self.assertTrue(doc.split("\n")[0].rstrip().endswith("."), f"{name}: first line should be a sentence")

    def test_display_names_are_title_case_and_unique(self):
        names = [option.display_name for option in OWN_OPTIONS.values()]
        self.assertEqual(len(names), len(set(names)))
        for name in names:
            self.assertRegex(name, r"^[A-Z0-9]", name)
            self.assertNotIn("_", name)

    def test_every_option_is_in_exactly_one_group(self):
        # Archipelago appends its own "Item & Location Options" group, so only this world's options are compared.
        grouped = [option for group in OPTION_GROUPS for option in group.options if option in OWN_OPTIONS.values()]
        self.assertEqual(len(grouped), len(set(grouped)))
        self.assertEqual(set(grouped), set(OWN_OPTIONS.values()))

    def test_groups_have_distinct_names(self):
        names = [group.name for group in OPTION_GROUPS]
        self.assertEqual(len(names), len(set(names)))

    def test_docstrings_use_valid_restructuredtext_lists(self):
        """Lists must be preceded by a blank line, otherwise the WebHost renders them as running text."""
        for name, option in OWN_OPTIONS.items():
            lines = (option.__doc__ or "").expandtabs().splitlines()
            for previous, line in zip(lines, lines[1:], strict=False):
                if re.match(r"\s*\* ", line) and previous.strip() and not re.match(r"\s*\* ", previous):
                    self.fail(f"{name}: list item without a blank line before it: {line!r}")

    def test_defaults_are_valid_values(self):
        options = make_options()
        self.assertEqual(options.goal.current_key, "story_complete")
        self.assertEqual(options.battle_logic.current_key, "relaxed")
        self.assertFalse(options.allow_unverified_build)

    def test_trap_weight_keys_are_real_trap_items(self):
        trap_names = {name for name in MedabotsRPGWorld.item_name_to_id if name.endswith("Trap")}
        self.assertEqual(set(TrapWeights.valid_keys), trap_names)
        self.assertEqual(set(TrapWeights.default), trap_names)


class TestPresets(unittest.TestCase):
    def test_presets_only_use_real_options_and_valid_values(self):
        self.assertGreaterEqual(len(OPTION_PRESETS), 3)
        for preset_name, values in OPTION_PRESETS.items():
            for option_name, value in values.items():
                self.assertIn(option_name, OWN_OPTIONS, f"{preset_name}: unknown option {option_name}")
                option: type[Option] = OWN_OPTIONS[option_name]
                option.from_any(value)  # raises for an invalid value

    def test_presets_survive_being_applied(self):
        for values in OPTION_PRESETS.values():
            make_options(**values)

    def test_presets_are_registered_on_the_webhost_page(self):
        self.assertIs(MedabotsRPGWorld.web.options_presets, OPTION_PRESETS)
        self.assertIs(MedabotsRPGWorld.web.option_groups, OPTION_GROUPS)
