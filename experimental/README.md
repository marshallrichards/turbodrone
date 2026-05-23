# Experimental
This directory contains early-stage support for drones that are not yet integrated into the main Turbodrone architecture.

Each subdirectory corresponds to a mobile app and contains control and video protocols.

## Drones and Apps

| App Name              | Supported Drones | Notes |
|-----------------------|------------------|-------|
| RC_UFO | E88 pro | PyQt5 app for flying it with a computer |
| CooingDV (`cooingdv/`) | M10, E88, E99, … | `gl_tilt_probe.py` — GL 21-byte packet probe for hidden camera tilt / servo |
| Macrochip S2x (`s2x/`) | S29, PL-515, S20, … | `s2x_tilt_probe.py` — HY bytes 8–17 + ST3 probe; `s2x_ptz_helper.py` — Ruko ST/PTZ commands + neutral HY stream |

### CooingDV GL tilt probe

See [`cooingdv/README.md`](cooingdv/README.md). Interactive and `--auto-sweep`
modes; not part of the main TurboDrone server.

### S2x HY / ST3 tilt probe

See [`s2x/README.md`](s2x/README.md). Tests the hypothesis that **bytes 8–17**
in `66 14 ... 99` are only zero in the app, plus optional **ST3** param sweeps
on UDP 8080. Best candidate hardware: **S29** (known servo per project README).
