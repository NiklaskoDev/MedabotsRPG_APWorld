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
    event_flag_bit,
    new_medal_record,
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
    SHAPED_FLAGS,
    SHAPED_IN_BATTLE,
    SHAPED_MEDALS,
    SHAPED_MONEY,
    SHAPED_PARTS,
    SHAPED_SAFE,
    STORY_COMPLETE_EVENT,
    FakeMemory,
    medal_table,
    shaped_data,
    verified_data,
)

SELF = "Ash"


def snapshot_of(data: WorldData, memory: FakeMemory) -> Snapshot:
    raw = {path: memory.read(ref.address, ref.size) for path, ref in readable_tables(data.memory_map)}
    return Snapshot(data.memory_map, raw)


class Harness:
    """Runs plan_step against a fake memory exactly like the client does: plan, guard-check, write, adopt state."""

    def __init__(self, data: WorldData | None = None, medal_table: bytes | None = None):
        self.data = data or verified_data()
        self.medal_table = medal_table
        self.memory = FakeMemory()
        self.state = ClientState()
        self.clock = 1000.0
        self.last = None

    def step(self, received=(), *, repair=False, strength="normal", mode="all", advance=0.0):
        self.clock += advance
        plan = plan_step(self.data, snapshot_of(self.data, self.memory), list(received), self.state, own_name=SELF,
                         strength=strength, message_mode=mode, now=self.clock, repair=repair,
                         medal_table=self.medal_table)
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


class TestCalibratedShapes(unittest.TestCase):
    """The table shapes calibration found in the real game: nibble event flags, two-byte part counts and the medal
    case of 64-byte records."""

    data = shaped_data()

    def harness(self):
        return Harness(self.data, medal_table=medal_table())

    def snapshot(self, memory):
        return snapshot_of(self.data, memory)

    def set_event(self, memory, flag, value=0, done=True):
        nibble = (8 if done else 0) | value
        address = SHAPED_FLAGS + (flag >> 1)
        shift = 4 if flag % 2 == 0 else 0
        memory.set_byte(address, (memory.byte(address) & ~(0xF << shift)) | (nibble << shift))

    def test_event_flags_share_a_byte(self):
        self.assertEqual(event_flag_bit(148), 74 * 8 + 7)
        self.assertEqual(event_flag_bit(1609), 804 * 8 + 3)

    def test_locations_are_found_by_their_event_flag(self):
        memory = FakeMemory()
        wanted = {loc.id for loc in self.data.locations}
        self.set_event(memory, 1610)
        self.assertEqual(detect_checked_locations(self.data, self.snapshot(memory), wanted), {20011})
        self.set_event(memory, 1611)  # the neighbour in the same byte
        self.assertEqual(detect_checked_locations(self.data, self.snapshot(memory), wanted), {20011, 20012})

    def test_event_value_detection(self):
        memory = FakeMemory()
        wanted = {20006}
        self.set_event(memory, 606, value=0, done=True)
        self.assertEqual(detect_checked_locations(self.data, self.snapshot(memory), wanted), set(), "done alone")
        self.set_event(memory, 606, value=1, done=False)
        self.assertEqual(detect_checked_locations(self.data, self.snapshot(memory), wanted), {20006})

    def test_story_complete_event(self):
        memory = FakeMemory()
        self.assertFalse(story_complete(self.data, self.snapshot(memory)))
        self.set_event(memory, STORY_COMPLETE_EVENT)
        self.assertTrue(story_complete(self.data, self.snapshot(memory)))

    def test_a_part_raises_its_count_from_zero_only(self):
        harness = self.harness()
        name = part_item_name(self.data.tables, 39, 3)
        harness.step(harness.receive(name))
        address = SHAPED_PARTS + 3 * 240 + 39 * 2
        self.assertEqual((harness.memory.byte(address), harness.memory.byte(address + 1)), (1, 0))
        harness.memory.set_byte(address, 5)
        harness.step(harness.receive(name), repair=True)
        self.assertEqual(harness.memory.byte(address), 5, "owning more is left alone")

    def test_a_medal_becomes_a_record_like_the_game_makes(self):
        harness = self.harness()
        harness.memory.set_byte(SHAPED_MEDALS + 64, 0x01)  # the game keeps a slot number in the low bits
        harness.memory.write(SHAPED_MEDALS, new_medal_record(2, medal_table()[32:48], [0] * 30, 0, "Tortoise", 64))
        harness.step(harness.receive("Medal: Bat"))
        record = harness.memory.read(SHAPED_MEDALS + 64, 64)
        self.assertEqual(record[:10], bytes([0x81, 15, 100, 0, 15, 0, 1, 7, 0, 0]))
        self.assertEqual(record[0x0A:0x18], bytes([2, 1, 20]) + bytes([0xFE]) * 11, "BAT, padded")
        self.assertEqual(record[0x20:0x28], bytes([8, 0, 8, 0, 0, 0, 6, 6]))

    def test_a_medal_is_not_added_twice(self):
        harness = self.harness()
        harness.step(harness.receive("Medal: Bat"))
        harness.step(harness.receive("Medal: Bat"), repair=True)
        used = [harness.memory.byte(SHAPED_MEDALS + 64 * i) & 0x80 for i in range(30)]
        self.assertEqual(sum(1 for flag in used if flag), 1)

    def test_new_medals_start_between_the_best_and_the_fourth_best(self):
        record = new_medal_record(5, medal_table()[80:96], [40, 30, 20, 10] + [0] * 26, 0, "Spider", 64)
        self.assertEqual(record[5], 25)
        self.assertEqual(int.from_bytes(record[2:4], "little"), 2600)
        self.assertEqual(record[8], 0, "level 25 is below the first threshold of 30")
        self.assertEqual(record[0x20], 24, "base 8 times (25 // 10 + 1)")

    def test_medals_wait_without_the_rom_medal_table(self):
        harness = Harness(self.data)
        harness.step(harness.receive("Medal: Bat"))
        self.assertEqual(harness.state.applied_index, 0)
        self.assertEqual(harness.memory.writes, [])

    def test_nothing_is_delivered_during_a_battle(self):
        harness = self.harness()
        harness.memory.set_byte(SHAPED_IN_BATTLE, 1)
        harness.step(harness.receive("Money Pouch (Small)"))
        self.assertEqual((harness.memory.u32(SHAPED_MONEY), harness.state.applied_index), (0, 0))
        harness.memory.set_byte(SHAPED_IN_BATTLE, 0)
        harness.step(harness.receive("Money Pouch (Small)"))
        self.assertEqual(harness.memory.u32(SHAPED_MONEY), 200)

    def test_nothing_is_delivered_while_a_script_runs(self):
        harness = self.harness()
        harness.memory.set_byte(SHAPED_SAFE, 1)
        harness.step(harness.receive("Money Pouch (Small)"))
        self.assertEqual(harness.state.applied_index, 0)
