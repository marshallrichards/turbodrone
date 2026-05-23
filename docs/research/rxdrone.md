# RxDrone Protocol Research

TurboDrone backend name: **`rxdrone`**

This note captures findings from the decompiled HF UFO Android app in
`decompiled-hfufo-1.5.2` (package `com.xaufohf.rxdrone`).

## App Identity

```text
package=com.xaufohf.rxdrone
versionName=1.5.2
versionCode=52
app_id_prefix=HFUFO_
main_activities:
  com.xaufohf.rxdrone.MainActivity
  com.xaufohf.rxdrone.ManualCtrlActivity
  com.xaufohf.rxdrone.HDManualCtrlActivity
```

## Relationship To Existing TurboDrone Backends

RxDrone is a **Jieli-family whitelabel** closely related to the stack documented in
`cooingdv.md` under `cooingdv_jieli`, but it is **not** a byte-for-byte match.

| Area | RxDrone (HF UFO 1.5.2) | `cooingdv_jieli` (KY FPV path) |
|------|------------------------|--------------------------------|
| SDK | `com.jieli.lib.dv.control`, `com.jieli.lib.stream` | Same |
| Video | RTP/JPEG on UDP `6666`, SDP TCP `6789`, stream socket `2224` | Same pattern |
| CTP JSON | `DeviceClient` / `SettingCmd` topics | Same envelope (`CTP:` + JSON) |
| Primary RC in manual UI | Hex `Protocol1` wrapped in CommandHub topic `0139` | `FLYING_CTRL` with `BYTE0..BYTE7` decimals |
| GPS / HD RC | Raw UDP stick packets via `UDPClientGPS` | Not used on KY FPV Jieli path |
| Default drone IP | `192.168.80.1` (HD), `192.168.8.1` (manual), `192.168.28.1` (Quanzhi) | `192.168.8.15` |

RxDrone should be treated as a **variant of the Jieli stack** with **extra raw-UDP RC
paths** and **CommandHub hex tunneling**, not as classic CooingDV RTSP/UDP
(`192.168.1.1:7099`) and not as `wifi_cam` native `8080`/`8090`.

TurboDrone's existing `cooingdv_jieli` adapter is the closest starting point for
**video** and for **DeviceClient CTP** commands, but RxDrone's main stick loop on
`ManualCtrlActivity` uses a different RC transport (see below). A dedicated
**`rxdrone`** backend should fork or wrap those pieces rather than alias
`cooingdv_jieli` blindly.

## Flight Screen Routing

`MainActivity.startBtnClick()` picks the control activity from the phone's Wi‑Fi IP:

```text
192.168.80.*  -> HDManualCtrlActivity  (type=1, PLANE_TYPE=0)
192.168.28.*  -> HDManualCtrlActivity  (type=2, Quanzhi / isQuanzhi)
192.168.8.1   -> ManualCtrlActivity    (type=0, Jieli CommandHub path)
other         -> HDManualCtrlActivity  (often offline)
```

Services:

- `ManualCtrlActivity` uses `com.xaufohf.service.CommunicationService`
  (`CommandHub` TCP + `UdpClientImpl` on UDP `2228`).
- `HDManualCtrlActivity` uses `com.xaufohf.service.hdservice.CommunicationService`
  (`ClientManager` / `DeviceClient` on TCP `3333` + `UDPClientGPS`).

## Video Feed

### Live preview (both flight activities)

Primary path is Jieli realtime stream:

1. `AVPlayer.createSocket(2224, …)` binds the local RT stream port
   (`ICommon.AP_RT_STREAM_PORT`).
2. App sends `CMD_RT_STREAM_OPEN` through `CommandHub` with resolution level args.
3. Device pushes RTP; app hosts a local SDP server so the player learns ports.

SDP server (`com.task.SDPServer`):

```text
TCP port: 6789 (IConstant.SDP_PORT)
Advertises:
  audio RTP/AVP 97 on UDP 1234 (L16/8000/1)
  video RTP/AVP 26 (JPEG) or 96 (H264) on UDP 6666
  framerate from device notify (default 30)
```

Constants (`com.fh.hdutil.IConstant`):

```text
RTP_VIDEO_PORT1 = 6666
RTP_AUDIO_PORT1 = 1234
RTS_UDP_PORT    = 2224
RTS_TCP_PORT    = 2223
RTS_TYPE_JPEG   = "0"
RTS_TYPE_H264   = "1"
```

`CommandHandler` starts `SDPServer` when the device notifies `OPEN_FRONT_RTS` /
`VIDEO_PARAM` / `PULL_VIDEO_PARAM`, caching width/height/format/fps/sample from
JSON topics.

Rendering:

- `ManualCtrlActivity`: `MjpegView` / `IjkVideoView` + `OnRTStreamListener`
  callbacks from `AVPlayer`.
