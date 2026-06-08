# Hisense AC Protocol Analysis - Checksum Solution

## Discovery
After analyzing the communication patterns, we discovered that this Hisense AC model doesn't use a traditional checksum. Instead, it uses a fixed pattern in the "checksum" position that only has 3 possible values:
- `0x05BD`
- `0x05BE` (most common)
- `0x05BF`

## What This Means
The bytes at position `[len-4][len-3]` that would normally contain a checksum are actually:
1. **Fixed prefix**: `0x05` (always the same)
2. **Variable suffix**: `0xBD`, `0xBE`, or `0xBF` (only last 2 bits vary)

This pattern suggests these bytes might be:
- A protocol version identifier
- A frame type indicator
- A simplified validation mechanism
- Or possibly a firmware bug where the checksum calculation was replaced with constants

## Solution Implemented

### 1. Frame Reception
- Accept any frame with values `0x05BD` through `0x05BF` in the checksum position
- Log but don't reject frames with other values (for debugging)
- This allows the component to read all status updates from the AC

### 2. Command Transmission
- Use `0x05BE` for all outgoing commands (the most commonly observed value)
- The query status command keeps its original value `0x01B3` as it was already working

## Testing Instructions

1. **Compile and Upload:**
   ```bash
   esphome run modern_hisense_ac/test_basic.yaml
   ```

2. **Monitor Initial Connection:**
   ```bash
   esphome logs modern_hisense_ac/test_basic.yaml
   ```
   
   You should see:
   - Status updates being received
   - Temperature readings
   - No more checksum warnings (or minimal warnings)

3. **Test Control Commands:**
   
   From Home Assistant, test each function:
   
   a. **Power Control:**
   - Turn AC ON → Should hear beep and see unit start
   - Turn AC OFF → Should hear beep and see unit stop
   
   b. **Temperature Control:**
   - Set to 20°C → AC should adjust
   - Set to 25°C → AC should adjust
   - Set to 30°C → AC should adjust
   
   c. **Mode Changes:**
   - COOL mode → Check if AC switches to cooling
   - HEAT mode → Check if AC switches to heating
   - DRY mode → Check if AC switches to dehumidify
   - FAN mode → Check if AC switches to fan only
   
   d. **Fan Speed:**
   - AUTO → AC should manage fan automatically
   - LOW → Fan should run slowly
   - MEDIUM → Fan should run at medium speed
   - HIGH → Fan should run fast
   
   e. **Swing Control:**
   - Vertical swing ON/OFF
   - Horizontal swing ON/OFF
   - Both swings ON/OFF

4. **Verify Feedback:**
   - After each command, the AC should beep
   - The display on the AC should update
   - Home Assistant should show the new state

## Troubleshooting

### Commands Still Not Working?

1. **Check Physical Connection:**
   - Ensure TX→RX and RX→TX connections are correct
   - Verify 5V and GND connections
   - Check that the UART adapter is properly inserted into the AC

2. **Try Different Command Values:**
   If `0x05BE` doesn't work, try modifying the code to use:
   - `0x05BD` instead
   - `0x05BF` instead
   
   Edit `hisense_ac.cpp` lines where we set:
   ```cpp
   cmd[cmd.size() - 4] = 0x05;
   cmd[cmd.size() - 3] = 0xBE;  // Try 0xBD or 0xBF
   ```

3. **Enable Debug Logging:**
   Use the debug configuration for more details:
   ```bash
   esphome run modern_hisense_ac/debug_test.yaml
   ```

### Reading Works But Commands Don't?

This might indicate:
- The AC expects a different command structure
- The AC needs a specific sequence (like authentication)
- The command timing needs adjustment

Try:
1. Increasing the delay between commands (edit `COMMAND_TIMEOUT_MS` in `hisense_ac.h`)
2. Sending the power ON command twice
3. Checking if the AC has a "lock" feature that needs to be disabled

## Technical Details

### Frame Structure
```
[F4 F5] [Type] [Length] [Data...] [05 BD/BE/BF] [F4 FB]
 Header                             "Checksum"    Footer
```

### Why This Works
- The AC firmware appears to validate frames by checking if bytes at the checksum position match the expected pattern
- It doesn't actually calculate or verify a mathematical checksum
- This is simpler but less robust than a true checksum

## Next Steps

If commands still don't work after these changes:
1. Capture the communication from the original remote/app
2. Compare the command structure with what we're sending
3. Look for any initialization or handshake sequences
4. Check if there's a different command format for this model

## Success Criteria

You'll know it's working when:
- ✅ No more checksum warnings in logs
- ✅ Temperature and status readings update correctly
- ✅ Commands sent from Home Assistant control the AC
- ✅ The AC beeps when receiving commands
- ✅ The AC display updates to show new settings