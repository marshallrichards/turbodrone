# CooingDV Protocol Research

This note documents the CooingDV-style drone protocol as implemented in
TurboDrone and as observed in the decompiled KY UFO and RC UFO Android apps.
The publisher/app family appears to reuse the same core control and video stack
across cosmetically different drone apps.

Primary evidence:

- TurboDrone implementation:
  - `turbodrone/backend/models/cooingdv_rc.py`
  - `turbodrone/backend/protocols/cooingdv_rc_protocol_adapter.py`
  - `turbodrone/backend/models/cooingdv_video_model.py`
  - `turbodrone/backend/protocols/cooingdv_video_protocol.py`
  - `turbodrone/backend/main.py`
  - `turbodrone/backend/web_server.py`
  - `turbodrone/backend/services/flight_controller.py`
  - `turbodrone/backend/services/video_receiver.py`
- Decompiled KY UFO app:
  - `decompiled-ky-ufo-1.5.8/sources/com/cooingdv/kyufo/socket/Config.java`
  - `decompiled-ky-ufo-1.5.8/sources/com/cooingdv/kyufo/socket/SocketClient.java`
  - `decompiled-ky-ufo-1.5.8/sources/com/cooingdv/kyufo/socket/UdpComm.java`
  - `decompiled-ky-ufo-1.5.8/sources/com/cooingdv/kyufo/tools/FlyController.java`
  - `decompiled-ky-ufo-1.5.8/sources/com/cooingdv/kyufo/fragment/DeviceBLFragment.java`
  - `decompiled-ky-ufo-1.5.8/sources/com/cooingdv/kyufo/fragment/DeviceGLFragment.java`
  - `decompiled-ky-ufo-1.5.8/sources/com/cooingdv/kyufo/thread/MjpegThread.java`
  - `decompiled-ky-ufo-1.5.8/sources/com/cooingdv/kyufo/models/VideoModel.java`
  - `decompiled-ky-ufo-1.5.8/sources/com/cooingdv/bl60xmjpeg/UAV.java`
  - `decompiled-ky-ufo-1.5.8/sources/com/cooingdv/bl60xmjpeg/utils/GLJni.java`
  - `decompiled-ky-ufo-1.5.8/sources/com/cooingdv/bl60xmjpeg/utils/TCJni.java`
- Decompiled RC UFO app:
  - `decompiled-rc-uf-19.3/sources/com/cooingdv/rcufo/socket/Config.java`
  - `decompiled-rc-uf-19.3/sources/com/cooingdv/rcufo/socket/SocketClient.java`
  - `decompiled-rc-uf-19.3/sources/com/cooingdv/rcufo/socket/UdpComm.java`
  - `decompiled-rc-uf-19.3/sources/com/cooingdv/rcufo/tools/FlyController.java`
  - `decompiled-rc-uf-19.3/sources/com/cooingdv/rcufo/fragment/DeviceBLFragment.java`
  - `decompiled-rc-uf-19.3/sources/com/cooingdv/rcufo/thread/MjpegThread.java`
  - `decompiled-rc-uf-19.3/sources/com/cooingdv/rcufo/models/VideoModel.java`
  - `decompiled-rc-uf-19.3/sources/com/cooingdv/rcufo/dialog/EnterPasswordDialog.java`
  - `decompiled-rc-uf-19.3/sources/com/cooingdv/rcufo/utils/WifiIdUtils.java`
- Decompiled RC FPV app:
  - `decompiled-rc-fpv-1.8.0/sources/com/cooingdv/rcfpv/socket/Config.java`
  - `decompiled-rc-fpv-1.8.0/sources/com/cooingdv/rcfpv/socket/SocketClient.java`
  - `decompiled-rc-fpv-1.8.0/sources/com/cooingdv/rcfpv/socket/UdpComm.java`
  - `decompiled-rc-fpv-1.8.0/sources/com/cooingdv/rcfpv/tools/FlyController.java`
  - `decompiled-rc-fpv-1.8.0/sources/com/cooingdv/bl60xmjpeg/UAV.java`
  - `decompiled-rc-fpv-1.8.0/sources/com/cooingdv/rcfpv/utils/WifiIdUtils.java`
- Decompiled KY FPV app:
  - `decompiled-ky-fpv-2.0.0/sources/com/cooingdv/kyfpv/socket/Config.java`
  - `decompiled-ky-fpv-2.0.0/sources/com/cooingdv/kyfpv/socket/UdpComm.java`
  - `decompiled-ky-fpv-2.0.0/sources/com/cooingdv/kyfpv/fragment/DeviceTXFragment.java`
  - `decompiled-ky-fpv-2.0.0/sources/com/cooingdv/kyfpv/tools/FlyController.java`
  - `decompiled-ky-fpv-2.0.0/sources/com/cooingdv/kyfpv/utils/StreamClient.java`
  - `decompiled-ky-fpv-2.0.0/sources/com/cooingdv/kyfpv/utils/FlyCommandUtils.java`
  - `decompiled-ky-fpv-2.0.0/sources/com/cooingdv/kyfpv/tools/FlyCommand.java`
  - `decompiled-ky-fpv-2.0.0/sources/com/cooingdv/kyfpv/utils/WifiIdUtils.java`
- Decompiled 4DRC FPV app:
  - `decompiled-4drc-fpv-1.6.0/sources/com/cooingdv/fpv4drc/socket/Config.java`
  - `decompiled-4drc-fpv-1.6.0/sources/com/cooingdv/fpv4drc/socket/SocketClient.java`
  - `decompiled-4drc-fpv-1.6.0/sources/com/cooingdv/fpv4drc/tools/FlyController.java`
  - `decompiled-4drc-fpv-1.6.0/sources/com/cooingdv/fpv4drc/tools/DriveController.java`
  - `decompiled-4drc-fpv-1.6.0/sources/com/cooingdv/fpv4drc/fragment/ExcavatorFragment.java`
  - `decompiled-4drc-fpv-1.6.0/sources/com/cooingdv/fpv4drc/utils/WifiIdUtils.java`

## Executive Summary

CooingDV drones in these apps use a simple Wi-Fi control plane:

- Drone IP: `192.168.1.1`
- RC/command UDP port: `7099`
- Preview video: `rtsp://192.168.1.1:7070/webcam`
- HTTP media access: `http://192.168.1.1/PHOTO/...` and
  `http://192.168.1.1/DCIM/...`
- FTP media root: `/0/`, username `ftp`, password `ftp`

The RC loop is a 20 Hz loop in the Android apps: `FlyController` schedules a
`TimerTask` every 50 ms. TurboDrone mirrors that by defaulting CooingDV control
to 20 Hz.

There are two Wi-Fi control packet families:

- TC / short packets: 9 bytes total over UDP.
- GL / extended packets: 21 bytes total over UDP.

Both packet families are wrapped with a leading `0x03` byte before being sent
over UDP. KY UFO also has a native/BLE-like path through `UAV`, `GLJni`, and
`TCJni` where the same inner payloads are sent without the Wi-Fi wrapper.

The video path in the Wi-Fi app mode is RTSP. The apps use an IJK-based video
view configured to expose original video frames as `byte[]`, then decode those
bytes with `BitmapFactory.decodeByteArray`, which strongly indicates JPEG/MJPEG
frame blobs at the app boundary. The apps can also re-encode displayed frames to
local H.264 MP4 for recording. That local H.264 encoder is not evidence that the
drone's wire stream itself is H.264.

## TurboDrone Compatibility Summary

TurboDrone's current `cooingdv` implementation is a good match for drones that
expose the classic CooingDV Wi-Fi path:

- RC/telemetry on UDP `192.168.1.1:7099`
- Video on `rtsp://192.168.1.1:7070/webcam`
- 20 Hz stick loop
- TC short packet `03 66 ... 99`
- GL extended packet `03 66 14 ... 99`
- Heartbeat `01 01`
- Exit-control command `08 01`

Compatibility by reviewed app:

