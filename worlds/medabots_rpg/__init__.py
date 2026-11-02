"""Medabots RPG (Medabots: Metabee / Rokusho, Game Boy Advance) for Archipelago."""
from __future__ import annotations

import logging
import os
from collections import Counter
from typing import Any, ClassVar, TextIO

import settings
from BaseClasses import LocationProgressType, Tutorial
from Options import OptionError
from worlds.AutoWorld import WebWorld, World

from .client import MedabotsRPGClient  # noqa: F401  (unused, but importing it registers the BizHawk client)
from .constants import GAME_NAME, KIND_PART
from .data_loader import LocationDef, WorldData, get_world_data
from .items import MedabotsItem, PoolPlan, build_item_pool, item_classification, pouch_name_for_filler
from .items import item_name_groups as build_item_name_groups
from .locations import location_name_groups as build_location_name_groups
from .locations import progress_type, select_locations
from .options import OPTION_GROUPS, OPTION_PRESETS, MedabotsOptions
from .regions import create_regions
from .rom import MedabotsRPGProcedurePatch, write_patch
from .rules import part_gate_thresholds
from .version import world_version

REPOSITORY_URL = "https://github.com/NiklaskoDev/MedabotsRPG_APWorld"


class MedabotsRPGSettings(settings.Group):
    class RomFile(settings.UserFilePath):
        """File name of your English Medabots: Metabee or Rokusho ROM (Game Boy Advance, USA or Europe)"""

        description = "Medabots: Metabee / Rokusho (English) ROM File"
        # No md5s: all four supported versions are accepted and told apart by their header when patching.

    rom_file: RomFile = RomFile("Medabots - Metabee Version (USA).gba")


class MedabotsRPGWebWorld(WebWorld):
    setup_en = Tutorial(
        "Multiworld Setup Guide",
        "A guide to playing Medabots RPG with Archipelago.",
        "English",
        "setup_en.md",
        "setup/en",
        ["NiklaskoDev"],
    )

    tutorials = [setup_en]
    theme = "ocean"
    options_presets = OPTION_PRESETS
    option_groups = OPTION_GROUPS
    rich_text_options_doc = True
    bug_report_page = f"{REPOSITORY_URL}/issues"


class MedabotsRPGWorld(World):
    """
    Medabots: Metabee and Rokusho is a turn-based RPG in which a boy and his Medabot take on Robattles across
    Riverview, Medabot Island and Medaropolis. Collect medaparts and medals to build the strongest Medabot, and
    uncover the plot of the Rubberobo gang.
    """

    game = GAME_NAME
    web = MedabotsRPGWebWorld()
    topology_present = True
    required_client_version = (0, 6, 8)

    settings_key = "medabots_rpg_settings"
    settings: ClassVar[MedabotsRPGSettings]

    options_dataclass = MedabotsOptions
    options: MedabotsOptions

    data: ClassVar[WorldData] = get_world_data()
    item_name_to_id = {item.name: item.id for item in data.items}
    location_name_to_id = {location.name: location.id for location in data.locations}
    item_name_groups = build_item_name_groups(data)
    location_name_groups = build_location_name_groups(data)

    active_locations: list[LocationDef]
    pool: PoolPlan
    gates: dict[str, int]

    # --- generation -------------------------------------------------------------------------------------------------
    def generate_early(self) -> None:
        self.active_locations = select_locations(self.data, self.options)
        if not self.active_locations:
            raise OptionError(
                f"Medabots RPG ({self.player_name}): the selected options leave no locations to randomize. "
                "Turn at least one location category on."
            )
        self._enforce_verification_gate()

        excluded = sum(1 for loc in self.active_locations if progress_type(loc, self.options) is
                       LocationProgressType.EXCLUDED)
        self.pool = build_item_pool(self.data, self.options, len(self.active_locations), excluded, self.random)
        for note in self.pool.notes:
            logging.warning("Medabots RPG (%s): %s", self.player_name, note)

        per_area = Counter(loc.area for loc in self.active_locations)
        self.gates = part_gate_thresholds(self.data, self.options.battle_logic.current_key,
                                          self.pool.count(self.data, KIND_PART), per_area)

    def _enforce_verification_gate(self) -> None:
        """Refuse to build a seed from data that has not been checked against a real ROM (invariant G1)."""
        unverified = [loc for loc in self.active_locations if not loc.verified]
        if self.data.memory_map.verified and not unverified:
            return
        if not self.options.allow_unverified_build:
            raise OptionError(
                f"Medabots RPG ({self.player_name}): this version of the world has not been verified against a real "
                "ROM yet, so a seed generated now may not be playable. To generate anyway (for testing), set "
                f"'allow_unverified_build: true' in your YAML. Details: {REPOSITORY_URL}"
            )
        logging.warning(
            "Medabots RPG (%s): generating from unverified data (%d of %d locations unverified, memory map %s).",
            self.player_name, len(unverified), len(self.active_locations),
            "verified" if self.data.memory_map.verified else "unverified",
        )

    def create_regions(self) -> None:
        create_regions(self, self.active_locations, self.gates)

    def create_items(self) -> None:
        self.multiworld.itempool += [self.create_item(name) for name in self.pool.item_names]

    def create_item(self, name: str) -> MedabotsItem:
        item = self.data.item_by_name[name]
        return MedabotsItem(name, item_classification(item, self.options), item.id, self.player)

    def get_filler_item_name(self) -> str:
        return pouch_name_for_filler(self.data, self.random)

    # --- output -----------------------------------------------------------------------------------------------------
    def generate_output(self, output_directory: str) -> None:
        patch = MedabotsRPGProcedurePatch(player=self.player, player_name=self.player_name)
        write_patch(
            patch,
            data=self.data,
            seed_name=self.multiworld.seed_name,
            slot=self.player,
            player_name=self.player_name,
            allow_unverified=bool(self.options.allow_unverified_build),
            locations=self.active_locations,
        )
        base_name = self.multiworld.get_out_file_name_base(self.player)
        patch.write(os.path.join(output_directory, f"{base_name}{patch.patch_file_ending}"))

    def fill_slot_data(self) -> dict[str, Any]:
        return {
            "world_version": world_version(),
            "data_hash": self.data.content_hash,
            "seed_name": self.multiworld.seed_name,
            "goal": self.options.goal.current_key,
            "goal_medal_count": self.pool.goal_medal_count,
            "goal_part_count": self.pool.goal_part_count,
            "battle_logic": self.options.battle_logic.current_key,
            "area_part_gates": self.gates,
            "trap_strength": self.options.trap_strength.current_key,
            "receive_item_messages": self.options.receive_item_messages.current_key,
            "unverified_build": not self.data.is_verified,
        }

    def write_spoiler(self, spoiler_handle: TextIO) -> None:
        if not self.gates:
            return
        width = max(len(name) for name in self.gates)
        spoiler_handle.write(f"\nMedabots RPG ({self.player_name}) - medaparts needed to enter an area:\n")
        for area in self.data.areas:
            if area.name in self.gates:
                spoiler_handle.write(f"  {area.name:<{width}}  {self.gates[area.name]:>3}\n")
