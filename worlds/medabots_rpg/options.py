"""YAML options and WebHost presets.

Every docstring below is shown to players, both as a comment in the generated YAML template and on the WebHost options
page (rendered as reStructuredText), so they are written as short, complete sentences.
"""
from __future__ import annotations

from dataclasses import dataclass

from Options import (
    Choice,
    DefaultOnToggle,
    OptionCounter,
    OptionGroup,
    PerGameCommonOptions,
    Range,
    Toggle,
)

from .constants import KIND_TRAP
from .data_loader import get_world_data

_TRAP_NAMES = tuple(item.name for item in get_world_data().items if item.kind == KIND_TRAP)


# ---------------------------------------------------------------------------------------------------------------------
# Goal & Victory
# ---------------------------------------------------------------------------------------------------------------------
class Goal(Choice):
    """What you have to do to finish the game.

    * **Story Complete:** finish the story by completing the last area.
    * **Collect Medals:** receive the number of medals set by *Goal: Medals to Collect*.
    * **Collect Medaparts:** receive the number of medaparts set by *Goal: Medaparts to Collect*.
    """

    display_name = "Goal"
    option_story_complete = 0
    option_collect_medals = 1
    option_collect_medaparts = 2
    default = option_story_complete


class GoalMedalCount(Range):
    """How many different medals you must receive when the goal is *Collect Medals*.

    The value is lowered automatically if there are not enough locations to hold that many medals.
    """

    display_name = "Goal: Medals to Collect"
    range_start = 1
    range_end = 28
    default = 10


class GoalPartCount(Range):
    """How many different medaparts you must receive when the goal is *Collect Medaparts*.

    The value is lowered automatically if there are not enough locations to hold that many medaparts.
    """

    display_name = "Goal: Medaparts to Collect"
    range_start = 1
    range_end = 480
    default = 40


# ---------------------------------------------------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------------------------------------------------
class ShuffleMedalPickups(DefaultOnToggle):
    """Medals you pick up in medal rooms and receive from the story become checks."""

    display_name = "Shuffle Medal Pickups"


class ShuffleChests(DefaultOnToggle):
    """Chests, lockers and items lying around in the world become checks."""

    display_name = "Shuffle Chests and Pickups"


class ShuffleGifts(DefaultOnToggle):
    """Items that characters hand to you become checks."""

    display_name = "Shuffle Gifts From Characters"


class ShuffleBossRewards(DefaultOnToggle):
    """Winning story and boss Robattles becomes a check."""

    display_name = "Shuffle Boss Rewards"


class ShuffleMinigamePrizes(Toggle):
    """Prizes from the arcade and other mini-games become checks."""

    display_name = "Shuffle Mini-Game Prizes"


class Shopsanity(Toggle):
    """Buying something in a shop becomes a check.

    Not available yet: the game keeps no record of purchases, so no shop can be detected as a check and this option
    currently adds no locations.
    """

    display_name = "Shop Purchases"


class TrainerRobattles(Toggle):
    """Winning Robattles against ordinary trainers becomes a check."""

    display_name = "Trainer Robattles"


class IncludeMissableLocations(Toggle):
    """Allow important items on locations that can be missed for good.

    When this is off, such locations only ever hold filler, so nothing you need can be lost.
    """

    display_name = "Include Missable Locations"


# ---------------------------------------------------------------------------------------------------------------------
# Item pool
# ---------------------------------------------------------------------------------------------------------------------
class PartWeight(Range):
    """How many of the items in the pool are medaparts, relative to the other two weights."""

    display_name = "Medapart Weight"
    range_start = 0
    range_end = 100
    default = 55


class MedalWeight(Range):
    """How many of the items in the pool are medals, relative to the other two weights."""

    display_name = "Medal Weight"
    range_start = 0
    range_end = 100
    default = 25


class MoneyWeight(Range):
    """How many of the items in the pool are money pouches, relative to the other two weights.

    Money pouches are the filler of this game and are also what traps replace.
    """

    display_name = "Money Pouch Weight"
    range_start = 0
    range_end = 100
    default = 20


class IncludeVersionExclusives(Toggle):
    """Allow medaparts and medals that only exist in the other game version (Metabee or Rokusho).

    They cannot be obtained in a normal playthrough of your version, but Archipelago can give them to you.
    """

    display_name = "Include Version-Exclusive Items"


class BattleLogic(Choice):
    """How strong your Medabot is expected to be when you enter a new area.

    * **Off:** areas never require any medaparts.
    * **Relaxed:** later areas require a small share of all medaparts.
    * **Standard:** later areas require a larger share of all medaparts.
    """

    display_name = "Battle Logic"
    option_off = 0
    option_relaxed = 1
    option_standard = 2
    default = option_relaxed