| Reviewed app | Current TurboDrone fit | Notes / edge cases |
| --- | --- | --- |
| KY UFO `com.cooingdv.kyufo` | Strong for classic Wi-Fi TC/GL; partial for native BL60x path | The Java Wi-Fi path matches UDP `7099` and RTSP `7070`. KY UFO also has native `UAV` / `libuav_gl.so` / `libuav_tc.so` transport targeting `192.168.169.1:8800`; TurboDrone does not implement that native path yet. |
| RC UFO `com.cooingdv.rcufo` | Strong for classic Wi-Fi TC/GL | This is closest to TurboDrone's current adapter: UDP `7099`, RTSP `7070`, TC/GL auto-detection, password-capable IDs, and GL status telemetry. Some decompiled methods are damaged, so runtime captures are still useful. |
| RC FPV `com.cooingdv.rcfpv` | Good for classic TC/short Wi-Fi path | RC FPV uses the same RTSP/UDP constants and short `03 66 ... 99` packet. Its Java `FlyController` does not show the GL 21-byte branch; treat it as TC/short unless telemetry proves otherwise. It references `UAV` native bridges, but this decompile lacks bundled `.so` files. |
| KY FPV `com.cooingdv.kyfpv` | Good only for its classic `DeviceTXFragment` path; not complete for all KY FPV backends | KY FPV includes a TurboDrone-compatible RTSP/UDP TC path, but also has native `StreamClient` / `mjpeg_jni` and Jieli `DeviceClient` JSON `FLYING_CTRL` backends. TurboDrone does not currently implement those non-classic backends. |
| 4DRC FPV `com.cooingdv.fpv4drc` | Strong for classic Wi-Fi TC/GL drone path; separate for excavator/drive mode | Drone flight control uses the same TC/GL split as KY UFO, with UDP `7099`, RTSP `7070`, and optional BL60x native `UAV`. It also adds `EXCAVATOR_720 = 89` and a distinct drive/excavator packet `03 33 ... 88`, which is not covered by TurboDrone's flight controller. |

Control expectations for compatible classic-path drones:

- Video should generally work via RTSP `7070`.
- Manual stick control should generally work via UDP `7099`.
- Emergency stop should generally work through the TC/GL emergency flag mapping.
- Takeoff and land are best understood as TurboDrone UI abstractions over the
  apps' fast-up / fast-down one-shot bits. The reviewed apps do not expose clear
  named Android `takeoff` / `land` wire opcodes for the classic UDP path.

Practical rule: if a drone works in one of these apps while exposing
`192.168.1.1:7070` RTSP and responding on UDP `7099`, TurboDrone's current
`cooingdv` adapter is likely the correct first attempt. If the app is using KY
FPV's `mjpeg_jni`, Jieli JSON, or KY UFO's native `192.168.169.1:8800` path
exclusively, TurboDrone needs a separate backend before compatibility can be
claimed.

Likely future TurboDrone split:

- `cooingdv`: current classic RTSP/UDP implementation.
- `cooingdv_bl`: BL60x native MJPEG/control transport used by KY UFO `UAV` and
  KY FPV `StreamClient`, both centered on `192.168.169.1:8800`.
- `cooingdv_jieli`: KY FPV Jieli/CTP backend using `192.168.8.15:2228`,
  `DeviceClient`, `FLYING_CTRL`, and `CTP:` JSON packets.
- `rxdrone`: RxDrone / HF UFO Jieli video plus `Protocol1` RC (`0139` hex tunnel,
  GPS UDP `3456`, `FLIGHT_CONTROL` / `DRONE_DATA`). See `docs/research/rxdrone.md`.
- `cooingdv_drive` or `cooingdv_4drc_drive`: optional future non-drone backend
  for the 4DRC excavator/ground-vehicle path. This should stay separate from
  flight because its packet shape and controls are not quadcopter RC controls.

Implementation status in TurboDrone:

- `cooingdv` is implemented for classic RTSP/UDP.
- `cooingdv_jieli` has an initial RC implementation for `CTP:`/`FLYING_CTRL`
  over UDP `2228` and a first-pass RTP/JPEG video adapter using SDP `6789` and
  RTP video port `6666`.
- `cooingdv_bl` remains research-only until runtime captures confirm the safe
  ACK/session behavior needed for motor control.
- `cooingdv_drive` is not implemented and is out of scope for flight support.

### RxDrone (`rxdrone`) — HF UFO 1.5.2

The decompiled HF UFO app (`decompiled-hfufo-1.5.2`, package
`com.xaufohf.rxdrone`) shares the same Jieli video stack (RTP `6666`, SDP `6789`,
`AVPlayer` on UDP `2224`, `DeviceClient` CTP) documented above, but its **main RC
paths differ** from KY FPV's `FLYING_CTRL` decimal backend:

- `ManualCtrlActivity` (gateway `192.168.8.1`) tunnels hex-encoded `Protocol1`
  (13-byte `66 … 99 … A5`) or 20-byte Quanzhi packets through `CommandHub` topic
  `0139` (`CMD_NO_HEAD_MODE`), not `FLYING_CTRL` `BYTE0..BYTE7`.
- `HDManualCtrlActivity` (`192.168.80.x`) sends the same raw packets on
  `UDPClientGPS` to `192.168.80.1:3456`, and can also wrap them in CTP topic
  `FLIGHT_CONTROL` / `DRONE_DATA` via `DeviceClient` on TCP `3333`.

Planned TurboDrone backend name: **`rxdrone`**. Full mapping (video, RC, PTZ):
`docs/research/rxdrone.md`. Reuse Jieli **video** from `cooingdv_jieli`; implement
RC as a separate **`rxdrone`** adapter after capture on the target IP family.

## Network Constants

The two apps share the same network constants in `Config.java`.

- `SERVER_IP = "192.168.1.1"`
- `SERVER_PORT = 7070`
- `PREVIEW_ADDRESS = "rtsp://192.168.1.1:7070/webcam"`
- `TCP_SERVER_HOST = "192.168.1.1"`
- `TCP_SERVER_PORT = 5000`
- `FTP_HOST = "192.168.1.1"`
- `FTP_USERNAME = "ftp"`
- `FTP_PASSWORD = "ftp"`
- `FTP_ROOT_DIR = "/0/"`
- `VIDEO_PATH = "DCIM"`
- `IMAGE_PATH = "PHOTO"`
- `LOCAL_IMAGE_SUFFIX = ".jpg"`
- `LOCAL_VIDEO_SUFFIX = ".avi"`
- `REMOTE_IMAGE_SUFFIX = ".jpg"`
- `REMOTE_VIDEO_SUFFIX = ".avi"`

The Java code inspected does not use `TCP_SERVER_PORT = 5000` for flight
control. Active RC, heartbeat, camera switch, gallery sync, and password
commands all go through `UdpComm` to UDP port `7099`.

The newer KY FPV app still carries these constants for one of its RTSP/UDP
screens, but it also supports other backends through `StreamClient` and
`DeviceClient`; see "Additional CooingDV Publisher Apps" below.

## UDP Session Lifecycle

Both apps create their UDP client like this:

```text
UdpComm.getInstance("192.168.1.1", 7099)
```

`UdpComm` uses `new DatagramSocket()` with no explicit local bind, so Android
uses an ephemeral local port. The same socket is used for transmit and receive.

The receive thread allocates a 20-byte buffer:

```text
byte[] bArr = new byte[20]
DatagramPacket(bArr, bArr.length)
socket.receive(datagramPacket)
callback.onReceiveData(copyOf(datagramPacket.getData(), datagramPacket.getLength()))
```

That means telemetry observed by the Java callback is limited to 20 bytes in
these app builds. This is enough for the app's first-byte capability detection,
camera reset state, gallery counters, password metadata, and small GL status
frames.

The apps send a heartbeat every 1000 ms:

```text
01 01
```

When leaving flight-control mode, the Wi-Fi path sends:

```text
08 01
```

Important: this is not a startup init packet. In both apps it is sent when the
control timer is cancelled. KY sends native command `65` (`0x65`, decimal 101)
instead when its `UAV` native path is active.

## Discrete UDP Commands

Observed discrete commands on UDP port `7099`:

- `01 01`: heartbeat, once per second while preview/control is active.
- `08 01`: leave flight-control mode / stop controller timer.
- `06 01`: select one camera, usually front/default.
- `06 02`: select alternate camera, usually rear/secondary.
- `09 01`: screen/gallery/photo-side synchronization. Used by KY `switchScreen`
  and by both apps after photo telemetry (`M`, `0x4d`).
- `09 02`: screen/gallery/video-side synchronization. Used by KY `switchScreen`
  and by both apps after video telemetry (`X`, `0x58`).
- `0a d0 d1 d2 d3 d4 d5 d6 d7`: RC UFO password set command, where each `dN`
  is a numeric byte parsed from one character of an 8-digit UI password.

KY native-only commands through `UAV.sendCommand`:

- `64` (`0x64`, decimal 100): sent after first native `picData` frame to
  acknowledge/activate native streaming.
- `63` (`0x63`, decimal 99): sent after native resolution/capability messages.
- `65` (`0x65`, decimal 101): sent when leaving control mode while `UAV` is
  active.

