# CooingDV GL camera tilt probe

Experimental tool to hunt for a hidden **camera tilt / servo** command in the
**21-byte GL** control packet used by drones like the **M10** (`resolution-id`
90–101, e.g. `101`).

Stock KY UFO / RC UFO apps keep **Wi-Fi bytes 9–18** at zero and do not expose
PTZ in the UI. This script tries non-zero values there (and unused flag bits)
while sticks stay centered so flight should not move much.

## Before you start

1. Connect the PC to the drone Wi‑Fi (`192.168.1.1`).
2. If you use multiple adapters on `192.168.1.x`, set the drone Wi‑Fi interface
   metric higher so traffic goes to the drone (same fix as TurboDrone).
3. Confirm the drone speaks **GL** (21-byte), not TC (9-byte). TurboDrone logs:
   `Auto-detected GL control variant. resolution-id=101`
4. **Safety:** table, props off if you can, battery in. Have `Esc` ready to stop
   the script (sends stop-ish `08 01` on exit).
5. Open video so you can see the camera angle:
   - TurboDrone UI, or
   - `rtsp://192.168.1.1:7070/webcam` in VLC

Check whether the M10 hardware actually has a **tilt servo**; a fixed camera
will never move regardless of packets.

## Run (interactive)

From the repo (with backend venv activated optional — script uses stdlib only):

```powershell
cd "C:\Users\marsh\Downloads\RC  UFO_1.9.3_APKPure"
python turbodrone\experimental\cooingdv\gl_tilt_probe.py
```

Focus the terminal and use:

| Key | Action |
|-----|--------|
| `0`–`8` | Select reserved byte Wi‑Fi index `9`–`17` |
| `+` / `-` or `[` / `]` | Cycle probe value for that byte |
| `c` | Clear selected reserved byte |
| `n` | Neutral — clear all reserved bytes and flags |
| `1` | Toggle current `flags1` probe bit |
| `2` | Toggle current `flags2` probe bit |
| `q` / `w` | Move `flags1` / `flags2` bit cursor |
| `f` / `g` | Clear `flags1` / `flags2` |
| `p` | Print current packet hex |
| `h` | Help |
| `Esc` | Quit |

Probe values cycled per byte: `00, 01, 02, 04, 08, 10, 20, 40, 80, FF`.

**What to look for:** camera pitch changes while sticks are neutral (`80` center).

When something works, note **exact byte index and value** (and whether flags were set).

## Run (automated sweep)

Hands-off walk through all reserved bytes and flag bits (~2.5 s per step).
Review the log and your video recording afterward.

```powershell
python turbodrone\experimental\cooingdv\gl_tilt_probe.py --auto-sweep --log-file sweep.log -v
```

Optional: shorter holds for a quick pass (less reliable to spot tilt):

```powershell
python turbodrone\experimental\cooingdv\gl_tilt_probe.py --auto-sweep --hold-seconds 1.5 --log-file sweep.log
```

## Packet reference

```text
03 66 14  B1  B2  ACC  TURN  F1  F2  [9..18 reserved]  CHK  99
```

- Checksum XORs only bytes **3–8** (axes + flags), not reserved bytes.
- Heartbeat `{01 01}` once per second (same as TurboDrone).
- Control rate default **20 Hz**.

## After a hit

1. Add findings to `turbodrone/docs/research/cooingdv.md`.
2. Wire into `cooingdv_rc_protocol_adapter.py` + model only after reproducing on hardware.
3. Enable `camera_tilt` in `web_server.py` capabilities for `cooingdv` if confirmed.

## If nothing moves

- **M10 (2026-05):** full auto-sweep (bytes 9–18 + flag bits + WiFi-UAV-style
  patterns) produced **no camera servo movement**. Some combos toggled LED
  solid/flashing (invalid-frame behavior). Documented in `docs/research/cooingdv.md`.
- Try the **stock RC UFO / KY UFO** app and look for any tilt UI; capture UDP
  `7099` with Wireshark while using it.
- Confirm GL variant (not TC) with `COOINGDV_VARIANT=gl` in TurboDrone `.env`.
- Hardware may have no servo — digital pan/zoom in the app is not mechanical tilt.

See also: `turbodrone/docs/research/cooingdv.md` (PTZ / servo section).
