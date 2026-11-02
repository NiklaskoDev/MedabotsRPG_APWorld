"""Client game logic: location detection, item delivery, traps and their safety properties."""
import unittest

from ..data_loader import WorldData, get_world_data, part_item_name
from ..effects import (
    MAX_DELIVERIES_PER_TICK,
    TRAP_TIMEOUT_SECONDS,
    ClientState,
    Received,
    Snapshot,
    collection_goal_reached,
    detect_checked_locations,
    plan_step,
    readable_tables,
    story_complete,
)
from .support import (
    ARMOR_SCALE,
    FLAG_BIT_MEDAL_ROOM,
    FLAG_BIT_SQUIDGUTS,
    FLAG_BIT_STORY_COMPLETE,
    FLAGS,
    FORCE_ENCOUNTER,
    IN_BATTLE,
    MEDAL_DISABLE,
    MEDALS,
    MONEY,
    PARTS,
    SAFE,
    FakeMemory,
    verified_data,
)

SELF = "Ash"


def snapshot_of(data: WorldData, memory: FakeMemory) -> Snapshot:
    raw = {path: memory.read(ref.address, ref.size) for path, ref in readable_tables(data.memory_map)}
    return Snapshot(data.memory_map, raw)


class Harness:
    """Runs plan_step against a fake memory exactly like the client does: plan, guard-check, write, adopt state."""

    def __init__(self, data: WorldData | None = None):
        self.data = data or verified_data()
        self.memory = FakeMemory()
        self.state = ClientState()
        self.clock = 1000.0
        self.last = None

    def step(self, received=(), *, repair=False, strength="normal", mode="all", advance=0.0):
        self.clock += advance
        plan = plan_step(self.data, snapshot_of(self.data, self.memory), list(received), self.state, own_name=SELF,
                         strength=strength, message_mode=mode, now=self.clock, repair=repair)
        for (address, expected), (_, new) in zip(plan.guards, plan.writes, strict=True):
            assert self.memory.read(address, len(expected)) == expected, "guard would fail"
            self.memory.write(address, new)
        self.state = plan.state
        self.last = plan
        return plan

    def receive(self, *names, sender=SELF, advancement=False):
        return [Received(name, sender, advancement) for name in names]


class TestDetection(unittest.TestCase):
    data = verified_data()

    def test_checked_locations_are_found_by_their_flag(self):
        memory = FakeMemory()
        wanted = {loc.id for loc in self.data.locations}
        self.assertEqual(detect_checked_locations(self.data, snapshot_of(self.data, memory), wanted), set())
        memory.set_bit(FLAGS, FLAG_BIT_SQUIDGUTS)
        self.assertEqual(detect_checked_locations(self.data, snapshot_of(self.data, memory), wanted), {20003})
        memory.set_bit(FLAGS, FLAG_BIT_MEDAL_ROOM)
        self.assertEqual(detect_checked_locations(self.data, snapshot_of(self.data, memory), wanted), {20001, 20003})

    def test_only_wanted_locations_are_reported(self):
        memory = FakeMemory()
        memory.set_bit(FLAGS, FLAG_BIT_SQUIDGUTS)
        self.assertEqual(detect_checked_locations(self.data, snapshot_of(self.data, memory), {20001}), set())

    def test_unverified_locations_without_detection_are_ignored(self):
        shipped = get_world_data()
        snapshot = Snapshot(shipped.memory_map, {})
        self.assertEqual(detect_checked_locations(shipped, snapshot, {loc.id for loc in shipped.locations}), set())

    def test_story_complete_flag(self):
        memory = FakeMemory()
        self.assertFalse(story_complete(self.data, snapshot_of(self.data, memory)))
        memory.set_bit(FLAGS, FLAG_BIT_STORY_COMPLETE)
        self.assertTrue(story_complete(self.data, snapshot_of(self.data, memory)))

    def test_collection_goals_count_unique_items(self):
        medals = [f"Medal: {name}" for name in ("Kuwagata", "Kabuto", "Bear")]
        self.assertFalse(collection_goal_reached(self.data, medals, "collect_medals", 4, 0))
        self.assertFalse(collection_goal_reached(self.data, medals + medals[:1], "collect_medals", 4, 0))
        self.assertTrue(collection_goal_reached(self.data, medals + ["Medal: Cat"], "collect_medals", 4, 0))
        self.assertFalse(collection_goal_reached(self.data, medals, "story_complete", 1, 1))
        self.assertFalse(collection_goal_reached(self.data, [], "collect_medaparts", 0, 0), "needs at least one")