## Flight Control Axes

The Android apps name the four stick bytes as:

- `controlByte1`
- `controlByte2`
- `controlAccelerator`
- `controlTurn`

The values use byte-centered joystick semantics:

- Default center: `128`
- Minimum: `1`
- Maximum: `255`
- If `controlAccelerator == 1`, the app writes it as `0` before sending.

TurboDrone maps these into the higher-level model fields:

- `roll` -> `controlByte1`
- `pitch` -> `controlByte2`
- `throttle` -> `controlAccelerator`
- `yaw` -> `controlTurn`

`CooingdvRcModel` defines a safe control range of `50..200` centered at `128`.
The protocol adapter performs a final byte clamp to `1..255`, matching the app
frame builder. This separation is intentional: the model limits normal control
motion, while the adapter preserves protocol validity.

## TC / Short Flight Packet

The TC path is used when the app's device type is `10`.

Native inner payload in KY `UAV` mode:

```text
66 B1 B2 ACC TURN FLAGS CHECKSUM 99
```

Wi-Fi UDP payload:

```text
03 66 B1 B2 ACC TURN FLAGS CHECKSUM 99
```

Total Wi-Fi length: 9 bytes.

Byte layout:

- Byte 0: `0x03`, Wi-Fi wrapper/prefix.
- Byte 1: `0x66`, start marker.
- Byte 2: `controlByte1`.
- Byte 3: `controlByte2`.
- Byte 4: `controlAccelerator`, except app coerces `1` to `0`.
- Byte 5: `controlTurn`.
- Byte 6: flags.
- Byte 7: XOR checksum.
- Byte 8: `0x99`, end marker.

Checksum:

```text
checksum = B1 ^ B2 ^ ACC ^ TURN ^ FLAGS
```

The Android app's TC flag byte is:

- Bit `0x01`: `isFastFly`
- Bit `0x02`: `isFastDrop`
- Bit `0x04`: `isEmergencyStop`
- Bit `0x08`: `isCircleTurnEnd`
- Bit `0x10`: `isNoHeadMode`
- Bit `0x20`: `isFastReturn || isUnLock`
- Bit `0x40`: KY `isOpenLight`; RC source is damaged here and has no
  `isOpenLight` field.
- Bit `0x80`: `isGyroCorrection`

TurboDrone's TC flag names are higher-level names:

- `0x01`: `takeoff_flag`
- `0x02`: `land_flag`
- `0x04`: `stop_flag`
- `0x08`: `flip_flag`
- `0x10`: `headless_flag`
- `0x80`: `calibration_flag`

The TurboDrone mapping matches the byte positions and the most plausible
button-level effects, but the decompiled app does not name explicit
`takeoff`/`land` opcodes. The app names the low two bits as one-shot
fast-up/fast-down actions. Treat TurboDrone's `takeoff` and `land` semantics as
an abstraction over those app buttons, not as literal Android symbol names.

## GL / Extended Flight Packet

The GL path is used when the app's device type is not `10`, normally device type
`2`.

Native inner payload in KY `UAV` mode:

```text
66 14 B1 B2 ACC TURN FLAGS1 FLAGS2 00 00 00 00 00 00 00 00 00 00 CHECKSUM 99
```

Wi-Fi UDP payload:

```text
03 66 14 B1 B2 ACC TURN FLAGS1 FLAGS2 00 00 00 00 00 00 00 00 00 00 CHECKSUM 99
```

Total Wi-Fi length: 21 bytes.

Byte layout:

- Byte 0: `0x03`, Wi-Fi wrapper/prefix.
- Byte 1: `0x66`, start marker.
- Byte 2: `0x14`, decimal 20, extended payload marker/inner length.
- Byte 3: `controlByte1`.
- Byte 4: `controlByte2`.
- Byte 5: `controlAccelerator`, except app coerces `1` to `0`.
- Byte 6: `controlTurn`.
- Byte 7: `flags1`.
- Byte 8: `flags2`.
- Bytes 9..18: reserved zero bytes in the generated app frames, except byte 19
  below is checksum when using zero-based Wi-Fi indexing.
- Byte 19: XOR checksum.
- Byte 20: `0x99`, end marker.

Checksum:

```text
checksum = B1 ^ B2 ^ ACC ^ TURN ^ FLAGS1 ^ FLAGS2
```

The Android app's GL `flags1` byte is:

- Bit `0x01`: `isFastFly || isFastDrop`
- Bit `0x02`: `isEmergencyStop`
- Bit `0x04`: `isGyroCorrection`
- Bit `0x08`: `isCircleTurnEnd`
- Bit `0x10`: KY `isOpenLight`; absent in RC `FlyController`.
- Bit `0x40`: `isGestureMode`

The Android app's GL `flags2` byte is:

- Bit `0x01`: `isNoHeadMode`
- Bit `0x02`: `isFixedHeightMode`

TurboDrone's GL mapping:

- `takeoff_flag` or `land_flag` -> `flags1 0x01`
- `stop_flag` -> `flags1 0x02`
- `calibration_flag` -> `flags1 0x04`
- `flip_flag` -> `flags1 0x08`
- `headless_flag` -> `flags2 0x01`

Again, TurboDrone's names represent the product-level control surface. The
decompiled apps expose these bits as fast up/down, emergency, gyro, circle/flip,
headless, and fixed-height style features.

## Variant Detection

The apps infer TC versus GL behavior from UDP telemetry/capability bytes.

KY `WifiIdUtils.isGL(i)`:

```text
90..101, 103
```

KY `WifiIdUtils.isNoGL(i)`:

```text
5, 9, 12, 19, 20, 21, 23, 24, 31, 45, 51, 63, 64, 65, 66, 67, 72
```

RC `WifiIdUtils.isGL(i)`:

```text
90..101, 103, 82, 85
```

RC password-capable IDs:

```text
80, 81, 82, 85
```

RC adds many KY aliases plus RC-specific resolution IDs:

```text
26, 27, 29, 30, 31, 41, 43, 44, 45, 68, 69, 70, 71, 72,
80, 81, 82, 83, 84, 85, 86, 87, 90..101, 103, 105
```

TurboDrone mirrors this detection through the first byte of received UDP
telemetry:

- IDs in `GL_RESOLUTION_IDS` select GL.
- IDs in `KNOWN_RESOLUTION_IDS` select TC unless they also match GL.
- Until a known ID is received, TurboDrone falls back to TC.
- `COOINGDV_VARIANT=tc` or `COOINGDV_VARIANT=gl` can force a variant.
- Aliases accepted by TurboDrone:
  - TC: `tc`, `e88`, `short`
  - GL: `gl`, `flow`, `extended`
  - Auto: empty, `auto`, `detect`, `autodetect`

## Additional CooingDV Publisher Apps

Two later decompiles broaden the CooingDV publisher picture:

- `RC FPV 1.8.0` package: `com.cooingdv.rcfpv`
- `KY FPV 2.0.0` package: `com.cooingdv.kyfpv`

Both are recognizably from the same publisher family, but they do not map
one-to-one onto the same runtime stack.

### RC FPV 1.8.0

RC FPV is closest to the original KY UFO / RC UFO implementation.

Shared constants and paths:

- `Config.PREVIEW_ADDRESS = "rtsp://192.168.1.1:7070/webcam"`
- `SERVER_IP = "192.168.1.1"`
- `SERVER_PORT = 7070`
- `TCP_SERVER_PORT = 5000` defined but not used for RC in the inspected Java
  paths.
- `UdpComm.getInstance("192.168.1.1", 7099)`
- `UdpComm` uses the same `DatagramSocket()` send/receive model and 20-byte
  receive buffer.
- Heartbeat is `01 01` every 1000 ms.
- Camera switch uses `06 01` / `06 02`.
- Photo/video gallery sync uses `09 01` / `09 02`.
- Exit control mode uses `08 01` when not in native `UAV` mode.

RC FPV includes the same Java native bridge package:

- `com.cooingdv.bl60xmjpeg.UAV`
- `GLJni` -> `System.loadLibrary("uav_gl")`
- `TCJni` -> `System.loadLibrary("uav_tc")`

However, the inspected `decompiled-rc-fpv-1.8.0/resources` tree has no
`resources/lib` directory. Like RC UFO, this decompile either lacks the native
split/universal APK libs or represents a packaging variant where those binaries
were omitted from the extracted resource tree.

RC FPV's `FlyController` builds only the TC/short inner packet:

```text
66 B1 B2 ACC TURN FLAGS CHECKSUM 99
```

Wi-Fi mode prefixes that with `0x03`:

```text
03 66 B1 B2 ACC TURN FLAGS CHECKSUM 99
```

Native `UAV` mode sends the inner 8-byte payload directly.

RC FPV does not show the GL 20-byte packet branch in its `FlyController`. It is
therefore best modeled as a TC/short CooingDV variant, with optional native
`UAV` support if its missing native libraries are recovered.

RC FPV flag bits match the TC-style family:

- `0x01`: fast fly / up
- `0x02`: fast drop / down
- `0x04`: emergency stop
- `0x08`: circle turn end / flip-like one-shot
- `0x10`: no-head / headless
- `0x20`: fast return or unlock
- `0x80`: gyro correction

Two details differ from the older RC UFO source:

- `controlTurn` is dead-zoned to 128 when it falls between 104 and 152.
- The decompiled fast-return/unlock branch is cleaner than RC UFO's damaged
  output: `0x20` is set when `isFastReturn` or `isUnLock` is true.

RC FPV `WifiIdUtils` is narrower than RC UFO:

- Adds `COVERT_8K = 33`
- Adds `RESOLUTION_SETTING = 46`
- Double-camera IDs: `41`, `43`, `44`
- Password-capable IDs still include `80`, `81`, `82`, `85` constants, but no
  `EnterPasswordDialog` equivalent was observed in the same way as RC UFO.
- No GL/flow ID table was observed in this `WifiIdUtils`; it is not doing the
  same GL-vs-TC selection as RC UFO.

### KY FPV 2.0.0

KY FPV 2.0.0 is broader than the UFO apps and carries at least three control
families behind one publisher UI.

1. Native BL/MJPEG `StreamClient`

`StreamClient` loads:

```text
System.loadLibrary("mjpeg_jni")
```

Native methods:

- `streamStartServer()`
- `streamStopServer()`
- `streamSendCommand(byte[] command, int channel)`
- `streamSwitchCamera(int index)`
- `streamSetModify(String ssid, int resolution, int channel, int camera)`

Callbacks:

- `functionPicture(byte[], long, byte)` marks the stream active, sends native
  command `64` (`0x64`, decimal 100) once, and forwards frame bytes to
  `OnStreamListener.onVideo`.
- `functionMessage(int)` handles resolution/status values, broadcasts fake
  resolution changes, applies model-specific UI customization, and forwards the
  integer to `OnStreamListener.onReceiver`.

`FlyController` type `1` sends the same short TC inner packet through
`StreamClient.sendCommand(...)`:

```text
66 B1 B2 ACC TURN FLAGS CHECKSUM 99
```

It also sends native command `65` (`0x65`, decimal 101) when leaving control
mode, matching the older `UAV` native exit behavior.

The native split APK for KY FPV contains `libmjpeg_jni.so` under
`resources/config.armeabi_v7a.apk/lib/armeabi-v7a`. Ghidra and ELF inspection
show it is the same protocol family as the KY UFO `libuav_tc.so` engine, but
with a different Java wrapper:

- Java class: `com.cooingdv.kyfpv.utils.StreamClient`
- JNI library: `libmjpeg_jni.so`
- Native target: `192.168.169.1:8800`
- Local socket: UDP bound to `0.0.0.0` with an ephemeral local port
- Start packet: `ef 00 04 00`
- Incoming envelope marker: `0x93`
- Native frame assembly: 1024-byte fragments, embedded `640x360` JPEG headers,
  quality tables for 5/10/25/50/75/100, and final JPEG EOI `ff d9`
- Native callbacks:
  - `functionPicture(byte[], long, byte)`
  - `functionMessage(int)`

Important Ghidra-confirmed functions:

- `Java_com_cooingdv_kyfpv_utils_StreamClient_streamStartServer`
- `Java_com_cooingdv_kyfpv_utils_StreamClient_streamStopServer`
- `Java_com_cooingdv_kyfpv_utils_StreamClient_streamSendCommand`
- `Java_com_cooingdv_kyfpv_utils_StreamClient_streamSwitchCamera`
- `Java_com_cooingdv_kyfpv_utils_StreamClient_streamSetModify`
- `mjpeg_ndk_command_send`
- `mjpeg_ndk_settings_send`
- `mjpeg_ndk_queryinfo_cmd_send`
- `handle_mcu_msg_frag`
- `handle_mcu_msg_ack`
- `build_send_ack`

`streamSendCommand(byte[], int)` copies the Java command bytes and calls
`mjpeg_ndk_command_send`. That native command path accepts payloads shorter than
`0x81`, stores command length plus a `length + 0x0c` field, and piggybacks the
command into the native ACK/control stream. This is not the Java UDP `7099`
transport; it should be treated as a separate BL60x native backend even though
the 8-byte stick payload is familiar.

`streamSetModify(...)` builds the same `oGMcOfyZdIurm2kS` settings payload
family seen in the KY UFO native code, with a mode value of `2` for this
StreamClient path.

2. Jieli / JSON `DeviceClient`

KY FPV adds `com.jieli.lib.dv.control.DeviceClient` through `ClientManager`.
This is a materially different backend from the raw UDP packet path.

KY FPV constructs `new DeviceClient(context, 1)`, selecting the UDP
implementation. The app connects to:

```text
192.168.8.15:2228
```

from `IConstants.DEFAULT_DEV_IP` and `AP_MODE_UDP_PORT`.

The Jieli command envelope is not the CooingDV `0x03 0x66` packet. It is a
little-endian CTP envelope:

```text
offset  size  meaning
0x00    4     ASCII "CTP:"
0x04    2     little-endian topic length
0x06    N     topic string
...     4     little-endian JSON payload length
...     M     JSON payload
```

The JSON payload looks like:

```json
{"op":"PUT","param":{"state":"1"}}
```

or, for flight controls:

```json
{
  "op": "PUT",
  "param": {
    "BYTE0": "102",
    "BYTE1": "...",
    "BYTE2": "...",
    "BYTE3": "...",
    "BYTE4": "...",
    "BYTE5": "...",
    "BYTE6": "...",
    "BYTE7": "153"
  }
}
```

`FlyCommandUtils.tryToSendFlyCommand(int[])` sends a `SettingCmd` topic
`FLYING_CTRL` with parameters:

```text
BYTE0=102
BYTE1=B1
BYTE2=B2
BYTE3=ACC
BYTE4=TURN
BYTE5=FLAGS
BYTE6=CHECKSUM
BYTE7=153
```

`FlyController` type `2` uses this JSON backend. The same 8-byte TC control
payload is preserved, but it is transported as named JSON settings rather than
as a raw UDP datagram.

Other JSON command topics in `FlyCommand` include:

- `CONTROL_MODE`
- `FLYING_CTRL`
- `SWITCH_CAMERA`
- `RT_PIC_POSITION_CTL`
- `REQUEST_FAKE_NUMBER`
- numeric legacy topics such as `0136`, `0138`, `0141`, `0142`, `0143`,
  `0144`, `0145`, `0146`, `0147`

This strongly suggests that newer CooingDV apps support at least one chipset/app
backend that is not covered by TurboDrone's current raw UDP/RTSP CooingDV
adapter.

3. Classic RTSP/UDP `DeviceTXFragment`

KY FPV still includes a classic RTSP/UDP path:

- RTSP preview: `rtsp://192.168.1.1:7070/webcam`
- UDP telemetry/control: `192.168.1.1:7099`
- Heartbeat: `01 01`
- Exit control: `08 01`
- Photo/video notifications: `M` / `X`, with `09 01` / `09 02` responses
- `OnReceivedOriginalDataListener` -> `MjpegThread.drawBitmap(byte[])`

`FlyController` type `3` delegates raw 8-byte TC inner frames back to
`DeviceTXFragment.sendFlyControllerData`, which prefixes `0x03` and sends the
result by `UdpComm`.

KY FPV therefore preserves the TurboDrone-compatible TC/short path, but it also
contains non-TurboDrone backends.

KY FPV `WifiIdUtils` has the broadest observed model table so far. Notable
additional IDs and model families:

- FPV IDs: `25`, `26`, `27`, `29`, `30`
- DF FPV: `14`, `50`
- E19 Eachine: `10`
- Hasakee Q8: `62`
- Qixin Toy: `34`
- XKY 4K: `60`, `61`
- hide/custom UI variants: `13`, `28`, `32`
- PRO26 family: `105`, `109`, `112`, `119`, `121`, `123`, `124`
- F-resolution no music/gesture IDs: `212`, `213`

These model IDs should be considered publisher-level capability IDs, not just
resolution values. KY FPV uses them to hide controls, change language, switch
backgrounds, set double-camera state, and select backend behavior.

