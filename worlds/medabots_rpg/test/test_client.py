"""The BizHawk client, driven against a fake BizHawk and a fake server connection."""
import asyncio
import types
import unittest
from unittest import mock

import worlds._bizhawk as bizhawk
from NetUtils import ClientStatus, NetworkItem

from ..client import MedabotsRPGClient
from ..constants import GAME_NAME
from ..rom import ApIdentity
from .support import (
    FLAG_BIT_SQUIDGUTS,
    FLAG_BIT_STORY_COMPLETE,
    FLAGS,
    MEDIUM_POUCH,
    MONEY,
    SMALL_POUCH,
    SYSTEM_BUS,
    FakeMemory,
    build_rom,
    verified_data,
)

DATA = verified_data()
BLOCK, BLOCK_SIZE = DATA.memory_map.ap_block_offset, DATA.memory_map.ap_block_size
SEED = "seed-abc"
ID_TO_NAME = {item.id: item.name for item in DATA.items}
NAME_TO_ID = {name: code for code, name in ID_TO_NAME.items()}


def patched_rom(header_id="MEDABOTSMTBVA8BEE9", seed=SEED, data_hash=DATA.content_hash, unverified=False):
    identity = ApIdentity(1, ApIdentity.digest_seed(seed), ApIdentity.digest_data(data_hash), unverified, "Ash")
    rom = bytearray(build_rom(header_id))
    rom[BLOCK:BLOCK + BLOCK_SIZE] = identity.pack(BLOCK_SIZE)
    return bytes(rom)


class FakeBizHawk:
    """In-memory replacement for the functions of ``worlds._bizhawk`` that the client uses."""

    def __init__(self, memory: FakeMemory):
        self.memory = memory
        self.messages: list[str] = []
        self.reads = 0
        self.raise_on_read = False

    async def read(self, ctx, read_list):
        self.reads += 1
        if self.raise_on_read:
            raise bizhawk.RequestFailedError("BizHawk is busy")
        try:
            return [self.memory.read(address, size, domain) for address, size, domain in read_list]
        except IndexError as exc:
            raise bizhawk.RequestFailedError(str(exc)) from exc

    async def guarded_write(self, ctx, write_list, guard_list):
        if self.memory.fail_next_guard:
            self.memory.fail_next_guard = False
            return False
        if any(self.memory.read(address, len(expected), domain) != bytes(expected)
               for address, expected, domain in guard_list):
            return False
        for address, data, domain in write_list:
            self.memory.write(address, bytes(data), domain)
        return True

    async def display_message(self, ctx, message):
        self.messages.append(message)


def make_context(*, slot_data=None, received=(), missing=()):
    sent: list[dict] = []

    async def send_msgs(messages):
        sent.extend(messages)

    ctx = types.SimpleNamespace(
        bizhawk_ctx=object(), server=object(), slot=1, team=0, auth=None, game=None, items_handling=None,
        want_slot_data=False, finished_game=False, locations_checked=set(), missing_locations=set(missing),
        player_names={0: "Archipelago", 1: "Ash", 2: "Misty"}, slot_data=slot_data,
        items_received=[NetworkItem(NAME_TO_ID[name], 0, sender, flags) for name, sender, flags in received],
        item_names=types.SimpleNamespace(lookup_in_game=lambda code, game=None: ID_TO_NAME[code]),
        send_msgs=send_msgs, sent=sent,
    )
    return ctx


SLOT_DATA = {"goal": "story_complete", "trap_strength": "normal", "receive_item_messages": "all",
             "data_hash": DATA.content_hash, "world_version": "0.1.0", "seed_name": SEED}


class ClientTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.memory = FakeMemory(patched_rom())
        self.bh = FakeBizHawk(self.memory)
        for name in ("read", "guarded_write", "display_message"):
            patcher = mock.patch.object(bizhawk, name, getattr(self.bh, name))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = MedabotsRPGClient()
        self.client.data = DATA

    async def connect(self, **kwargs):
        """A context for a client that has validated its ROM and is connected to the server."""
        self.assertTrue(await self.client.validate_rom(make_context()))
        ctx = make_context(slot_data=dict(SLOT_DATA), **kwargs)
        self.client.counter_loaded = True
        return ctx