- `HDManualCtrlActivity`: GLES `VideoTextureRenderer` / `BitmapSurfaceTexture`
  on a stream view.

### RTSP fallback

`IConstant.KEY_RTSP` and `STR_RTSP` exist; `DeviceDesc` exposes
`rtsp_forward_support` / `rtsp_behind_support`. The live path reviewed in code
centers on RTP/SDP above; RTSP is a secondary/device-dependent mode, not the
main loop used by `AVPlayer` in the reviewed flight screens.

### TurboDrone mapping (`rxdrone` video)

Reuse or extend `cooingdv_jieli_video_protocol.py` under the **`rxdrone`** name:

- Open stream via CTP (`OPEN_RT_STREAM` / CommandHub equivalent).
- Listen on UDP `6666` for JPEG RTP (and add H.264 if `format=1`).
- Run local SDP on TCP `6789`.

Drone IP is **not** fixed to `192.168.8.15`; bind to the gateway subnet the phone
uses (`192.168.80.1`, `192.168.8.1`, etc.).

## RC Controls

RxDrone implements **three stick encoders** and **three transports**.

### Stick encoders

**1. `Protocol1` — 13-byte GPS/drone packet** (`com.fh.util.Protocol1`)

```text
byte[0]  = 0x66   (102, head)
byte[1]  = ch1    (roll / yaw stick, scaled 0..255, center 128)
byte[2]  = ch2
byte[3]  = ch3    (throttle on HD path; axis remap on manual UI)
byte[4]  = ch4
byte[5]  = flag1  (mode bits: headless, stop, roll, one-key, light, calibrate, …)
byte[6]  = xor(flag1, ch1..ch4)
byte[7]  = 0x99   (-103, inner marker)
byte[8]  = data_l
byte[9]  = data_h
byte[10] = flag2  (follow, palm, speed, RTH, …)
byte[11] = xor(data_l, data_h, flag2)
byte[12] = 0xA5   (-91, tail)
```

**8-byte short form** (`packageOf8()`): `66 ch1 ch2 ch3 ch4 flag1 csum 99` —
same family as CooingDV TC `66 … 99` when `PROTOCOL_PLANE == 5`.

**2. `ProtocolOfQuanzhi` — 20-byte packet** (`com.fh.util.ProtocolOfQuanzhi`)

```text
66 14 ch1 ch2 ch3 ch4 flag1 flag2 distH distL xH xL yH yL res1 res2 res3 res4 csum 99
```

Used when `MainApplication.isQuanzhi` or `protocol_version` is `2` or `3`, or
device description `protocol_version == -1` on Quanzhi hardware (`192.168.28.x`).

**3. CommandHub wrapper — topic `0139` (`FlyCommand.CMD_NO_HEAD_MODE`)**

`ManualCtrlActivity` rc loop (~40 ms):

```java
mCommandHub.sendCommand("3", FlyCommand.CMD_NO_HEAD_MODE,
    toHex(protocol1.packaging()));  // or protocolHuiYuan.packaging()
```

Category `"3"` is `FlyCommand.CTP_ID_FLYING`. The parameter is a **hex string of
the raw 13- or 20-byte packet**, not decimal `BYTE0..BYTE7` fields.

`CommandHub` sends `DataForm` records over a **TCP socket** to the device
(CommandHub client port from stream SDK, typically device port `2222` on
`192.168.1.1` in `ICommon`, while RxDrone HD service uses `3333` for
`DeviceClient`).

### RC transports

| Mode | Activity | Transport | Target | Payload |
|------|----------|-----------|--------|---------|
| Manual / `192.168.8.1` | `ManualCtrlActivity` | `CommandHub` TCP | Device command port | Hex `Protocol1` / `ProtocolOfQuanzhi` via topic `0139` |
| HD / `192.168.80.x` | `HDManualCtrlActivity` | `UDPClientGPS` UDP | `192.168.80.1:3456` | Raw `packaging()` / `packageOf8()` bytes |
| HD + CTP | `HDManualCtrlActivity` | `DeviceClient` CTP | `deviceIp:3333` (AP_MODE_PORT) | Topic `FLIGHT_CONTROL`, param `DRONE_DATA` = hex packet |
| Quanzhi / `192.168.28.x` | `HDManualCtrlActivity` | `UDPClientGPS` UDP | `192.168.28.1:7080` | 20-byte `ProtocolOfQuanzhi` |

`UDPClientGPS` send thread copies `rockerBuf` unchanged into a UDP datagram every
`interval` ms (40 ms in HD rc loop).

`HDManualCtrlActivity.sendControlCmd()`:

```java
settingCmd.setTopic("FLIGHT_CONTROL");
settingCmd.setParams("DRONE_DATA", hex(protocol1.packaging()));
ClientManager.getClient().tryToPut(settingCmd, …);
```