### Impact On TurboDrone

Current TurboDrone `cooingdv` support maps well to:

- RC UFO Wi-Fi TC/GL path.
- KY UFO Wi-Fi TC/GL path.
- RC FPV classic TC Wi-Fi path.
- KY FPV `DeviceTXFragment` classic TC Wi-Fi path.
- 4DRC FPV drone-flight path.

Current TurboDrone does not yet cover:

- KY/RC native `UAV` / `StreamClient` BL60x-style native transport unless the
  drone also exposes the classic Java Wi-Fi path.
- KY FPV `DeviceClient` / Jieli JSON settings backend.
- The expanded KY FPV model-ID capability table and UI-hide/customization
  behavior.
- 4DRC FPV excavator/ground-vehicle controls.

The safest immediate expansion is to broaden CooingDV telemetry recognition with
the RC FPV and KY FPV IDs while keeping the packet encoder conservative:

- Treat RC FPV as TC/short unless runtime telemetry proves otherwise.
- Treat KY FPV classic `DeviceTXFragment` as TC/short.
- Do not assume the Jieli JSON backend is reachable through UDP `7099`.
- Do not assume KY FPV native `mjpeg_jni` behaves exactly like KY UFO
  `libuav_gl.so` / `libuav_tc.so` for every model, even though Ghidra shows the
  same BL60x-style `192.168.169.1:8800` native protocol family.
- Treat 4DRC FPV `EXCAVATOR_720 = 89` as a non-flight device class. It may share
  video and native BL transport, but its RC packet is a drive/excavator packet,
  not a quadcopter packet.

Implementation recommendation:

- Add `cooingdv_bl` only if hardware capture shows target drones require the
  native `192.168.169.1:8800` path and do not expose classic RTSP/UDP.
- Add `cooingdv_jieli` as a distinct backend if we want KY FPV
  `DeviceClient`/Jieli devices. It needs CTP packet construction, UDP `2228`,
  Jieli realtime stream handling, and JSON command topics. TurboDrone now has
  initial CTP RC and RTP/JPEG video support, but it still needs hardware
  validation and H.264 handling if a device chooses RTS format `1`.
- Add a drive/excavator backend only if TurboDrone intentionally grows beyond
  flying drones. The 4DRC excavator path is clearly CooingDV-family, but it does
  not belong in a flight-control adapter.

### 4DRC FPV 1.6.0

4DRC FPV package:

```text
com.cooingdv.fpv4drc
```

The app is a strong overlap with KY UFO / RC FPV:

- Classic RTSP preview: `rtsp://192.168.1.1:7070/webcam`
- UDP command/telemetry: `192.168.1.1:7099`
- Heartbeat: `01 01`
- Camera switch: `06 01` / `06 02`
- Photo/video gallery sync: `09 01` / `09 02`
- Native bridge: `com.cooingdv.bl60xmjpeg.UAV`
- Native libraries in split APK:
  - `libuav_gl.so`
  - `libuav_tc.so`
  - `libnative-lib.so`
  - IJK/OpenCV/GPUImage/pocketsphinx support libraries

The 4DRC native `libuav_gl.so` and `libuav_tc.so` contain the same important
BL60x-family strings and symbols:

- `192.168.169.1`
- `8800`
- `mjpeg_ndk_start`
- `mjpeg_ndk_command_send`
- `mjpeg_ndk_set_active_camera_index`
- `mjpeg_ndk_set_QPara`
- `build_send_ack`
- `handle_mcu_msg_frag`
- embedded `jpeg_header_640x360_Q*` tables

This means 4DRC FPV overlaps with `cooingdv_bl`, not Jieli.

4DRC FPV `FlyController` is the familiar KY UFO-style TC/GL split:

- If `UAV.getInstance().getDeviceType() != 10`, it builds the GL extended
  20-byte inner payload `66 14 ... 99`, then prefixes `03` for Wi-Fi.
- If device type is `10`, it builds the TC 8-byte inner payload `66 ... 99`,
  then prefixes `03` for Wi-Fi.
- Native `UAV` mode sends the inner payload directly.
- Stop/exit sends native `65` (`0x65`, decimal 101) when native is active, or
  UDP `08 01` otherwise.

The biggest unique piece is not a drone: 4DRC FPV includes an excavator/drive
mode.

`WifiIdUtils` defines:

```text
EXCAVATOR_720 = 89
```

If this ID is selected, the menu opens `ExcavatorFragment`, which uses
`DriveController`, not `FlyController`.

`DriveController` packet:

```text
33 TURN ACCEL BUCKET_FLAGS MODE_FLAGS 88
```

Wi-Fi wrapper:

```text
03 33 TURN ACCEL BUCKET_FLAGS MODE_FLAGS 88
```

Drive/excavator bytes:

- Byte 0: `0x33` (`51`)
- Byte 1: turn
- Byte 2: accelerator
- Byte 3: bucket flags
  - `0x01`: excavator rise
  - `0x02`: excavator drop
  - `0x04`: excavator left
  - `0x08`: excavator right
- Byte 4: mode flags
  - `0x04`: auto
  - `0x08`: music
  - `0x10`: light
- Byte 5: `0x88` (`136`)

This packet has no checksum byte and is not compatible with TurboDrone's
quadcopter control model. If we ever support it, it should be a separate
ground-vehicle/excavator backend, not a `cooingdv` flight variant.

## Telemetry And App Messages

Both apps pass received UDP packets to the flight fragment.

Common photo/video notifications:

- If `bArr[2] == 77` (`0x4d`, ASCII `M`), the app treats it as a photo event.
  The photo counter is read from `bArr[3]`.
- If `bArr[2] == 88` (`0x58`, ASCII `X`), the app treats it as a video event.
  The video counter is read from `bArr[4]`.
- On new photo count, both apps send `09 01`.
- On new video count, both apps send `09 02`.
- Shorter packets with only `bArr[2] == M/X` trigger direct UI tab switching.

RC UFO has additional GL Wi-Fi status handling when `SocketClient.getDeviceType()
== 2` and `bArr[0] == 0x66`:

- If `bArr[1] == 0`, it reads state from `bArr[2]` and `bArr[9]`.
- If packet length is 10 or 15, it reads a state byte from `bArr[4]`.
- State values toggle `isTakingControl` and simulate top-list UI clicks for
  photo/video tabs.

KY's Wi-Fi `SocketClient` handles first-byte resolution, GL/TC detection, camera
reset state in `bArr[1]`, and screen-switch state in `bArr[2]`. KY's richer GL
status parsing appears in the native `PicDataCallback` path used by
`DeviceGLFragment` and `DeviceBLFragment`.

## KY UFO Native Path

KY UFO includes `com.cooingdv.bl60xmjpeg.UAV` and native wrappers:

- `GLJni` loads `libuav_gl`
- `TCJni` loads `libuav_tc`

`MainActivity` initializes the native stack:

```text
UAV.getInstance().init(this)
UAV.getInstance().startServer()
SocketClient.getInstance().initVideoView(...)
SocketClient.getInstance().start()
```

`UAV` starts in unknown device type `0`. Native `deviceStatus` sets:

- `10` for TC.
- `2` for GL.

`UAV.sendCommand(byte[])` sends to the native implementation selected by
`mDeviceType`.

Important distinction:

- Wi-Fi control packets include the leading `0x03` wrapper.
- Native `UAV` commands use the inner 8-byte TC or 20-byte GL payload directly.

Native video callbacks:

- `picData(byte[] bArr, long seq, byte quality)` receives JPEG-like frame bytes.
- On first frame, `UAV` marks itself active and sends native command `0x64`.
- If not stopped, frames are passed to `PicDataCallback.onData`.
- `picMessage(byte[] bArr)` is used for resolution/status messages and can send
  native command `0x63` after resolution discovery.

RC UFO does not include this `bl60xmjpeg.UAV` path in the inspected package. It
is Wi-Fi/RTSP oriented and adds password handling and advertising/consent code.

## Native Library Inventory

KY UFO ships native libraries under `resources/lib` for three ABIs:

- `arm64-v8a`
- `armeabi`
- `armeabi-v7a`

Each ABI contains:

- `libgesture-lib.so`
- `libgpuimage-library.so`
- `libijkffmpeg.so`
- `libijkplayer.so`
- `libijksdl.so`
- `libopencv_java3.so`
- `libuav_gl.so`
- `libuav_tc.so`

The `arm64-v8a` libraries are the most useful static-analysis target:

