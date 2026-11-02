"""BizHawk client: connects the running game to the multiworld server.

This module only does the plumbing (reading memory, talking to the server, showing messages). What to detect and what
to write is decided by ``effects.py``. Connecting to the server itself (``ws://`` and ``wss://``) is handled by
Archipelago's ``CommonClient``, which this client builds on.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import worlds._bizhawk as bizhawk
from NetUtils import ClientStatus
from Utils import async_start
from worlds._bizhawk.client import BizHawkClient

from .constants import GAME_NAME, GBA_ROM_DOMAIN
from .data_loader import get_world_data
from .effects import (
    ClientState,
    Received,
    Snapshot,
    collection_goal_reached,
    detect_checked_locations,
    plan_step,
    readable_tables,
    story_complete,
)
from .rom import ApIdentity, PatchError, identify_header

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext

logger = logging.getLogger("Client")

REPAIR_INTERVAL_SECONDS = 5.0
"""How often ownership of every received part and medal is re-asserted (this repairs loaded older saves)."""


class MedabotsRPGClient(BizHawkClient):
    game = GAME_NAME
    system = "GBA"
    patch_suffix = ".apmedabots"

    def __init__(self) -> None:
        self.data = get_world_data()
        self._reset()

    def _reset(self) -> None:
        self.identity: ApIdentity | None = None
        self.state = ClientState()
        self.counter_loaded = False
        self.blocked: str | None = None
        self.goal_sent = False
        self.last_repair = 0.0
        self._told: set[str] = set()

    def _tell_once(self, key: str, message: str) -> None:
        """Log a message a single time per ROM so the log stays readable."""
        if key not in self._told:
            self._told.add(key)
            logger.info(message)

    # ------------------------------------------------------------------------------------------------------------------
    # ROM validation and authentication
    # ------------------------------------------------------------------------------------------------------------------
    async def validate_rom(self, ctx: BizHawkClientContext) -> bool:
        info, memory_map = self.data.rom, self.data.memory_map
        try:
            header, block = await bizhawk.read(ctx.bizhawk_ctx, [
                (info.header_offset, info.header_length, GBA_ROM_DOMAIN),
                (memory_map.ap_block_offset, memory_map.ap_block_size, GBA_ROM_DOMAIN),
            ])
        except bizhawk.RequestFailedError:
            return False

        try:
            identify_header(header, self.data)
        except PatchError:
            return False  # some other game; stay quiet so other clients can claim it

        identity = ApIdentity.unpack(block)
        if identity is None:
            self._tell_once("unpatched", "This is an unpatched Medabots ROM. Open your .apmedabots patch file with the "
                                         "Archipelago Launcher to create the patched ROM, then load that one.")
            return False

        self._reset()
        self.identity = identity
        ctx.game = self.game
        ctx.items_handling = 0b111  # receive everything, including items from this slot and the starting inventory
        ctx.want_slot_data = True
        if identity.unverified or not memory_map.verified:
            logger.warning("This ROM was patched from an unverified build of the Medabots RPG world. Tracking may be "
                           "incomplete until its memory map has been verified (see docs/CALIBRATION.md).")
        return True

    async def set_auth(self, ctx: BizHawkClientContext) -> None:
        if self.identity is not None:
            ctx.auth = self.identity.player_name

    # ------------------------------------------------------------------------------------------------------------------
    # Server packages
    # ------------------------------------------------------------------------------------------------------------------
    def on_package(self, ctx: BizHawkClientContext, cmd: str, args: dict) -> None:
        if self.identity is None:
            return
        if cmd == "RoomInfo" and ApIdentity.digest_seed(args["seed_name"]) != self.identity.seed_digest:
            self._block("This ROM was patched for a different multiworld than the one on this server. Connect to the "
                        "right server, or patch your ROM again with the matching .apmedabots file.")
        elif cmd == "Connected":
            self._check_slot_data(ctx, args.get("slot_data") or {})
            if self.blocked is None:
                ctx.slot_data = args.get("slot_data")
                self.counter_loaded = False
                async_start(ctx.send_msgs([{"cmd": "Get", "keys": [self._counter_key(ctx)]}]))
        elif cmd == "Retrieved" and self._counter_key(ctx) in args.get("keys", {}):
            stored = args["keys"][self._counter_key(ctx)]
            self.state.applied_index = int(stored or 0)
            self.counter_loaded = True

    def _check_slot_data(self, ctx: BizHawkClientContext, slot_data: dict) -> None:
        if slot_data.get("data_hash") != self.data.content_hash:
            self._block(f"This seed was generated with a different version of the Medabots RPG world "
                        f"({slot_data.get('world_version', 'unknown')}) than the one installed. Install the matching "
                        "version.")

    def _block(self, reason: str) -> None:
        self.blocked = reason
        logger.error("Medabots RPG client stopped: %s", reason)

    @staticmethod
    def _counter_key(ctx: BizHawkClientContext) -> str:
        return f"medabots_rpg_{ctx.team}_{ctx.slot}_applied"

    # ------------------------------------------------------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------------------------------------------------------
    async def game_watcher(self, ctx: BizHawkClientContext) -> None:
        if self.blocked or ctx.server is None or ctx.slot is None or ctx.slot_data is None:
            return
        try:
            snapshot = await self._read_snapshot(ctx)
            await self._report_locations(ctx, snapshot)
            await self._report_goal(ctx, snapshot)
            if self.counter_loaded:
                await self._deliver(ctx, snapshot)
        except bizhawk.RequestFailedError:
            return  # BizHawk did not answer (for example it is loading); the main loop reconnects on its own

    async def _read_snapshot(self, ctx: BizHawkClientContext) -> Snapshot:
        memory_map = self.data.memory_map
        tables = readable_tables(memory_map)
        chunks = await bizhawk.read(ctx.bizhawk_ctx, [(ref.address, ref.size, memory_map.domain) for _, ref in tables])
        return Snapshot(memory_map, {path: chunk for (path, _), chunk in zip(tables, chunks, strict=True)})

    async def _report_locations(self, ctx: BizHawkClientContext, snapshot: Snapshot) -> None:
        # The server only learns about a check from us, so also skip what we already sent while it catches up.
        found = detect_checked_locations(self.data, snapshot, ctx.missing_locations) - ctx.locations_checked
        if found:
            ctx.locations_checked |= found
            await ctx.send_msgs([{"cmd": "LocationChecks", "locations": sorted(found)}])

    async def _report_goal(self, ctx: BizHawkClientContext, snapshot: Snapshot) -> None:
        if self.goal_sent or ctx.finished_game:
            return
        slot_data = ctx.slot_data or {}
        goal = slot_data.get("goal", "story_complete")
        names = [ctx.item_names.lookup_in_game(item.item, self.game) for item in ctx.items_received]
        reached = (story_complete(self.data, snapshot) if goal == "story_complete" else
                   collection_goal_reached(self.data, names, goal, slot_data.get("goal_medal_count", 0),
                                           slot_data.get("goal_part_count", 0)))
        if reached:
            self.goal_sent = True
            await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])

    async def _deliver(self, ctx: BizHawkClientContext, snapshot: Snapshot) -> None:
        slot_data = ctx.slot_data or {}
        received = [
            Received(
                name=ctx.item_names.lookup_in_game(net.item, self.game),
                sender=ctx.player_names.get(net.player, f"Player {net.player}"),
                advancement=bool(net.flags & 0b001),
            )
            for net in ctx.items_received
        ]
        now = time.monotonic()
        repair = now - self.last_repair >= REPAIR_INTERVAL_SECONDS
        plan = plan_step(
            self.data, snapshot, received, self.state,
            own_name=ctx.player_names.get(ctx.slot, ""),
            strength=slot_data.get("trap_strength", "normal"),
            message_mode=slot_data.get("receive_item_messages", "all"),
            now=now, repair=repair,
        )
        if plan.writes:
            domain = self.data.memory_map.domain
            applied = await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(address, list(data), domain) for address, data in plan.writes],
                [(address, list(data), domain) for address, data in plan.guards],
            )
            if not applied:
                return  # the game changed under us; plan again from a fresh snapshot next tick
        if repair:
            self.last_repair = now

        previous = self.state.applied_index
        self.state = plan.state
        for text in plan.announcements:
            await bizhawk.display_message(ctx.bizhawk_ctx, text)
        if self.state.applied_index != previous:
            await ctx.send_msgs([{
                "cmd": "Set", "key": self._counter_key(ctx), "default": 0, "want_reply": False,
                "operations": [{"operation": "replace", "value": self.state.applied_index}],
            }])
