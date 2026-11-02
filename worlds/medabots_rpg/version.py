"""The world's version, read from ``archipelago.json`` so there is exactly one place to bump it."""
from __future__ import annotations

import json
import pkgutil
from functools import lru_cache


@lru_cache(maxsize=1)
def world_version() -> str:
    raw = pkgutil.get_data(__package__, "archipelago.json")
    assert raw is not None, "archipelago.json is missing from the world"
    return json.loads(raw)["world_version"]
