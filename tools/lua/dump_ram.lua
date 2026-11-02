-- Medabots RPG calibration helper for BizHawk (Game Boy Advance).
--
-- Press F9 to save a raw snapshot of the game's RAM. Compare two snapshots with tools/ramdiff.py to find where the game
-- keeps flags, owned parts, money and so on (see docs/CALIBRATION.md).
--
-- How to use it: in BizHawk open  Tools > Lua Console > Script > Open Script  and pick this file, load the game, and
-- press F9 whenever you want a snapshot. The files are written next to EmuHawk.exe (or to the folder BizHawk runs in)
-- as medabots_snapshot_<number>_<memory>.bin. Keep a note of what you did before each snapshot, the numbers are in
-- the order you pressed F9.

local OUTPUT_PREFIX = "medabots_snapshot"
local SNAPSHOT_KEY = "F9"
local CHUNK = 4096 -- bytes per file write; keeps string.char within Lua's argument limit

-- The two RAM areas of the Game Boy Advance. Sizes are those of the hardware.
local DOMAINS = {
    { name = "EWRAM", size = 0x40000, base = 0x02000000 },
    { name = "IWRAM", size = 0x08000, base = 0x03000000 },
}

local snapshot_count = 0
local key_was_down = false

local function write_snapshot(domain, path)
    memory.usememorydomain(domain.name)
    local bytes = memory.read_bytes_as_array(0, domain.size)
    local file, err = io.open(path, "wb")
    if not file then
        console.log("Could not write " .. path .. ": " .. tostring(err))
        return false
    end
    for first = 1, #bytes, CHUNK do
        local last = math.min(first + CHUNK - 1, #bytes)
        file:write(string.char(table.unpack(bytes, first, last)))
    end
    file:close()
    return true
end

local function take_snapshot()
    snapshot_count = snapshot_count + 1
    local all_ok = true
    for _, domain in ipairs(DOMAINS) do
        local path = string.format("%s_%03d_%s.bin", OUTPUT_PREFIX, snapshot_count, domain.name)
        if write_snapshot(domain, path) then
            console.log(string.format("Saved %s (%s starts at 0x%08X)", path, domain.name, domain.base))
        else
            all_ok = false
        end
    end
    gui.addmessage(string.format("Snapshot %d %s", snapshot_count, all_ok and "saved" or "FAILED, see the Lua console"))
end

console.log("Medabots RPG calibration helper: press " .. SNAPSHOT_KEY .. " to save a RAM snapshot.")

while true do
    local key_is_down = input.get()[SNAPSHOT_KEY] == true
    if key_is_down and not key_was_down then
        take_snapshot()
    end
    key_was_down = key_is_down
    emu.frameadvance()
end
