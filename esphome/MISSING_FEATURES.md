# Missing Features from alt_impl_2

## Critical Features We Should Add

### 1. Flow Control Pin (RS485 Direction Control)
**Why it matters**: Many Hisense AC units use half-duplex RS485 communication
```cpp
// Before sending
if (flow_control_pin_) flow_control_pin_->digital_write(true);
// Send data
// After sending  
if (flow_control_pin_) flow_control_pin_->digital_write(false);
```

### 2. State Machine for Robust Communication
Current implementation lacks proper state management:
- Add timeout handling (10 seconds no response = reset)
- Add retry logic with 8-second backoff
- Add state tracking for commands vs queries

### 3. Display Control
Add ability to turn AC display on/off:
```cpp
// Byte 36 controls display
status[36] = display_on ? 0b11000000 : 0b01000000;
```

## Encoding Differences to Check

### Temperature Encoding
alt_impl_2 uses:
```cpp
temp_byte = (temp << 1) | 0x01;  // Shift left and OR with 1
```
We use:
```cpp
temp_byte = (temp << 1) | 0x01;  // Same!
```

### Mode Encoding  
alt_impl_2 uses more complex encoding:
```cpp
mode_byte = ((mode << 1) | 1) << 4 | 0x0C;
```
We use simpler:
```cpp
mode_byte = 0x0C | (mode << 4);
```

### Swing Mode Values
alt_impl_2 uses different bit patterns:
- BOTH: `0xF0` (we use `0xC0`)
- OFF: `0x50` (we use `0x00`)
- VERTICAL: `0x30` (we use `0x80`)
- HORIZONTAL: `0x70` (we use `0x40`)

## Additional Features (Nice to Have)

### More Sensors
- Indoor/Outdoor coil temperatures (already partially supported)
- Humidity sensors
- Compressor current
- Expansion valve position

### Fan Speed Values
alt_impl_2 uses: 0, 1, 2, 10, 12, 14, 16, 18
We use: 0, 1, 2, 10, 14, 16, 18

## Quick Fixes to Try

1. **Add Flow Control Pin** (if using RS485)
2. **Try alt_impl_2 Swing Values**
3. **Try alt_impl_2 Mode Encoding**
4. **Add Display Control**

## Command Structure Comparison

### Query Status Command
Both use identical: `F4 F5 00 40 0C 00 00 01 01 FE 01 00 00 66 00 00 00`

### Control Command Structure
Position | alt_impl_2 | Ours | Notes
---------|------------|------|-------
18 | Mode+Power | Mode+Power | Different encoding
19 | Temperature | Temperature | Same encoding
23 | 0x04 | 0x04 | Same
32 | Swing | Swing | Different values
36 | Display | Not set | Missing feature

## Testing Priority

1. **Test with current checksum fix first**
2. If commands don't work, try:
   - Different swing values
   - Different mode encoding
   - Add display control byte
3. If using RS485, add flow control pin

## Code Changes Needed

### High Priority
- [ ] Add flow control pin support
- [ ] Fix swing mode values
- [ ] Add display control

### Medium Priority  
- [ ] Add state machine
- [ ] Add timeout/retry logic
- [ ] Try alternative mode encoding

### Low Priority
- [ ] Add more sensors
- [ ] Add command queuing