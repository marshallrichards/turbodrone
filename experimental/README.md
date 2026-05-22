# Experimental
This directory contains early-stage support for drones that are not yet integrated into the main Turbodrone architecture.

Each subdirectory corresponds to a mobile app and contains control and video protocols.

## Drones and Apps

| App Name              | Supported Drones | Notes |
|-----------------------|------------------|-------|
| RC_UFO | E88 pro | PyQt5 app for flying it with a computer |
| CooingDV (`cooingdv/`) | M10, E88, E99, … | `gl_tilt_probe.py` — GL 21-byte packet probe for hidden camera tilt / servo |

### CooingDV GL tilt probe

See [`cooingdv/README.md`](cooingdv/README.md). Interactive and `--auto-sweep`
modes; not part of the main TurboDrone server.