| Library | Size | SHA-256 prefix | Role |
| --- | ---: | --- | --- |
| `libuav_gl.so` | 30,472 | `b62090ca898f41d4` | GL native MJPEG/control engine |
| `libuav_tc.so` | 26,376 | `d43457e0f04b6025` | TC native MJPEG/control engine |
| `libgesture-lib.so` | 501,976 | `b209601f7489a586` | OpenCV-backed gesture recognition |
| `libijkplayer.so` | 418,984 | `c8ed8af43bf12090` | IJK player core |
| `libijksdl.so` | 485,448 | `d53a2b3c63a6ce35` | IJK SDL/media glue |
| `libijkffmpeg.so` | 3,780,216 | `3787aeac5935379a` | FFmpeg media stack |
| `libopencv_java3.so` | 18,696,224 | `34b23b9914cfb6bb` | OpenCV runtime |
| `libgpuimage-library.so` | 5,448 | `a7d4b44990bb5ef0` | GPUImage JNI/helper |

RC UFO's inspected `resources` tree has no `resources/lib` directory and no
bundled `.so` files. Its Java still calls `System.loadLibrary("lib_gesture")`,
so this particular decompile appears to be incomplete for that library, built
from a split APK without the native split, or decompiled from an APK variant that
omitted native libs.

## Native JNI Surface

KY `GLJni` exports these JNI entrypoints from `libuav_gl.so`:

- `Java_com_cooingdv_bl60xmjpeg_utils_GLJni_nativeInit`
- `Java_com_cooingdv_bl60xmjpeg_utils_GLJni_nativeStart`
- `Java_com_cooingdv_bl60xmjpeg_utils_GLJni_nativeStop`
- `Java_com_cooingdv_bl60xmjpeg_utils_GLJni_nativeUninit`
- `Java_com_cooingdv_bl60xmjpeg_utils_GLJni_UnregisterDeviceStatus`
- `Java_com_cooingdv_bl60xmjpeg_utils_GLJni_nativeSendCommand`
- `Java_com_cooingdv_bl60xmjpeg_utils_GLJni_nativeSetCameraIndex`
- `Java_com_cooingdv_bl60xmjpeg_utils_GLJni_nativeSetQPara`
- `Java_com_cooingdv_bl60xmjpeg_utils_GLJni_nativeSetModify`

KY `TCJni` exports these JNI entrypoints from `libuav_tc.so`:

- `Java_com_cooingdv_bl60xmjpeg_utils_TCJni_stringFromJNI`
- `Java_com_cooingdv_bl60xmjpeg_utils_TCJni_unimplementedStringFromJNI`
- `Java_com_cooingdv_bl60xmjpeg_utils_TCJni_nativeSendCommand`
- `Java_com_cooingdv_bl60xmjpeg_utils_TCJni_nativeSetModify`
- `Java_com_cooingdv_bl60xmjpeg_utils_TCJni_setActiveCameraIndex`
- `Java_com_cooingdv_bl60xmjpeg_utils_TCJni_setQPara`

`libgesture-lib.so` exports:

- `Java_com_cooingdv_kyufo_utils_JniUtils_nativeGestureRecognition`

The KY gesture library links against `libopencv_java3.so`, references
`gesture.jpg`, `fist.xml`, and `rpalm.xml` under the app documents directory,
and appears UI/vision-only. It does not appear to carry flight-control or video
transport protocol logic.

The native callback map is:

```text
libuav_gl.so
  -> GLJni.cbJpegFromNative(byte[], long, byte)
      -> ReceiveDataCallback.picData(...)
      -> UAV.AnonymousClass1.picData(...)
      -> PicDataCallback.onData(...)
      -> MjpegThread.drawBitmap(...)

  -> GLJni.cbCtlMsgFromNative(byte[], long)
      -> ReceiveDataCallback.picMessage(...)
      -> UAV.AnonymousClass1.picMessage(...)
      -> PicDataCallback.onReceiver(...)

  -> GLJni.cbDeviceStatusFromNative(byte[], long)
      -> ReceiveDataCallback.deviceStatus(...)
      -> UAV.AnonymousClass1.deviceStatus(...)

libuav_tc.so
  -> TCJni.function_for_pic(byte[], long, byte)
      -> ReceiveDataCallback.picData(...)

  -> TCJni.java_function_for_mcuctl(byte[], int, int)
      -> ReceiveDataCallback.picMessage(...)
```

## Native MJPEG Engine Findings

`libuav_gl.so` and `libuav_tc.so` are not generic wrappers only. They contain a
small native MJPEG/control engine with symbols such as:

- `mjpeg_ndk_start`
- `mjpeg_ndk_startup`
- `mjpeg_ndk_stop`
- `mjpeg_ndk_command_send`
- `mjpeg_ndk_settings_send`
- `mjpeg_ndk_queryinfo_cmd_send` (TC)
- `mjpeg_ndk_custom_cmd_send` (GL)
- `mjpeg_ndk_frame_callback_register`
- `mjpeg_ndk_ctlmsg_cb_register`
- `mjpeg_ndk_device_status_cb_register` (GL)
- `handle_mcu_msg_ctlmsg`
- `handle_mcu_msg_frag`
- `build_send_ack`

The native libraries also contain built-in JPEG header tables:

- `jpeg_header_640x360_Q5`
- `jpeg_header_640x360_Q10`
- `jpeg_header_640x360_Q25`
- `jpeg_header_640x360_Q50`
- `jpeg_header_640x360_Q75`
- `jpeg_header_640x360_Q100`

The decompiled native fragment handlers show the native path is assembling JPEG
frames from MCU fragments:

- The fragment payload size is `0x400` bytes for non-final fragments.
- The final fragment copies `body_len & 0x3ff` bytes.
- Fragment slots are keyed by sequence and fragment ID.
- Four image assembly slots are used.
- A small output queue is used; when full, the oldest queued frame is dropped.
- Fragment receipt is tracked with a bitset.
- The first fragment causes the library to copy one of the built-in JPEG
  headers into the output buffer.
- Width/height fields are patched into that JPEG header.
- The final fragment appends JPEG EOI bytes `ff d9`.
- Once all fragments are present, a complete JPEG is pushed to the Java callback
  queue.

This is stronger than the Java-only inference: KY's native `UAV` path delivers
complete JPEG byte arrays to Java after native fragment reassembly. The Java
`MjpegThread` then decodes those complete JPEGs with `BitmapFactory`.

The quality byte from native fragment metadata selects the JPEG header table:

- `5` -> Q5
- `10` -> Q10
- `25` -> Q25
- `50` -> Q50
- `75` -> Q75
- `100` -> Q100

Both `libuav_gl.so` and `libuav_tc.so` contain `192.168.169.1` as a native
target string, and the decompiled native start paths pass port string `8800`.
That does not match the Wi-Fi RTSP/UDP Java constants `192.168.1.1:7070` and
`192.168.1.1:7099`; the KY native `UAV` path is therefore a separate BL60x-style
native transport, not the same Java `SocketClient` Wi-Fi path.

### Native Socket Lifecycle

Both native engines allocate a large session object and open a UDP socket:

- Local bind: `getaddrinfo("0.0.0.0", NULL, ...)`, `socket(AF_INET, SOCK_DGRAM)`,
  then `bind(...)`. Because no service/port is provided, this binds an ephemeral
  local UDP port.
- Remote target: `getaddrinfo("192.168.169.1", "8800", ...)`.
- GL marks the socket non-blocking with `fcntl(..., O_NONBLOCK)`.
- Both engines store the local socket and remote sockaddr in the session.

GL creates three detached threads from `create_instance`:

- Timer / ACK / start thread.
- Frame delivery thread.
- Receive/parser thread.

TC creates analogous threads, but its thread functions attach to the JVM because
TC uses static Java callback functions.

The timer/start thread sends a 4-byte start packet until the first frame/fragment
activity is established:

```text
ef 00 04 00
```

This is `0x000400ef` in the little-endian decompiler output. The thread sends it
about every 100 ms while the engine is not yet active. Once active, it watches
for fragment silence; after roughly 3000 ms without fragments, it resets the
native assembly state and starts again.

The native engines also send ACKs about every 25 ms while active. If the last
fragment was very recent, the ACK builder uses the latest fragment slot; if not,
it uses a special `0xfffffffe` path that can request recovery or report pending
flight-control-only state.

### Native Incoming Message Envelope

The native receive thread reads up to `0x438` bytes from the UDP socket and only
accepts packets whose first byte is `0x93` and whose 16-bit length field at
offset 2 equals the number of bytes read.

The observed incoming envelope is:

```text
offset  size  meaning
0x00    1     0x93 packet marker
0x01    1     message type
0x02    2     total packet length
0x04    4     sequence / command id / status id
0x08    2     payload length for control/status callbacks
0x0c    ...   payload bytes
```

Message types observed in native dispatch:

- `0x01`: image fragment, handled by `handle_mcu_msg_frag`.
- `0x02`: ACK, TC-only dispatch to `handle_mcu_msg_ack`.
- `0x04`: MCU control/status message, handled by `handle_mcu_msg_ctlmsg`.
- `0x08`: query-info response, TC-only dispatch to
  `handle_mcu_msg_queryinfo_resp`.

GL's receive thread handles fragment (`0x01`) and control/status (`0x04`).
TC's receive thread handles fragment (`0x01`), ACK (`0x02`), control/status
(`0x04`), and query-info response (`0x08`).

### Native Control Message Handling

Native `nativeSendCommand(byte[])` does not reinterpret the Java control bytes.
Both GL and TC wrappers copy the Java byte array from JNI into a local buffer and
pass it to `mjpeg_ndk_command_send`.

Important differences:

- GL native command send accepts payloads shorter than `0x81` bytes and stores
  command length and `length + 0x0c`.
- TC native command send accepts payloads shorter than `9` bytes and stores a
  duplicate command envelope with magic `0x04ef`.
- The Java `FlyController` sends inner TC/GL payloads into native mode, not the
  Wi-Fi `0x03` wrapper.

Native command payloads are not always sent immediately as standalone UDP
packets. The regular `mjpeg_ndk_command_send` path stores the command in the
session so the ACK/timer thread can include it in the next outgoing ACK/control
packet. This explains the native log string:

```text
[ACK] 0 frame ack, flyctl msg only
```

Settings/custom helpers do send immediate UDP packets:

- GL/TC settings packets use magic `0x04ef`, a `length + 0x0c` field, and copy
  the settings payload after a 12-byte native envelope.
- GL custom command packets use magic `0x20ef`, a `length + 4` field, and copy a
  payload of 1..64 bytes.
- TC query-info packets use magic `0x10ef` and message type/status `0x08` in the
  decompiled `0x000810ef` word.

Native `handle_mcu_msg_ctlmsg` receives MCU control/status payloads and forwards
the bytes after a 12-byte native envelope to Java callbacks:

- GL forwards `param_2 + 0x0c`, length at `param_2 + 8`, and sequence/status at
  `param_2 + 4`.
- TC checks a header byte `0x93`, validates the packet length, forwards
  `param_2 + 0x0c`, and sends an 8-byte ACK/control response with magic
  `0x0808ef`.

Native `build_send_ack` builds ACK packets for image fragments:

- GL uses magic `0x02ef` with `0x01000202` in the decompiled local header.
- TC uses analogous ACK behavior and logs urgent whole-loss, normal, special,
  and fly-control-only ACK cases.
- GL logs `[ACK] 0 frame ack, flyctl msg only` when there are no image-frame
  ACKs but a pending flight-control message exists.

These ACK/envelope formats are internal to the KY native MJPEG transport. They
are not the same as the Java Wi-Fi RC packets documented earlier.

### Native Frame Delivery Thread

After `handle_mcu_msg_frag` has assembled a complete JPEG, it pushes the image
into a small native queue. A separate delivery thread drains that queue:

- Sleeps around 38 ms between normal delivery attempts.
- If the queue is empty, waits an additional ~19 ms and checks again.
- Logs delayed delivery when frame interval exceeds about 76 ms.
- Calls the registered Java frame callback with:
  - JPEG bytes
  - total JPEG length
  - sequence metadata
  - quality byte
  - GL-only extra camera/status flag

This means the native `UAV` frame callback is already latency-throttled before
Java sees it. It is not just a raw packet callback.

## PTZ / Servo / Camera Tilt Findings

No confirmed PTZ or camera-tilt servo command was found in the inspected KY UFO
or RC UFO paths.

Several UI elements look suspicious at first:

- `verticalBar`
- `horizontalBar`
- `horizontalCenterBar`
- `view_control_device_vertical_add`
- `view_control_device_vertical_del`
- `VerticalSeekBar`

However, these are flight trim controls, not camera servos. In both KY UFO and
RC UFO, `verticalCurrentValue` is added into `controlByte2`, the same pitch axis
that is sent in the regular RC control packet. `horizontalCurrentValue` adjusts
yaw/turn, and `horizontalCenterCurrentValue` adjusts `controlByte1`.

Observed mapping:

- `horizontalBar` -> yaw trim / `controlTurn`
- `horizontalCenterBar` -> roll trim / `controlByte1`
- `verticalBar` -> pitch trim / `controlByte2`

KY native camera-related functions are also not PTZ:

- `UAV.switchActiveCamera(...)` -> `setActiveCameraIndex(...)` /
  `nativeSetCameraIndex(...)`. Native code stores a camera index byte that is
  later included in ACK/control state; this appears to select front/rear or
  active camera stream.
- `UAV.setQPara(...)` -> native JPEG quality parameter ranges. Native code
  validates quality values such as 5, 10, 25, 50, 75, and 100 and stores
  min/max quality thresholds.
- `UAV.setModify(...)` is firmware/configuration UI for SSID, resolution,
  channel, protocol, rotate, and flow orientation. It is not exposed as runtime
  tilt control.

The apps also implement digital pan/zoom on decoded frames through
`MjpegThread.setFocusScale(...)` and `setFocusMove(...)`, but that is display
crop/zoom, not mechanical camera motion.

Conclusion: if some CooingDV-published drones have tilt servos, this pair of
decompiled apps does not expose an obvious runtime PTZ command for them. It may
exist in another white-label app, another firmware telemetry/status packet, or a
model-specific command not reachable from the visible KY/RC UI.

### M10 hardware probe (GL reserved-byte sweep, negative)

TurboDrone `experimental/cooingdv/gl_tilt_probe.py` was run against an **M10**
on **GL** (`resolution-id=101`, 21-byte `03 66 14 ... 99` packets):

- Full auto-sweep of Wi-Fi bytes **9–18** with values
  `00, 01, 02, 04, 08, 10, 20, 40, 80, FF` (2.5 s each, neutral sticks).
- Sweep of unused `flags1` bits `10, 20, 40, 80` and `flags2` bits
  `02, 04, 08, 10, 20, 40, 80`.
- WiFi-UAV-style 2-bit patterns on bytes 9–10 (`40`/`80`/`C0`, `01`/`02`).

**Result:** no mechanical camera tilt observed. Some flag/reserved combos caused
LEDs to switch between solid and flashing (likely firmware rejecting non-stock
frames); flight axes were left at center (`0x80`).

This does not prove all CooingDV drones lack a tilt servo, but for **M10 + GL
Wi-Fi RC on UDP 7099**, tilt is **not** in the obvious reserved region or
unused GL flag bits tested above.

## Video Feed

### Wi-Fi RTSP Path

Both apps use:

```text
rtsp://192.168.1.1:7070/webcam
```

Playback is handled by `IjkVideoView`. The apps configure:

- `mediacodec = 0`
- `readtimeout = 5000000`
- `preferred-image-type = 0`
- `image-quality-min = 2`
- `image-quality-max = 20`
- `preferred-video-type = 2`
- `video-need-transcoding = 1`
- `mjpeg-pix-fmt = 1`
- `video-quality-min = 2`
- `video-quality-max = 20`
- `x264-option-preset = 0`
- `x264-option-tune = 5`
- `x264-option-profile = 1`
- `x264-params = "crf=23"`
- `auto-drop-record-frame = 3`
- codec option `err_detect = "explode"`

The app enables original frame callbacks:

```text
mVideoView.setOutputOriginalVideo(true)
mVideoView.setOnReceivedOriginalDataListener(...)
```

The callback passes each `byte[]` to the fragment's `onVideo(...)`, and the
fragment calls:

```text
mjpegThread.drawBitmap(bArr)
```

`MjpegThread` decodes the whole byte array:

```text
BitmapFactory.decodeByteArray(remove, 0, remove.length)
```

That makes the app boundary frame format effectively "complete JPEG blob per
callback". There is no Java RTP packet assembler in these app paths.

### Display Transform Variations

The apps apply display-side transformations after decoding JPEG bytes:

- Cropping `800x600` frames to `800x540` by removing 30 pixels top and bottom.
- Rotating portrait-like frame sizes such as `240x320`, `120x160`, and
  `160x272` by 90 degrees unless the resolution ID is a no-rotate ID.
