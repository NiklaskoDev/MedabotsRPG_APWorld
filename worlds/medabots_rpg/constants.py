"""Names and small constants shared by every module of the world."""

GAME_NAME = "Medabots RPG"
"""The game name Archipelago and every player YAML refer to. Changing it breaks existing YAML files."""

PART_SLOTS = ("Head", "Right Arm", "Left Arm", "Legs")
"""Medapart slots, in the order the game stores them (head, right arm, left arm, legs)."""

PART_SLOT_GROUPS = ("Head Parts", "Right Arm Parts", "Left Arm Parts", "Leg Parts")
"""Item group for every slot in PART_SLOTS."""

# Item groups
GROUP_PARTS = "Medaparts"
GROUP_MEDALS = "Medals"
GROUP_MONEY = "Money Pouches"
GROUP_TRAPS = "Traps"

# Item kinds as used in ItemDef.kind
KIND_PART = "part"
KIND_MEDAL = "medal"
KIND_CONSUMABLE = "consumable"
KIND_TRAP = "trap"

# Location verification states as used in LocationDef.status
STATUS_CANDIDATE = "candidate"
STATUS_VERIFIED = "verified"

# Version-specific constants
GBA_ROM_DOMAIN = "ROM"