class TestDelivery(unittest.TestCase):
    def test_a_part_sets_its_ownership_bit_model_major(self):
        harness = Harness()
        harness.step(harness.receive(part_item_name(harness.data.tables, 3, 2)))
        self.assertTrue(harness.memory.bit(PARTS, 3 * 4 + 2))
        self.assertEqual(harness.state.applied_index, 1)

    def test_a_part_sets_its_ownership_bit_slot_major(self):
        harness = Harness(verified_data(parts_layout="slot_major"))
        harness.step(harness.receive(part_item_name(harness.data.tables, 3, 2)))
        self.assertTrue(harness.memory.bit(PARTS, 2 * 120 + 3))

    def test_a_medal_sets_its_bit(self):
        harness = Harness()
        harness.step(harness.receive("Medal: Kabuto"))
        self.assertTrue(harness.memory.bit(MEDALS, 1))

    def test_money_is_added_and_clamped_to_the_maximum(self):
        harness = Harness()
        harness.memory.set_u32(MONEY, 1000)
        harness.step(harness.receive("Money Pouch (Medium)"))
        self.assertEqual(harness.memory.u32(MONEY), 2000)
        harness.memory.set_u32(MONEY, 998_000)
        harness.step(harness.receive("Money Pouch (Medium)", "Money Pouch (Large)"))  # only the second is new
        self.assertEqual(harness.memory.u32(MONEY), 999_999)

    def test_nothing_is_delivered_twice(self):
        harness = Harness()
        received = harness.receive("Money Pouch (Small)", part_item_name(harness.data.tables, 0, 0))
        harness.step(received)
        harness.step(received)
        harness.step(received, repair=True)
        self.assertEqual(harness.memory.u32(MONEY), 200)
        self.assertEqual(harness.state.applied_index, 2)

    def test_nothing_happens_in_an_unsafe_state(self):
        harness = Harness()
        harness.memory.set_byte(SAFE, 1)
        harness.step(harness.receive("Money Pouch (Small)"))
        self.assertEqual(harness.memory.u32(MONEY), 0)
        self.assertEqual(harness.state.applied_index, 0)
        harness.memory.set_byte(SAFE, 0)
        harness.step(harness.receive("Money Pouch (Small)"))
        self.assertEqual(harness.memory.u32(MONEY), 200)

    def test_nothing_happens_when_the_safe_state_address_is_unknown(self):
        shipped = get_world_data()  # memory map without any address: the client must not guess
        plan = plan_step(shipped, Snapshot(shipped.memory_map, {}), [Received("Money Pouch (Small)", SELF, False)],
                         ClientState(), own_name=SELF, strength="normal", message_mode="all", now=0, repair=True)
        self.assertEqual((plan.writes, plan.state.applied_index), ([], 0))

    def test_deliveries_are_rationed_per_tick(self):
        harness = Harness()
        harness.step(harness.receive(*["Money Pouch (Small)"] * 10))
        self.assertEqual(harness.state.applied_index, MAX_DELIVERIES_PER_TICK)
        harness.step(harness.receive(*["Money Pouch (Small)"] * 10))
        harness.step(harness.receive(*["Money Pouch (Small)"] * 10))
        self.assertEqual(harness.state.applied_index, 10)
        self.assertEqual(harness.memory.u32(MONEY), 2000)

    def test_unknown_item_names_are_skipped_not_stuck_on(self):
        harness = Harness()
        harness.step(harness.receive("Item From The Future", "Money Pouch (Small)"))
        self.assertEqual(harness.state.applied_index, 2)
        self.assertEqual(harness.memory.u32(MONEY), 200)

    def test_loading_an_older_save_is_repaired(self):
        harness = Harness()
        received = harness.receive(part_item_name(harness.data.tables, 5, 1), "Medal: Cat")
        harness.step(received)
        harness.memory.ram[:] = bytes(len(harness.memory.ram))  # "load an older save": everything gone
        harness.step(received, repair=False)
        self.assertFalse(harness.memory.bit(PARTS, 5 * 4 + 1))
        plan = harness.step(received, repair=True)
        self.assertTrue(harness.memory.bit(PARTS, 5 * 4 + 1))
        self.assertTrue(harness.memory.bit(MEDALS, 26))
        self.assertEqual(plan.announcements, [], "repairs are silent")

    def test_repair_never_removes_anything(self):
        harness = Harness()
        harness.memory.set_bit(PARTS, 17)  # a part the player found in the game itself
        harness.step(harness.receive(part_item_name(harness.data.tables, 0, 0)), repair=True)
        self.assertTrue(harness.memory.bit(PARTS, 17))

    def test_writes_are_guarded_by_the_exact_bytes_that_were_read(self):
        harness = Harness()
        harness.memory.set_u32(MONEY, 1234)
        plan = harness.step(harness.receive("Money Pouch (Small)"))
        self.assertEqual(plan.guards, [(MONEY, (1234).to_bytes(4, "little"))])
        self.assertEqual(plan.writes, [(MONEY, (1434).to_bytes(4, "little"))])

    def test_an_item_that_cannot_be_delivered_blocks_without_losing_it(self):
        data = verified_data()
        harness = Harness(data)
        # make the money table vanish from the snapshot: the pouch cannot be delivered, so it must stay pending
        snapshot = snapshot_of(data, harness.memory)
        del snapshot.raw["tables.money"]
        plan = plan_step(data, snapshot, harness.receive("Money Pouch (Small)"), ClientState(), own_name=SELF,
                         strength="normal", message_mode="all", now=0, repair=False)
        self.assertEqual((plan.state.applied_index, plan.writes), (0, []))


