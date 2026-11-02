"""Shared test base. Tests run against the data shipped with the world, which is unverified, so they opt in."""
from test.bases import WorldTestBase

from ..constants import GAME_NAME


class MedabotsTestBase(WorldTestBase):
    game = GAME_NAME
    options = {"allow_unverified_build": True}
