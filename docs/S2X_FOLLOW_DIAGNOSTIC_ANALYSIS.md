# S2X Follow Plugin Diagnostic Analysis

## Summary of Facts
1. **Frontend is NOT sending zero messages intermittently** when follow plugin is enabled (verified in logs)
2. **WiFi-UAV drones respond correctly** to follow plugin commands
3. **S2x drones do NOT respond** to follow plugin commands
4. Both drone types go through the same `FlightController` and follow plugin code paths

## Architecture Review

### Control Flow Path (Both Drones)
```
FollowService._loop()
  ↓
  yaw, pitch = self.ctrl.current_commands()  # Returns percentage points (e.g., -40 to +40)
  ↓
  self.fc.set_axes_from("follow", throttle=0, yaw=yaw/100.0, pitch=pitch/100.0, roll=0)  # Normalizes to -1..+1
  ↓
FlightController.set_axes_from()
  ↓ stores normalized -1..+1 in self.{throttle,yaw,pitch,roll}_dir
  ↓
FlightController._control_loop() @ 80Hz
  ↓
  self.model.update(dt, {"throttle": self.throttle_dir, "yaw": self.yaw_dir, ...})
  ↓
[BRANCH POINT: Strategy determines what happens next]
  ↓
DirectStrategy.update() → model._scale_normalised() → sets raw stick values directly
  OR
IncrementalStrategy.update() → model._update_axes_incremental() → accelerates/decelerates over time
  ↓
  packet = self.protocol.build_control_packet(self.model)
  ↓
  self.protocol.send_control_packet(packet)
```

### Key Difference: Stick Ranges

**S2x (S20/S29):**
```python
STICK_RANGE = StickRange(60, 128, 200)  # min, center, max
# Usable range: 68 units below center, 72 units above center
# Total range: 140 units
```

**WiFi-UAV:**
```python
STICK_RANGE = StickRange(40, 128, 220)  # min, center, max
# Usable range: 88 units below center, 92 units above center
# Total range: 180 units
```

### _scale_normalised() Math

Located in `backend/models/base_rc.py:90-97`:
```python
def _scale_normalised(self, value: float) -> float:
    """Map a normalised [-1 … +1] input to raw protocol units"""
    if value >= 0:
        return self.center_value + value * (self.max_control_value - self.center_value)
    return self.center_value + value * (self.center_value - self.min_control_value)
```

**Example: yaw = +0.20 (20% deflection, a typical follow command)**

S2x calculation:
- `128 + 0.20 * (200 - 128) = 128 + 0.20 * 72 = 128 + 14.4 = 142.4`
- Packet byte: `0x8E` (142 decimal)
- Deflection from center: **14 units**

WiFi-UAV calculation:
- `128 + 0.20 * (220 - 128) = 128 + 0.20 * 92 = 128 + 18.4 = 146.4`
- Packet byte: `0x92` (146 decimal)
- Deflection from center: **18 units**

**WiFi-UAV produces ~29% more stick deflection for the same normalized input.**

### Protocol Adapter Remapping (S2x only)

`backend/protocols/s2x_rc_protocol_adapter.py:89-96`:
```python
def _remap_to_full_range(self, value, model):
    """Remap value from constrained range to full 0-255 range for sending to drone"""
    if value >= model.center_value:
        # Map center...max_control to 128...255
        return 128.0 + (value - model.center_value) * (255.0 - 128.0) / (model.max_control_value - model.center_value)
    else:
        # Map min_control...center to 0...128
        return (value - model.min_control_value) * 128.0 / (model.center_value - model.min_control_value)
```

**Continuing example: raw stick = 142.4**

S2x remapping:
- `128.0 + (142.4 - 128) * 127 / (200 - 128)`
- `128.0 + 14.4 * 127 / 72`
- `128.0 + 14.4 * 1.764 = 128.0 + 25.4 = 153.4`
- Final packet byte: `0x99` (153 decimal)
- **Net deflection from 0x80 (128): 25 units**

WiFi-UAV (no remapping, uses raw value directly):
- Raw stick = 146.4
- Packet byte: `0x92` (146 decimal)
- **Net deflection from 0x80 (128): 18 units**

**Wait... S2x actually gets MORE deflection after remapping!**

So the stick range difference is NOT the root cause.

## Critical Discovery: Strategy Application Timing

### Follow Plugin Strategy Switch
`backend/plugins/follow/follow_service.py:126-137`:
```python
follow_strategy = os.getenv("FOLLOW_STRATEGY", "direct").lower()
self._prev_strategy = getattr(self.fc.model, "strategy", None)
self._prev_expo = getattr(self.fc.model, "expo_factor", None)

try:
    if follow_strategy == "incremental":
        from control.strategies import IncrementalStrategy
        self.fc.model.set_strategy(IncrementalStrategy())
        print(f"[FollowService] Using IncrementalStrategy (expo preserved)")
    else:
        self.fc.model.set_strategy(DirectStrategy())
        # Disable expo so tiny commands aren't squashed by v^(1+expo)
        try:
            self.fc.model.expo_factor = 0.0
            print(f"[FollowService] Using DirectStrategy with expo=0.0")
```