class TestValidateRom(ClientTestCase):
    async def test_a_patched_rom_is_claimed_and_configured(self):
        ctx = make_context()
        self.assertTrue(await self.client.validate_rom(ctx))
        self.assertEqual((ctx.game, ctx.items_handling, ctx.want_slot_data), (GAME_NAME, 0b111, True))

    async def test_all_four_versions_are_claimed(self):
        for version in DATA.rom.versions:
            self.memory.rom[:] = patched_rom(version.header_id)
            self.assertTrue(await self.client.validate_rom(make_context()), version.id)

    async def test_the_medal_table_is_read_from_the_rom_version_in_use(self):
        for version in DATA.rom.versions:
            rom = bytearray(patched_rom(version.header_id))
            rom[version.medal_table_offset:version.medal_table_offset + 2] = bytes([0xAB, len(version.id)])
            self.memory.rom[:] = rom
            self.assertTrue(await self.client.validate_rom(make_context()))
            self.assertEqual(len(self.client.medal_table), 30 * 16)
            self.assertEqual(self.client.medal_table[:2], bytes([0xAB, len(version.id)]), version.id)

    async def test_an_unpatched_rom_is_refused_with_instructions(self):
        self.memory.rom[:] = build_rom()
        with self.assertLogs("Client", "INFO") as logs:
            self.assertFalse(await self.client.validate_rom(make_context()))
            self.assertFalse(await self.client.validate_rom(make_context()))
        self.assertEqual(len(logs.records), 1, "the hint is shown once, not on every poll")
        self.assertIn(".apmedabots", logs.output[0])

    async def test_other_games_are_left_alone_quietly(self):
        self.memory.rom[:] = build_rom("POKEMON EMERBPEE01")
        with self.assertNoLogs("Client"):
            self.assertFalse(await self.client.validate_rom(make_context()))

    async def test_an_unreadable_rom_is_not_claimed(self):
        self.memory.rom[:] = b"\0" * 64
        self.assertFalse(await self.client.validate_rom(make_context()))

    async def test_unverified_patches_warn_the_player(self):
        self.memory.rom[:] = patched_rom(unverified=True)
        self.client.data = DATA  # verified now, but the patch was made from an unverified build
        with self.assertLogs("Client", "WARNING"):
            self.assertTrue(await self.client.validate_rom(make_context()))

    async def test_the_slot_name_comes_from_the_rom(self):
        await self.client.validate_rom(make_context())
        ctx = make_context()
        await self.client.set_auth(ctx)
        self.assertEqual(ctx.auth, "Ash")


class TestServerPackages(ClientTestCase):
    async def asyncSetUp(self):
        await self.client.validate_rom(make_context())

    async def test_matching_seed_is_accepted(self):
        self.client.on_package(make_context(), "RoomInfo", {"seed_name": SEED})
        self.assertIsNone(self.client.blocked)

    async def test_rom_for_another_multiworld_stops_the_client(self):
        with self.assertLogs("Client", "ERROR"):
            self.client.on_package(make_context(), "RoomInfo", {"seed_name": "someone-elses-seed"})
        self.assertIn("different multiworld", self.client.blocked)

    async def test_a_foreign_seed_is_caught_even_if_room_info_came_first(self):
        """RoomInfo can arrive before the ROM is recognised, so the slot data must be checked as well."""
        with self.assertLogs("Client", "ERROR"):
            self.client.on_package(make_context(), "Connected", {"slot_data": {**SLOT_DATA, "seed_name": "other"}})
        self.assertIn("different multiworld", self.client.blocked)

    async def test_seed_from_another_world_version_stops_the_client(self):
        with self.assertLogs("Client", "ERROR"):
            self.client.on_package(make_context(), "Connected", {"slot_data": {**SLOT_DATA, "data_hash": "0" * 64,
                                                                               "world_version": "9.9.9"}})
        self.assertIn("9.9.9", self.client.blocked)

    async def test_connecting_requests_the_delivery_counter(self):
        ctx = make_context()
        self.client.on_package(ctx, "Connected", {"slot_data": SLOT_DATA})
        await asyncio.sleep(0)
        self.assertEqual(ctx.sent, [{"cmd": "Get", "keys": ["medabots_rpg_0_1_applied"]}])
        self.assertFalse(self.client.counter_loaded)

    async def test_the_stored_counter_is_adopted(self):
        ctx = make_context()
        self.client.on_package(ctx, "Retrieved", {"keys": {"medabots_rpg_0_1_applied": 7}})
        self.assertEqual((self.client.state.applied_index, self.client.counter_loaded), (7, True))
        self.client.on_package(ctx, "Retrieved", {"keys": {"medabots_rpg_0_1_applied": None}})
        self.assertEqual(self.client.state.applied_index, 0)

    async def test_unrelated_packages_are_ignored(self):
        self.client.on_package(make_context(), "Retrieved", {"keys": {"something_else": 3}})
        self.assertFalse(self.client.counter_loaded)