Auxiliary CTP commands (headless, takeoff, track, wind, gyro, etc.) use
`FlyCommand` numeric topics (`0129`, `0130`, `0131`, …) via `CommandHub` or
`DeviceClient` depending on screen.

### Axis mapping (manual UI)

Rocker listeners write `Protocol1` channels; GPS broadcast can override:

```text
Channel1 <- left stick X
Channel2 <- left stick Y
Channel3 <- right stick Y   (swapped vs classic mode in some paths)
Channel4 <- right stick X
```

Speed modes adjust `speedPercent` (4.0 / 7.0 / 10.0) before channel scaling.

### TurboDrone mapping (`rxdrone` RC)

- **Video**: start from `cooingdv_jieli` video adapter; ship as `rxdrone` with
  configurable drone IP.
- **RC (HD / 192.168.80.x)**: `rxdrone` — raw UDP to port `3456` with
  `Protocol1` 13-byte builder; optional 8-byte when `protocol_version` implies it.
- **RC (manual / CommandHub)**: `rxdrone` — CommandHub `DataForm` + topic `0139`
  hex tunnel, or confirm with capture whether the device also accepts
  `FLYING_CTRL` on `2228` for the same firmware.
- **RC (Quanzhi)**: `rxdrone` — 20-byte encoder + UDP `7080`.
- Do **not** assume `192.168.1.1:7099` CooingDV short packet unless hardware
  exposes that subnet.

Suggested env / config knob when implemented: `DRONE_TYPE=rxdrone`.

## Camera Tilt / PTZ

### UI label "PTZ" = digital video pan, not gimbal

In both `ManualCtrlActivity` and `HDManualCtrlActivity`, the PTZ button toggles
`isShowPtz` and:

- Shows `tranRudder` (translated rudder overlay).
- Scales the **preview** (`setScaleOfIjk(2.0f)` or `TouchRenderHelper.setScale(3.0f)`).
- Pans by adjusting **texture pivot** (`setSelfPivot`) from rudder deltas.

No `Protocol1` flag, `FlyCommand` topic, or `UDPClientGPS` field is updated when
the user operates PTZ. **No servo/gimbal command path is wired to this control.**

### Device capability flags (unused for gimbal in reviewed code)

`dev_desc.txt` JSON may include:

```text
"PTZ": "0" | "1"   -> DeviceDesc.ptz_state (parsed, default true)
```

`GpsInfo.planePTZAdj` exists for telemetry from the flight controller UDP path,
but no Java setter was found in the decompiled sources; treat as **status-only**
unless a native/GPS parser assigns it.

`FlyCommand.CMD_CAMERA_CONTROL` (`0130`) exists in the command table but is not
part of the PTZ button handler.

### Conclusion for hardware tilt

- **App-level camera tilt (gimbal)**: **Not implemented** in the recovered UI →
  protocol path. The PTZ feature is **viewport pan/zoom** on the live texture.
- **Possible firmware PTZ**: `planePTZAdj` and `DEV_PTZ_MODE` hint that some
  airframes may support it via GPS binary or undisclosed commands; needs packet
  capture on target hardware.

## Network Constants (quick reference)

```text
# HD / default drone
DEFAULT_DEV_IP     = 192.168.80.1
GPS_UDP_PORT       = 3456

# Quanzhi
DEFAULT_DEV_IP_Q   = 192.168.28.1
GPS_UDP_PORT_Q     = 7080

# Manual / stream SDK defaults
INSIDE_FTP / manual gateway = 192.168.8.1
AP_MODE_PORT (DeviceClient) = 3333
AP_MODE_UDP_PORT            = 2228
CommandHub / RTS            = 2224 (UDP), 2222 (TCP per ICommon.AP_MODE_DEVICE_PORT)

# RTP / SDP
SDP 6789, video 6666, audio 1234
```

## Implementation Notes

1. Read `protocol_version` from `dev_desc.txt` (`MainApplication.PROTOCOL_PLANE`)
   to choose 8-byte vs 13-byte vs 20-byte stick encoding.
2. Prefer hardware capture per IP family (`80.x` vs `8.1` vs `28.x`) before
   merging into `cooingdv_jieli`; RxDrone's `0139` hex tunnel may differ from
   `FLYING_CTRL` decimal bytes on the same chipset.
3. For TurboDrone UI, do not expose "camera tilt" unless implementing either the
   digital pan feature (client-side only) or a confirmed gimbal command from
   capture.

## See Also

- `docs/research/cooingdv.md` — Jieli/`cooingdv_jieli` family and CTP envelope
- `docs/research/wifi_cam.md` — explains false-positive Jieli constant overlap
- `turbodrone/backend/protocols/cooingdv_jieli_*` — first-pass Jieli adapters
  to fork for `rxdrone` video