### Default Strategies

**S2x Model** (`backend/models/s2x_rc.py:23`):
```python
self.strategy = IncrementalStrategy()   # default
```

**WiFi-UAV Model** (`backend/models/wifi_uav_rc.py:37`):
```python
self.strategy = IncrementalStrategy()   # default
```

**Both models default to IncrementalStrategy!**

### IncrementalStrategy Behavior

`backend/control/strategies.py:13-16`:
```python
class IncrementalStrategy(ControlStrategy):
    def update(self, model, dt, axes):
        # axes entries are  -1, 0, +1  (discrete keys)
        model._update_axes_incremental(dt, axes)
```

**The problem:** IncrementalStrategy is designed for KEYBOARD input where axes are discrete `-1, 0, +1` values.

When follow sends continuous values like `yaw=0.20`, IncrementalStrategy treats it as:
- If value > 0: accelerate toward max
- If value < 0: accelerate toward min  
- If value == 0: decelerate to center

**It doesn't respect the MAGNITUDE of the input!**

The incremental update accumulates over time based on `accel_rate` and `decel_rate`, not the input value.

## Root Cause Hypothesis

### Theory: S2x has stricter deceleration or different profile tuning

Compare profiles:

**S2x** (`backend/models/s2x_rc.py:13-17`):
```python
PRESETS = {
    "normal":     ControlProfile("normal",     2.08, 4.86, 0.5, 0.02),
    "precise":    ControlProfile("precise",    1.39, 5.56, 0.3, 0.01),
    "aggressive": ControlProfile("aggressive", 4.17, 3.89, 1.5, 0.11),
}
# Default: accel=2.08, decel=4.86, expo=0.5, immediate=0.02
```

**WiFi-UAV** (`backend/models/wifi_uav_rc.py:27-32`):
```python
PRESETS = {
    "normal":     ControlProfile("normal",     2.0, 4.0, 0.5, 0.02),
    "precise":    ControlProfile("precise",    1.2, 5.0, 0.3, 0.01),
    "aggressive": ControlProfile("aggressive", 4.0, 3.0, 1.2, 0.10),
}
# Default: accel=2.0, decel=4.0, expo=0.5, immediate=0.02
```

**S2x has HIGHER deceleration rate (4.86 vs 4.0).**

### What Happens with IncrementalStrategy + High Decel