class TestGameWatcher(ClientTestCase):
    async def test_does_nothing_while_not_connected_to_a_server(self):
        await self.client.validate_rom(make_context())
        reads = self.bh.reads
        ctx = make_context(slot_data=dict(SLOT_DATA))
        ctx.server = None
        await self.client.game_watcher(ctx)
        self.assertEqual(self.bh.reads, reads)

    async def test_does_nothing_once_blocked(self):
        ctx = await self.connect()
        reads = self.bh.reads
        self.client.blocked = "mismatch"
        await self.client.game_watcher(ctx)
        self.assertEqual(self.bh.reads, reads)

    async def test_a_new_location_is_reported_exactly_once(self):
        ctx = await self.connect(missing={20003, 20001})
        self.memory.set_bit(FLAGS, FLAG_BIT_SQUIDGUTS)
        await self.client.game_watcher(ctx)
        await self.client.game_watcher(ctx)
        self.assertEqual(ctx.sent, [{"cmd": "LocationChecks", "locations": [20003]}])
        self.assertEqual(ctx.locations_checked, {20003})

    async def test_story_goal_is_reported_once(self):
        ctx = await self.connect()
        await self.client.game_watcher(ctx)
        self.assertEqual(ctx.sent, [])
        self.memory.set_bit(FLAGS, FLAG_BIT_STORY_COMPLETE)
        await self.client.game_watcher(ctx)
        await self.client.game_watcher(ctx)
        self.assertEqual(ctx.sent, [{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])

    async def test_collection_goal_is_reported_when_enough_medals_arrived(self):
        ctx = await self.connect(received=[("Medal: Cat", 0, 0), ("Medal: Bat", 2, 0)])
        ctx.slot_data.update(goal="collect_medals", goal_medal_count=3)
        await self.client.game_watcher(ctx)
        self.assertNotIn({"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}, ctx.sent)
        ctx.items_received.append(NetworkItem(NAME_TO_ID["Medal: Ghost"], 0, 2, 0))
        await self.client.game_watcher(ctx)
        self.assertIn({"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}, ctx.sent)

    async def test_items_are_delivered_announced_and_counted(self):
        ctx = await self.connect(received=[("Money Pouch (Medium)", 2, 0b001)])
        await self.client.game_watcher(ctx)
        self.assertEqual(self.memory.u32(MONEY), MEDIUM_POUCH)
        self.assertEqual(self.bh.messages, ["Received Money Pouch (Medium) from Misty"])
        counter = [m for m in ctx.sent if m["cmd"] == "Set"]
        self.assertEqual(counter[0]["key"], "medabots_rpg_0_1_applied")
        self.assertEqual(counter[0]["operations"], [{"operation": "replace", "value": 1}])
        await self.client.game_watcher(ctx)
        self.assertEqual(self.memory.u32(MONEY), MEDIUM_POUCH, "not delivered twice")

    async def test_nothing_is_delivered_before_the_counter_is_known(self):
        ctx = await self.connect(received=[("Money Pouch (Medium)", 2, 0)])
        self.client.counter_loaded = False
        await self.client.game_watcher(ctx)
        self.assertEqual(self.memory.u32(MONEY), 0)

    async def test_a_failed_guard_changes_nothing_and_is_retried(self):
        ctx = await self.connect(received=[("Money Pouch (Small)", 2, 0)])
        self.memory.fail_next_guard = True
        await self.client.game_watcher(ctx)
        self.assertEqual((self.memory.u32(MONEY), self.client.state.applied_index, self.bh.messages), (0, 0, []))
        self.assertEqual([m for m in ctx.sent if m["cmd"] == "Set"], [])
        await self.client.game_watcher(ctx)
        self.assertEqual((self.memory.u32(MONEY), self.client.state.applied_index), (SMALL_POUCH, 1))

    async def test_bizhawk_hiccups_are_survived(self):
        ctx = await self.connect(received=[("Money Pouch (Small)", 2, 0)])
        self.bh.raise_on_read = True
        await self.client.game_watcher(ctx)  # must not raise
        self.bh.raise_on_read = False
        await self.client.game_watcher(ctx)
        self.assertEqual(self.memory.u32(MONEY), SMALL_POUCH)

    async def test_progression_only_messages(self):
        ctx = await self.connect(received=[("Money Pouch (Small)", 2, 0), ("Medal: Cat", 2, 0b001)])
        ctx.slot_data["receive_item_messages"] = "progression_only"
        await self.client.game_watcher(ctx)
        self.assertEqual(self.bh.messages, ["Received Medal: Cat from Misty"])

    async def test_the_domain_used_for_memory_comes_from_the_memory_map(self):
        self.assertEqual(DATA.memory_map.domain, SYSTEM_BUS)