class TestAnnouncements(unittest.TestCase):
    def texts(self, mode, *received):
        harness = Harness()
        return harness.step(list(received), mode=mode).announcements

    def test_modes(self):
        own = Received("Medal: Cat", SELF, True)
        other = Received("Money Pouch (Small)", "Misty", False)
        self.assertEqual(self.texts("all", own, other), ["Found Medal: Cat", "Received Money Pouch (Small) from Misty"])
        self.assertEqual(self.texts("progression_only", own, other), ["Found Medal: Cat"])
        self.assertEqual(self.texts("none", own, other), [])


class TestTraps(unittest.TestCase):
    def trap_harness(self):
        harness = Harness()
        harness.memory.set_u32(MONEY, 1000)
        harness.memory.set_byte(ARMOR_SCALE, 100)
        return harness

    def test_money_drain_takes_a_share_and_never_goes_below_zero(self):
        for strength, expected in (("mild", 900), ("normal", 750), ("harsh", 500)):
            harness = self.trap_harness()
            harness.step(harness.receive("Money Drain Trap"), strength=strength)
            self.assertEqual(harness.memory.u32(MONEY), expected, strength)
        harness = Harness()
        harness.step(harness.receive("Money Drain Trap"))
        self.assertEqual(harness.memory.u32(MONEY), 0)

    def test_rusty_armor_lasts_exactly_one_battle(self):
        harness = self.trap_harness()
        harness.step(harness.receive("Rusty Armor Trap"))
        self.assertEqual(harness.memory.byte(ARMOR_SCALE), 60)
        harness.memory.set_byte(IN_BATTLE, 1)
        harness.step(harness.receive("Rusty Armor Trap"))
        self.assertEqual(harness.memory.byte(ARMOR_SCALE), 60, "still active during the battle")
        harness.memory.set_byte(IN_BATTLE, 0)
        harness.step(harness.receive("Rusty Armor Trap"))
        self.assertEqual(harness.memory.byte(ARMOR_SCALE), 100, "restored when the battle is over")
        self.assertEqual(harness.state.traps, [])

    def test_medal_nap_harsh_lasts_two_battles(self):
        harness = self.trap_harness()
        received = harness.receive("Medal Nap Trap")
        harness.step(received, strength="harsh")
        self.assertEqual(harness.memory.byte(MEDAL_DISABLE), 1)
        for battle in (1, 2):
            harness.memory.set_byte(IN_BATTLE, 1)
            harness.step(received, strength="harsh")
            harness.memory.set_byte(IN_BATTLE, 0)
            harness.step(received, strength="harsh")
            self.assertEqual(harness.memory.byte(MEDAL_DISABLE), 1 if battle == 1 else 0)

    def test_ambush_is_re_armed_between_battles_for_a_series(self):
        harness = self.trap_harness()
        received = harness.receive("Ambush Trap")
        harness.step(received, strength="harsh")
        self.assertEqual(harness.memory.byte(FORCE_ENCOUNTER), 1)
        harness.memory.set_byte(FORCE_ENCOUNTER, 0)  # the game consumed the flag and started a battle
        harness.memory.set_byte(IN_BATTLE, 1)
        harness.step(received, strength="harsh")
        harness.memory.set_byte(IN_BATTLE, 0)
        harness.step(received, strength="harsh")
        self.assertEqual(harness.memory.byte(FORCE_ENCOUNTER), 1, "second ambush of the series")
        self.assertEqual(len(harness.state.traps), 1)

    def test_every_trap_is_lifted_after_a_timeout_even_if_no_battle_is_ever_reported(self):
        harness = self.trap_harness()
        harness.step(harness.receive("Rusty Armor Trap"))
        harness.step(harness.receive("Rusty Armor Trap"), advance=TRAP_TIMEOUT_SECONDS + 1)
        self.assertEqual(harness.memory.byte(ARMOR_SCALE), 100)
        self.assertEqual(harness.state.traps, [])

    def test_traps_do_not_stack(self):
        harness = self.trap_harness()
        harness.step(harness.receive("Rusty Armor Trap", "Rusty Armor Trap"))
        self.assertEqual(len(harness.state.traps), 1)

    def test_traps_never_fire_in_an_unsafe_state(self):
        harness = self.trap_harness()
        harness.memory.set_byte(SAFE, 1)
        harness.step(harness.receive("Money Drain Trap", "Rusty Armor Trap"))
        self.assertEqual((harness.memory.u32(MONEY), harness.memory.byte(ARMOR_SCALE)), (1000, 100))
        self.assertEqual(harness.state.applied_index, 0, "deferred, not dropped")

    def test_trap_without_its_memory_entry_fizzles_instead_of_guessing(self):
        harness = Harness(verified_data(with_optional=False))
        harness.step(harness.receive("Rusty Armor Trap"))
        self.assertEqual(harness.state.applied_index, 1)
        self.assertEqual(harness.state.traps, [])
        self.assertEqual(harness.memory.writes, [])