When follow plugin switches to DirectStrategy but the model is STILL using IncrementalStrategy (if the switch fails or doesn't apply):

1. Follow sends `yaw=0.15` (15% right)
2. IncrementalStrategy sees `yaw > 0`, starts accelerating right
3. But the acceleration is slow (2.08 * half_range * dt)
4. With 80Hz loop, dt = 0.0125s
5. half_range for S2x = 72, so accel per tick = 2.08 * 72 * 0.0125 = 1.87 units/tick
6. To reach yaw=142 from center=128 needs 14 units → takes ~7-8 ticks = ~100ms
7. But if follow updates faster than that, OR if the decel kicks in when follow adjusts, sticks never build momentum

**WiFi-UAV with lower decel rate (4.0) might accumulate enough deflection before decel kicks in.**

## Alternative Theory: Strategy Switch Not Applied to S2x

Check if `set_strategy()` actually works on S2xDroneModel.

`backend/models/s2x_rc.py:119-120`:
```python
def set_strategy(self, strategy) -> None:
    self.strategy = strategy
```

Looks correct. But is it being called?

## Critical Questions for Log Analysis

### 1. **Is DirectStrategy actually being applied?**

Look for in RC-Loop logs:
```
[RC-Loop] src=follow   norm T:+0.00 Y:+0.15 P:+0.05 R:+0.00 | raw T:128 Y:142 P:135 R:128 | strat=DirectStrategy
```

If you see `strat=IncrementalStrategy` when follow is running, **the strategy switch failed**.

### 2. **Are raw stick values moving away from 128?**

In the RC-Loop logs, check the `raw Y:` and `raw P:` values:
- **Expected (DirectStrategy):** Raw values should instantly jump to match normalized input
  - `norm Y:+0.20` → `raw Y:~142-153` (depending on remapping)
- **Wrong (IncrementalStrategy):** Raw values creep slowly from 128
  - After 1 second: might only reach 135-140
  - Never stabilize at the target value

### 3. **Does expo_factor get set to 0.0?**

DirectStrategy still uses expo if present:
```python
expo = getattr(model, "expo_factor", 0.0)
if expo:
    sign = 1 if v >= 0 else -1
    v = sign * (abs(v) ** (1 + expo))
```

S2x default expo = 0.5, so `0.20^1.5 = 0.089` → command gets crushed by ~55%!

Look for:
```
[FollowService] Using DirectStrategy with expo=0.0
```

If this line is missing or expo is not actually 0.0, follow commands are being heavily attenuated.

### 4. **Are follow commands even reaching FlightController?**

Enable `FOLLOW_DEBUG_AXES=true` and look for:
```
[FollowService] cmd yaw=+15.0 pitch=+8.0 -> norm Y:+0.15 P:+0.08 | raw Y:142 P:138
```

Then check if corresponding `[RC-In]` log appears:
```
[RC-In] src=follow   norm T:+0.00 Y:+0.15 P:+0.08 R:+0.00 | raw T:128 Y:??? P:??? R:128
```

If raw values in RC-In don't match FollowService output, something is wrong in `set_axes_from`.

### 5. **Is there a difference in packet send frequency?**

WiFi-UAV shares socket with video layer; S2x uses separate socket.

Check if S2x RC packets are being sent at 80Hz:
- Count `[RC-Loop]` lines over 10 seconds → should be ~800 lines
- If significantly less, RC loop is stalled or slow

### 6. **Are S2x packets being sent to the correct IP/port?**

In S2x adapter debug (if enabled):
```
Packet #1234: 66 14 80 88 80 80 00 0a 00 00 00 00 00 00 00 00 00 00 ab 99
  Controls: R:128 P:136 T:128 Y:128
```

Check that pitch/yaw bytes (indices 2-5) are moving.

## Recommended Log Collection Sequence

### Step 1: Enable comprehensive logging
```bash
export FLIGHT_LOG_CONTROLS=true
export FOLLOW_LOG_ENABLED=true
export FOLLOW_LOG_INTERVAL=0.5
export FOLLOW_DEBUG_AXES=true
```

### Step 2: Start backend and watch for strategy confirmation
Look for:
```
[FollowService] Using DirectStrategy with expo=0.0
```

### Step 3: Start follow plugin and capture 10 seconds of logs

Key patterns to search for:

**Pattern A: Strategy mismatch**
```
[RC-Loop] ... | strat=IncrementalStrategy
```
→ **Problem:** Strategy switch failed

**Pattern B: Expo not disabled**
```python
# If you don't see "expo=0.0" in startup logs, add a debug print in FlightController
print(f"[DEBUG] Model expo_factor = {getattr(self.model, 'expo_factor', None)}")
```
→ **Problem:** Expo is still active, crushing small commands

**Pattern C: Raw values not moving**
```
[RC-Loop] src=follow   norm T:+0.00 Y:+0.20 P:+0.10 R:+0.00 | raw T:128 Y:128 P:128 R:128 | ...
```
→ **Problem:** _scale_normalised not being called OR output being overwritten

**Pattern D: Raw values creeping slowly**
```
[RC-Loop] @ t=0.0s: raw Y:128
[RC-Loop] @ t=0.5s: raw Y:132
[RC-Loop] @ t=1.0s: raw Y:136
[RC-Loop] @ t=1.5s: raw Y:139
```
→ **Problem:** IncrementalStrategy is active, accumulating slowly

**Pattern E: Raw values jumping correctly**
```
[RC-Loop] @ t=0.0s: raw Y:128
[RC-Loop] @ t=0.0125s: raw Y:142   ← instant jump
[RC-Loop] @ t=0.025s: raw Y:142    ← stable
```
→ **Good:** DirectStrategy working, problem is elsewhere (gains, drone deadzone, etc.)

### Step 4: Compare S2x vs WiFi-UAV side-by-side

Run the same follow scenario on both drones and diff the logs.

Look for:
- Strategy name differences
- Raw stick value behavior (instant vs creeping)
- Packet send frequency
- Expo factor

## Likely Root Causes (Ranked)

### 1. **Strategy switch not being applied** (90% confidence)
- Follow plugin calls `set_strategy(DirectStrategy())` but it doesn't take effect
- S2x model continues using IncrementalStrategy
- Commands accumulate too slowly to overcome drone deadzone
- **Fix:** Add verification that strategy changed; force-set it in _control_loop if source=="follow"

### 2. **Expo not disabled** (70% confidence)
- Follow plugin sets `expo_factor = 0.0` but it's not persisted or DirectStrategy doesn't honor it
- Small follow commands (0.15-0.25) get crushed by `v^1.5`
- **Fix:** Verify expo=0.0 in logs; ensure DirectStrategy respects it

### 3. **S2x drone has larger deadzone than WiFi-UAV** (40% confidence)
- Even with correct stick values, S2x hardware ignores small deflections
- Would need to increase follow gains significantly
- **Fix:** Raise FOLLOW_P_GAIN_YAW/PITCH by 2-3x for S2x

### 4. **Axis mapping wrong for S2x** (20% confidence, you said swap_yaw_roll was an LLM suggestion)
- Commands going to wrong stick
- **Fix:** Verify with manual gamepad input that yaw/pitch axes respond

### 5. **Packet format or checksum issue** (5% confidence)
- S2x rejecting packets silently
- **Fix:** Enable packet debug, compare follow packets to manual packets

## Next Steps

1. **Collect logs with all debug flags enabled**
2. **Search for the 6 critical patterns above**
3. **Determine which theory matches the evidence**
4. **Apply targeted fix based on findings**

If logs show DirectStrategy is active and raw values are correct, the problem is downstream (gains/drone hardware). If logs show IncrementalStrategy or expo issues, the problem is in the strategy application.
