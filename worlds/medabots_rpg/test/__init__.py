"""Shared test base. Tests run against the data shipped with the world with default options."""
from test.bases import WorldTestBase

from ..constants import GAME_NAME


class MedabotsTestBase(WorldTestBase):
    game = GAME_NAME
    options = {}