# ---------------------------------------------------------------------------------------------------------------------
# Traps
# ---------------------------------------------------------------------------------------------------------------------
class TrapPercentage(Range):
    """What share of the filler (money pouches) is replaced by traps.

    Traps are always temporary and never take away parts or medals.
    """

    display_name = "Trap Percentage"
    range_start = 0
    range_end = 100
    default = 15


class TrapWeights(OptionCounter):
    """How likely each kind of trap is, relative to the others. Set a weight to 0 to disable that trap."""

    display_name = "Trap Weights"
    min = 0
    valid_keys = frozenset(_TRAP_NAMES)
    default = {"Money Drain Trap": 4, "Rusty Armor Trap": 3, "Medal Nap Trap": 2, "Ambush Trap": 1}


class TrapStrength(Choice):
    """How harsh traps are.

    * **Mild:** small effects that wear off quickly.
    * **Normal:** the intended difficulty.
    * **Harsh:** large effects that last a full battle.
    """

    display_name = "Trap Strength"
    option_mild = 0
    option_normal = 1
    option_harsh = 2
    default = option_normal


# ---------------------------------------------------------------------------------------------------------------------
# Quality of life
# ---------------------------------------------------------------------------------------------------------------------
class ReceiveItemMessages(Choice):
    """Which received items are announced on screen in BizHawk.

    * **All:** every item you receive.
    * **Progression Only:** only items that other players or the logic are waiting for.
    * **None:** no messages.
    """

    display_name = "Received Item Messages"
    option_all = 0
    option_progression_only = 1
    option_none = 2
    default = option_all


# ---------------------------------------------------------------------------------------------------------------------
# Advanced
# ---------------------------------------------------------------------------------------------------------------------
class AllowUnverifiedBuild(Toggle):
    """Generate even though this version of the world has not been verified against a real ROM.

    Until it is, memory addresses and check locations are educated guesses, so a generated game may not be playable.
    Leave this off unless you are testing the world.
    """

    display_name = "Allow Unverified Build"


@dataclass
class MedabotsOptions(PerGameCommonOptions):
    goal: Goal
    goal_medal_count: GoalMedalCount
    goal_part_count: GoalPartCount
    shuffle_medal_pickups: ShuffleMedalPickups
    shuffle_chests_and_pickups: ShuffleChests
    shuffle_npc_gifts: ShuffleGifts
    shuffle_boss_rewards: ShuffleBossRewards
    shuffle_minigame_prizes: ShuffleMinigamePrizes
    shopsanity: Shopsanity
    trainer_robattles: TrainerRobattles
    include_missable_locations: IncludeMissableLocations
    part_weight: PartWeight
    medal_weight: MedalWeight
    money_weight: MoneyWeight
    include_version_exclusives: IncludeVersionExclusives
    battle_logic: BattleLogic
    trap_percentage: TrapPercentage
    trap_weights: TrapWeights
    trap_strength: TrapStrength
    receive_item_messages: ReceiveItemMessages
    allow_unverified_build: AllowUnverifiedBuild


OPTION_GROUPS = [
    OptionGroup("Goal & Victory", [Goal, GoalMedalCount, GoalPartCount]),
    OptionGroup("Locations", [
        ShuffleMedalPickups, ShuffleChests, ShuffleGifts, ShuffleBossRewards, ShuffleMinigamePrizes, Shopsanity,
        TrainerRobattles, IncludeMissableLocations,
    ]),
    OptionGroup("Item Pool", [PartWeight, MedalWeight, MoneyWeight, IncludeVersionExclusives, BattleLogic]),
    OptionGroup("Traps", [TrapPercentage, TrapWeights, TrapStrength]),
    OptionGroup("Quality of Life", [ReceiveItemMessages]),
    OptionGroup("Advanced", [AllowUnverifiedBuild], start_collapsed=True),
]

OPTION_PRESETS: dict[str, dict[str, object]] = {
    "Casual": {
        "goal": "story_complete",
        "battle_logic": "relaxed",
        "trap_percentage": 0,
        "include_version_exclusives": False,
        "shopsanity": False,
        "trainer_robattles": False,
    },
    "Standard": {
        "goal": "story_complete",
        "battle_logic": "standard",
        "trap_percentage": 15,
        "trap_strength": "normal",
        "shopsanity": False,
        "trainer_robattles": False,
    },
    "Chaos": {
        "goal": "collect_medaparts",
        "goal_part_count": 80,
        "battle_logic": "standard",
        "trap_percentage": 40,
        "trap_strength": "harsh",
        "include_version_exclusives": True,
        "shopsanity": True,
        "trainer_robattles": True,
        "shuffle_minigame_prizes": True,
        "include_missable_locations": True,
    },
}
