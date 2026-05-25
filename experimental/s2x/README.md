# S2x camera tilt / servo probe

Macrochip apps (PL FPV, HiTurbo, REDRIE FLY, LOILEY FLY) send **20-byte HY** packets
`66 14 RR PP TT YY F1 F2 [8..17] CHK 99` on UDP **8080**. The decompiled
`HyControlConsumer` **always zeroes bytes 8–17** — likely because those apps have
no tilt UI, **not** because the flight board ignores them.

TurboDrone’s `s2x` adapter does the same. This tool probes whether firmware on
**S29 / PL-515 / S20** (or any `DRONE_TYPE=s2x` drone) still reacts to non-zero
bytes or to **ST3** side commands (`ff 53 54 33 <param> <value>`).

## Why this is worth trying (unlike guessing blindly)

| Evidence | Implication |
|----------|-------------|
| README: **S29 has a camera tilt servo** | Hardware may exist even if the app doesn’t drive it |
| Apps zero bytes 8–17 in Java | **Absence in app ≠ absence in firmware** (your hypothesis) |
| Same pattern as CooingDV GL reserved zeros | M10 sweep was negative, but S2x is a **different chipset** (XR872 / Macrochip) |
| `sendFlowParam` / `WifiCommandHelper` ST3 commands on same port | Tilt may be a **param ID**, not a byte in the HY frame |

## Before you start

1. Connect to the drone Wi‑Fi (often gateway **172.16.10.1** — check your DHCP).
2. Stop TurboDrone so nothing else owns UDP 8080.
3. Table, props off if possible, battery in.
4. Watch the camera: UDP video on **8888**, or stock PL FPV preview.

```powershell
cd turbodrone\experimental\s2x
python s2x_tilt_probe.py --drone-ip 172.16.10.1 --video-keepalive
```

Use your actual gateway if different (`ipconfig` while on drone Wi‑Fi).

## Quick start: auto ST3 sweep (recommended)

Best first test for hidden **tilt / lens / gimbal** on Macrochip drones when the
stock app has no tilt slider. Sends `ff 53 54 33 <param> <value>` on UDP **8080**
while a neutral **HY** stream keeps the link alive (~20 Hz). Includes values
**25** and **40** used by LOILEY FLY for dual-lens (`param=18`).

```powershell
cd turbodrone\experimental\s2x
python s2x_tilt_probe.py --mode st3 --auto-sweep --video-keepalive --log-file st3_sweep.log -v
```

- **~12–15 min** with defaults (params `0..48`, values `0,1,2,25,40,255`, 2.5 s per combo).
- Watch the camera (UDP **8888** or stock app preview). Note any line where the
  lens moves, tilts, or switches — especially `ST3 param=18 value=25` or `value=40`.
- Stop TurboDrone first so nothing else uses UDP 8080.

**LOILEY FLY / dual-lens only** (fast spot-check before the full sweep):

```powershell
python s2x_ptz_helper.py --once st3 --st3-param 18 --st3-value 40 --video-keepalive
python s2x_ptz_helper.py --once st3 --st3-param 18 --st3-value 25 --video-keepalive
```

If ST3 finds nothing but you suspect **servo tilt** (not lens switch), try the
Ruko-style angle command next: `python s2x_ptz_helper.py --once st-set --angle 140 --video-keepalive`.

## Modes

### `hy` — main hypothesis (reserved bytes 8–17)

Sends neutral sticks (`0x80`) and toggles one byte at a time. Checksum matches
TurboDrone (XOR bytes 2–17).

```powershell
# Interactive (keys 0–9 = bytes 8–17, +/- = values, n = neutral)
python s2x_tilt_probe.py --mode hy

# Automated (~4 min) + log
python s2x_tilt_probe.py --mode hy --auto-sweep --log-file hy_sweep.log -v
```

### `st3` — side-channel hypothesis

Sends `ff 53 54 33 <param> <value>` while keeping a neutral HY stream alive.
Default: params `0..48`, values `0,1,2,25,40,255` (25/40 from LOILEY FLY lens UI).

Same as [Quick start: auto ST3 sweep](#quick-start-auto-st3-sweep-recommended) above.
Shorter value list if you are in a hurry:

```powershell
python s2x_tilt_probe.py --mode st3 --auto-sweep --video-keepalive --st3-values 0,1,2,255 --log-file st3_sweep.log -v
```

If tilt or lens motion appears, note **param** and **value** (e.g. `param=18 value=40`).
Known labels in the log: `param=18 (lens_switch)`, `param=16/22 (camera_index_query)`.

### `all` — full pass

HY sweep, then ST3 sweep (~15–25 min depending on `--st3-param-max`).

```powershell
python s2x_tilt_probe.py --mode all --auto-sweep --video-keepalive --log-file full_sweep.log
```

### Resume after interrupt

HY phases run in order: **reserved** (bytes 8–17) → **flags6** → **flags7** → **patterns**.

If the script stops mid-run, note the last log line and restart from the next phase:

```powershell
# Example: stopped during flags6 (last line was byte[17]=0xff)
python s2x_tilt_probe.py --mode hy --auto-sweep --hy-from flags6 --log-append --log-file hy_sweep.log --video-keepalive -v

# Stopped at flags7=0x8a — resume patterns only (~15 s)
python s2x_tilt_probe.py --mode hy --auto-sweep --hy-from patterns --log-append --log-file hy_sweep.log --video-keepalive -v
```

If the last line was **`tilt-b8b9-01-02`**, the HY sweep is **finished** — run ST3 instead (do not re-run HY):

```powershell
python s2x_tilt_probe.py --mode st3 --auto-sweep --video-keepalive --log-file st3_sweep.log -v
```

## Interpreting results

- **Camera moves** during a specific byte/value or ST3 param → document it in
  `docs/research/S2x.md` and we wire it into `s2x_rc_protocol_adapter.py`.
- **LED / beep / mode changes only** (like M10 CooingDV sweep) → invalid combo,
  not tilt.
- **Nothing** on HY **and** ST3 → try stock PL FPV tilt UI + Wireshark, or
  handset-only servo (2.4 GHz controller, not Wi‑Fi).

## After a hit

1. Re-run interactively on that byte/param to confirm.
2. Update research doc + adapter.
3. Enable `camera_tilt` in web_server for `s2x` if stable.

## PTZ helper (`s2x_ptz_helper.py`)

For **confirmed Macrochip ST tilt** commands (Ruko Drone / Ruko GIM F11GIM3 apps)
while keeping the normal
`66 14` HY stream alive — useful on PL-515 / S29 when PL FPV has no tilt UI.

```powershell
cd turbodrone\experimental\s2x
python s2x_ptz_helper.py --video-keepalive
```

Interactive: **`s`** = ST set angle (`FF 53 54 32 01 <angle>`), **`u`/`d`** = angle
±5, **`t`** = try ST + HACK_FLY + FEI_SHA set paths, **`g`** = get angle.

One-shot:

```powershell
python s2x_ptz_helper.py --once st-set --angle 140 --video-keepalive
python s2x_ptz_helper.py --once st3 --st3-param 18 --st3-value 40 --video-keepalive
python s2x_ptz_helper.py --preset-sweep --video-keepalive --log-file ptz_sweep.log
```

Stop TurboDrone first so UDP 8080 is free. Try **`s` (ST)** before TCP variants
(`k` / `f`).

## Related

- `turbodrone/docs/research/S2x.md` — packet layout, Ruko PTZ, and ST3 notes
- `turbodrone/experimental/cooingdv/` — same idea for CooingDV GL (M10 negative)