- Optional 180-degree rotation through `isTurnBitmap`.
- Portrait crop to a 9:16 center region.
- Focus/zoom cropping controlled by `focusScale`, `focusMoveX`, and
  `focusMoveY`.
- Gesture recognition uses the same video byte stream.

No equivalent display transforms are currently implemented in
`CooingdvVideoProtocolAdapter`. TurboDrone receives decoded RTSP frames from
OpenCV and re-encodes them to JPEG without app-specific rotation/cropping.

### Local Recording

The apps' `VideoModel` records by encoding processed display frames to H.264:

- Encoder: `video/avc` or `OMX.google.h264.encoder`.
- Output: `REC_<unix>_0.mp4`.
- Bitrate: `2000000`.
- I-frame interval: `5`.
- Presentation time: `(frameIndex * 1000000 / fps) + 132`.
- SPS/PPS handling: once codec config is captured, if output byte 4 is `101`
  (`0x65`, H.264 IDR NAL), the app prepends SPS/PPS before returning the encoded
  buffer.

This is the app's local recording pipeline. It should not be confused with the
drone-to-phone RTSP/JPEG frame boundary.

## TurboDrone Implementation

### CLI and Web Defaults

`main.py` supports:

```text
--drone-type cooingdv
```

Defaults:

- `drone_ip = 192.168.1.1`
- `control_port = 7099`
- `video_port = 7070`
- `control_rate = 20.0`

`web_server.py` follows the same class wiring for `DRONE_TYPE=cooingdv`.

### RC Model

`CooingdvRcModel` extends `BaseRCModel` with:

- Stick range: `50..200`, center `128`.
- `IncrementalStrategy`.
- One-shot flags:
  - `takeoff_flag`
  - `land_flag`
  - `stop_flag`
  - `flip_flag`
  - `calibration_flag`
- Toggle state:
  - `headless_flag`

The model exposes:

- `takeoff()`
- `land()`
- `emergency_stop()`
- `flip()`
- `toggle_headless()`
- `calibrate_gyro()`
- `get_control_state()`

### RC Protocol Adapter

`CooingdvRcProtocolAdapter`:

- Opens one UDP socket.
- Binds to an ephemeral local port to match Android `DatagramSocket()`.
- Sends heartbeat `01 01` every second.
- Starts a receive thread for telemetry-driven variant detection.
- Builds TC or GL packets from the active variant.
- Sends packets to `drone_ip:control_port`.
- On `stop()`, stops heartbeat, sends `08 01`, stops receiver, and closes the
  socket.

Important constants:

- `PREFIX = 0x03`
- `START_MARKER = 0x66`
- `EXTENDED_MARKER = 0x14`
- `END_MARKER = 0x99`
- `HEARTBEAT_COMMAND = bytes([0x01, 0x01])`
- `STOP_COMMAND = bytes([0x08, 0x01])`

The adapter clears one-shot command flags immediately after building each
packet. It does not clear `headless_flag`, because that is a toggle state.

### Flight Controller Scheduling

`FlightController._control_loop`:

- Computes `dt`.
- Calls `model.update(dt, axes)`.
- Calls `protocol.build_control_packet(model)`.
- Calls `protocol.send_control_packet(packet)`.
- Sleeps `1 / update_rate`.

For CooingDV the default update interval is 50 ms, matching the Android app's
`SEND_COMMAND_INTERVAL = 50` in `FlyController`.

### Video Protocol Adapter

`CooingdvVideoProtocolAdapter`:

- Builds `rtsp://{drone_ip}:{video_port}/webcam`.
- Opens it using `cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)`.
- Sets `CAP_PROP_BUFFERSIZE = 1` for lower latency.
- Reads decoded BGR frames.
- Re-encodes each frame as JPEG with quality 85.
- Wraps the bytes with `CooingdvVideoModel.ingest_chunk`.
- Publishes `VideoFrame` objects through a size-2 queue.
- Drops the oldest queued frame when the queue is full.
- Reconnects after a 5 s frame timeout or OpenCV errors.

This is different from TurboDrone's S2x and WiFi-UAV adapters. There is no raw
UDP video packet assembler for CooingDV in TurboDrone; `get_packets()` returns
an empty list.

## Implementation Gaps And Risks

- TurboDrone currently uses product-level names (`takeoff`, `land`, `flip`) for
  bits whose app symbols are lower-level (`isFastFly`, `isFastDrop`,
  `isCircleTurnEnd`). This may be correct UX-wise, but the doc should not imply
  the Android apps have named takeoff/land opcodes.
- `0x08 0x01` is only an exit-control command in the apps. It should not be used
  as a startup/init packet.
- GL bit `flags2 0x02` (`isFixedHeightMode`) is observed in both apps, but
  TurboDrone does not currently expose or set a CooingDV fixed-height flag.
- KY GL `flags1 0x10` (`isOpenLight`) is not exposed by TurboDrone.
- GL `flags1 0x40` (`isGestureMode`) is app-side UI/vision behavior and should
  not be treated as a drone flight command unless separately verified.
- RC UFO's decompiled `FlyControlTask.run()` has damaged control-flow output
  around `isFastReturn` / `isUnLock`; KY's source is cleaner and should be
  preferred for TC flag interpretation.
- RC UFO's decompiled UDP receive method is also damaged around password and
  telemetry parsing. The visible fragments still confirm password IDs and the
  8-digit password command.
- RC UFO's Java references `System.loadLibrary("lib_gesture")`, but this
  workspace's RC UFO decompile has no `resources/lib` tree. If RC native
  behavior matters later, reacquire the full universal APK or the relevant split
  APK containing native libraries.
- The exact RTSP wire codec is not fully proven from Java source alone. At the
  app boundary, the original-data callback is handled as JPEG bytes.
- KY native `UAV` video is now stronger than inference: `libuav_gl.so` and
  `libuav_tc.so` reassemble 1024-byte MCU fragments into complete JPEG images
  using embedded 640x360 JPEG headers and append `ff d9` on the final fragment.
- TurboDrone does not yet implement the Android app's display transforms:
  no-rotate IDs, portrait rotations, `800x600 -> 800x540` crop, or alternate
  camera/screen restart behavior.
- TurboDrone auto-detection falls back to TC until it receives a recognized
  telemetry byte. GL hardware may need `COOINGDV_VARIANT=gl` if telemetry is
  delayed, filtered, or not sent to the ephemeral local port.
- KY native `libuav_gl.so` and `libuav_tc.so` use a separate
  `192.168.169.1:8800` native transport, while the Java CooingDV Wi-Fi path uses
  `192.168.1.1:7099` for RC and `192.168.1.1:7070` for RTSP. Do not change
  TurboDrone's CooingDV defaults based on the native path without hardware
  evidence that the target drone exposes that BL60x interface.

## Deep-Dive Follow-Ups

- Decompile the remaining unnamed helper functions around the GL/TC native
  threads to improve field names and confirm every byte in the ACK packet
  envelope. The main native socket target and incoming envelope are now mapped.
- Recover or reacquire RC UFO's missing native split if the RC gesture/native
  behavior needs parity with KY. The Java package references `lib_gesture`, but
  the inspected RC resources do not include it.
- Capture KY native traffic when `UAV.isActive()` is true. Confirm whether
  `192.168.169.1:8800` is reachable on real KY hardware, whether packets are
  sent over Wi-Fi or another interface, and how it relates to the Java RTSP path.
- Capture GL and TC Wi-Fi traffic from hardware while toggling fixed-height,
  light, camera, screen switch, gyro correction, and emergency stop. Use the
  captures to decide which currently unimplemented flags are safe to add to
  TurboDrone.
- Add optional TurboDrone diagnostics to log first-byte telemetry IDs, GL `0x66`
  status packets, and camera/gallery notifications before adding more control
  surface.

## Useful Test Packets

Neutral TC hover/control packet:

```text
03 66 80 80 80 80 00 00 99
```

Neutral GL hover/control packet:

```text
03 66 14 80 80 80 80 00 00 00 00 00 00 00 00 00 00 00 00 00 99
```

TC emergency-stop style packet:

```text
03 66 80 80 80 80 04 04 99
```

GL emergency-stop style packet:

```text
03 66 14 80 80 80 80 02 00 00 00 00 00 00 00 00 00 00 02 99
```

Heartbeat:

```text
01 01
```

Leave control mode:

```text
08 01
```

Camera switch:

```text
06 01
06 02
```

Gallery/screen sync:

```text
09 01
09 02
```

RC UFO password command for password `12345678`:

```text
0a 01 02 03 04 05 06 07 08
```
