"""Names and small constants shared by every module of the world."""

GAME_NAME = "Medabots RPG"
"""The game name Archipelago and every player YAML refer to. Changing it breaks existing YAML files."""

PART_SLOTS = ("Head", "Right Arm", "Left Arm", "Legs")
"""Medapart slots, in the order the game stores them (head, right arm, left arm, legs)."""

PART_SLOT_GROUPS = ("Head Parts", "Right Arm Parts", "Left Arm Parts", "Leg Parts")
"""Item group for every slot in PART_SLOTS."""

# Item groups
GROUP_PARTS = "Medaparts"
GROUP_USABLE_PARTS = "Usable Medaparts"
"""Medaparts of the gender of Ikki's first Tinpet, the only ones he can fit at first. Battle Logic counts these."""
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
STATUS_ABSENT = "absent"
"""Shown by calibration not to exist in the game. The row stays so its ID is never reused, but it is never selected."""

# Event flags (see memory_map.json): flag n lives in byte n >> 1 of the game_flags table, as one nibble per flag.
EVENT_FLAG_BITS = (7, 3)
"""Bit of the "done" flag for an even and an odd event number."""
EVENT_VALUE_SHIFTS = (4, 0)
"""Shift of the 3-bit event value for an even and an odd event number."""
MEDAL_RECORD_SIZE = 0x40
MEDAL_TABLE_ENTRY_SIZE = 16

GENDERS = ("male", "female")
"""A Tinpet takes only parts of its own gender, and every part of a Medabot model has that model's gender."""

REQUIRED_STATES = ("safe_to_deliver", "in_battle", "in_field")
"""State flags a verified memory map must define. ``in_field`` is what keeps the client from reading check and goal
flags out of memory the game has wiped (choosing New Game fills it with 0xFF), so a map without it is never complete."""
WIPED_FLAG_BYTE = 0xFF
"""What New Game fills the game's RAM with. A flag table made only of these bytes is not a game in progress."""

# Version-specific constants
GBA_ROM_DOMAIN = "ROM"
