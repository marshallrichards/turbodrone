# WiFi_CAM Protocol Research

This note documents the decompiled `WiFi_CAM` Android app from
`decompiled-wifi-cam-6.1.8`, including the native `libCamera.so` transport in
`resources/lib/arm64-v8a`.

## Executive Summary

`WiFi_CAM` should be treated as a separate TurboDrone backend candidate named
`wifi_cam`.

The first Java-only pass looked similar to `cooingdv_jieli` because
`IConstants.java` contains Jieli-style constants such as `192.168.8.15`, UDP
`2228`, RTP `6666`, and SDP `6789`. Native analysis of `libCamera.so` shows the
actual live camera/control path is different:

- Device IP: `192.168.4.153`
- Video/data UDP socket: `8080`
- RC/command UDP socket: `8090`
- Stream start command: `42 76`
- Stream stop command: `42 77`
- Rotate command: `42 78`
- Camera switch command: `42 79`
- RC payload: raw Java-built `66 ... 99` 8-byte or 20-byte command sent to UDP
  `8090`
- Video payload: fixed `0x5c0` UDP datagrams with an 8-byte native header and a
  `0x5b8` JPEG slice body, reassembled into complete JPEG frames by native code

This does not match TurboDrone's current `cooingdv`, `cooingdv_jieli`, `s2x`, or
`wifi_uav` implementations closely enough to reuse one unchanged.

## Native Evidence

Native libraries are present under:

```text
decompiled-wifi-cam-6.1.8/resources/lib/arm64-v8a/
```

Important library:

```text
libCamera.so
```

Ghidra headless outputs used for this pass:

- `tools/ghidra_out/wifi_cam_libCamera_functions_all.txt`
- `tools/ghidra_out/wifi_cam_libCamera_jni_table.txt`
- `tools/ghidra_out/wifi_cam_libCamera_decompiled/`

Helper scripts added for repeatable native analysis:

- `tools/ghidra_scripts/ExportFunctionsByAddress.java`
- `tools/ghidra_scripts/DumpJniNativeTable.java`
- `tools/ghidra_scripts/DumpMatchingSymbols.java`

## JNI Table

`JNI_OnLoad` registers 22 native methods for `com.tzh.wifi.utils.Camera`.
Important mappings:

```text
iCameraInit      -> FUN_00133718
iCameraDeinit    -> FUN_001337f4
iCameraStart     -> FUN_001338f8
iCameraStop      -> FUN_0013392c
iCmdStart        -> FUN_00133b20
iCameraRoate     -> FUN_00133b28
iCameraSwitch    -> FUN_00133b50
iCmdSend         -> FUN_00133b78
iCmdResume       -> FUN_00133c2c
iCmdStop         -> FUN_00133c34
iYuanInit        -> FUN_00133d2c
iYuanProc        -> FUN_00133e6c
iYuanRelease     -> video_uninit
```

`iCameraInit` allocates the native `Socket`, `MjpegToAvi`, `AviReader`, and
`MjpegToMp4` objects. `iCameraStart` calls `Socket::connect()`.

## Socket Lifecycle

`Socket::connect()` starts two threads:

- `udpSocketEnterance`
- `cmdSocketEnterance`

`udpSocketEnterance` creates two UDP sockets:

```text
Socket::create(udpSocket, "192.168.4.153", 0x1f90)  // 8080
Socket::create(cmdSocket, "192.168.4.153", 0x1f9a)  // 8090
```

The sockets are unconnected UDP sockets using `sendto(...)` and `recvfrom(...)`.
There is no CTP envelope, no `CTP:` string, no `FLYING_CTRL` topic, and no Jieli
JSON transport in the native library.

## IP Address Families

The app carries several IP constants, but they do not all represent active live
transport paths in the reviewed build:

- `192.168.4.153` is the active native camera/control target. `libCamera.so`
  hardcodes this address for both UDP `8080` video/data and UDP `8090` command
  sockets.
- `192.168.4.151` appears only in `WiFiApp.java` as `TCP_SERVER_IP`. The app
  compares the Wi-Fi DHCP gateway against `192.168.4.151` and `192.168.4.153`,
  returning `1` or `2`, but no caller was found under `com/tzh/wifi`. Treat this
  as a dormant/legacy mode hint until packet captures prove otherwise.
- `192.168.8.15` appears in `IConstants.DEFAULT_DEV_IP` with Jieli-like
  `2228`/RTP/SDP constants. No Java caller or native `libCamera.so` evidence was
  found for this path in the reviewed WiFi_CAM live preview/control flow.
- `192.168.1.1` appears as an FTP/media constant, likely for legacy file access
  or shared firmware support, not live flight/video control.

This suggests WiFi_CAM is a broad whitelabel codebase carrying constants for
multiple device families. For TurboDrone, implement the observed
`192.168.4.153` native UDP backend first, and only split additional
`wifi_cam_*` variants if later apps or captures show one of the dormant IP
families is actually used.

## Stream Commands

Ghidra data-symbol dump shows the 2-byte commands:

```text
startCmd   = 42 76
stopCmd    = 42 77
rotateCmd  = 42 78
switchCmd  = 42 79
```

`udpSocketEnterance` sends `startCmd` to `192.168.4.153:8080` after socket
creation and sends `stopCmd` when disconnecting. `iCameraRoate()` sends
`rotateCmd`; `iCameraSwitch()` sends `switchCmd`.

## Camera Tilt / Servo Findings

No confirmed camera-tilt/PTZ/servo command was found in the WiFi_CAM Java or
native paths reviewed so far.

The camera-named native commands are limited to:

- `Camera.iCameraRoate()` / `Socket::writeRotateCmd()` -> `42 78` on UDP
  `8080`.
- `Camera.iCameraSwitch()` / `Socket::writeCameraSwitch()` -> `42 79` on UDP
  `8080`.

The UI wiring suggests these are not camera pitch-servo controls:

- `btnCameraSwitch` calls `Camera.iCameraSwitch()` and is guarded by the
  camera-type probe, matching a front/back or dual-camera switch.
- `btnPlayRev` calls `Camera.iCameraRoate()` and uses `zone_rotate_180` assets,
  consistent with rotating/flipping the camera image orientation.
- `btnPlayRoate` toggles `ICmd_SetRotate(...)`; in `BaseCmd` this only sets the
  existing rotate/circle-turn RC flag (`0x08` in the short packet or byte `6`
  bit `3` in the 20-byte packet). While active, the right stick selects a
  flip/rotation direction through normal roll/pitch fields.
- `playLeftSlider`, `playRightSlider`, and `playCenterSlider` feed
  `ICmd_SetTune(...)`, which adjusts yaw/roll/pitch trim values before they are
  written into the normal RC axes.

Native string/function searches under the WiFi_CAM `libCamera.so` decompile did
not surface `ptz`, `tilt`, `servo`, `gimbal`, or similar command names. If a
WiFi_CAM-compatible drone has a physical camera tilt servo, it is not exposed by
an obvious control in this app build. A capture while using the stock app is
still the best way to verify whether any non-obvious packet changes when a tilt
control is used.

## Camera Type Probe

After sending `startCmd`, `udpSocketEnterance` waits for an 8-byte response from
the `8080` socket.

Known camera-type responses:

```text
55 00 01 00 00 00 01 99  -> camera type 1
55 00 02 00 00 00 02 99  -> camera type 2
```

The native code calls `C_Method::onNotifyCameraType(type)`, which reaches
`WiFiModelImpl.ICameraType(int)` and selects the Java command payload mode via
`BaseCmd.setCameraType(int)`.

## RC Command Path

Java builds flight packets in:

```text
decompiled-wifi-cam-6.1.8/sources/com/tzh/wifi/wificam/model/base/BaseCmd.java
```

`iCmdSend([B, int)` copies the Java byte array and calls:

```text
Socket::sendCmd(payload, length)
```

`Socket::sendCmd` sends raw bytes to `192.168.4.153:8090`.

Short 8-byte payload:

```text
index  value
0      0x66
1      roll
2      pitch
3      throttle / power
4      yaw
5      flags
6      xor checksum over bytes 1..5
7      0x99
```

Alternate 20-byte payload for camera type `2`:

```text
index  value
0      0x66
1      0x14
2      roll
3      pitch
4      throttle / power
5      yaw
6      flags group 1
7      flags group 2
8..17  reserved / zero in Java initializer
18     xor checksum over bytes 2..17
19     0x99
```

For the 8-byte payload, byte `5` flags are:

- `0x01`: one-key fly / fast fly
- `0x02`: one-key land / fast drop
- `0x04`: emergency
- `0x08`: rotate / circle turn
- `0x10`: headless mode
- `0x80`: checkout / calibration-like flag

For the 20-byte payload, bytes `6` and `7` are:

- byte `6`, `0x01`: fly and land both map here in the decompiled Java
- byte `6`, `0x02`: emergency
- byte `6`, `0x04`: checkout
- byte `6`, `0x08`: rotate / circle turn
- byte `7`, `0x01`: headless mode
- byte `7`, `0x02`: stay-high / altitude hold

## Command Response Path

`cmdSocketEnterance` listens on the `8090` command socket for 8-byte responses.
It copies each response into `recvCmd` and uses the same logic as
`parseCmdRecv(...)`:

- Read exactly 8 bytes.
- Update `prevIdx` from response byte `1`.
- Notify Java snap state with response byte `2`.
- Ignore duplicate response indexes.

The checksum expression in the decompile is awkward, but the shape is clearly an
8-byte command acknowledgement/status channel rather than CTP or JSON.

## Video Packet Format

`udpSocketEnterance` receives up to `0x5c0` bytes from the `8080` socket and
passes the packet to `Image::put(...)`.

Native reassembly behavior:

- Full UDP datagram size: `0x5c0` bytes (`1472`)
- Native packet header: 8 bytes
- JPEG slice body: `0x5b8` bytes (`1464`)
- Packet byte `0`: frame id / sequence byte
- Packet byte `1`: final-frame marker used by native code; completion requires
  this byte to equal `1`
- Packet byte `2`: total fragment count for the frame
- Packet byte `3`: resolution id forwarded to Java
- Packet byte `7`: retain/orientation value forwarded to Java
- Payload starts at byte `8`

`Image::putImgtoBuf(...)` appends each `0x5b8` payload into an internal frame
buffer. When the final chunk arrives, it scans for JPEG EOI `ff d9`, validates
that the assembled frame starts with JPEG SOI `ff d8` and ends with `ff d9`, and
calls:

```text
C_Method::onNotifyRecvState(resolution, jpeg_bytes, jpeg_len, retain)
```

Java receives this in `Camera.OnImageRecv(...)`, then forwards frame bytes to
`WiFiPresenter.onData(...)`. The app log tag says `MJPEG`, but the app boundary
is complete JPEG frame blobs.

## Comparison With Existing TurboDrone Backends

`cooingdv` is not a match:

- Uses `192.168.1.1`
- Uses UDP `7099`
- Uses RTSP `rtsp://192.168.1.1:7070/webcam`
- Wraps flight payloads with a leading `0x03`

`cooingdv_jieli` is not a match:

- Uses `192.168.8.15`
- Uses UDP `2228`
- Uses CTP envelope beginning with `CTP:`
- Uses JSON topics such as `CONTROL_MODE`, `FLYING_CTRL`, and `OPEN_RT_STREAM`
- Uses RTP/JPEG on UDP `6666` plus SDP TCP `6789`

`wifi_uav` is not a match:

- Uses `192.168.169.1`
- Uses UDP `8800` / `8801`
- Uses different native packet headers and ACK/request behavior

`s2x` is the closest structural comparison but still not a match:

- Both use a port `8080`, but S2x targets `172.16.10.1:8080`
- S2x video uses a separate UDP `8888` receiver and a `0x40 0x40` packet header
- S2x start command is `0x08 + local IPv4`, not `42 76`
- S2x RC packets are 20-byte packets sent to `8080`, not a separate `8090`
  command socket

## Recommended TurboDrone Implementation

Add a new backend family:

```text
DRONE_TYPE=wifi_cam
```

Implementation status:

- `wifi_cam` is wired as a first-pass backend in TurboDrone.
- RC supports short and extended raw command packets.
- Video supports `42 76` stream start, camera-type probing, and native JPEG
  chunk reassembly.
- Hardware validation is still needed against a WiFi_CAM-compatible device.

Suggested defaults:

```text
WIFI_CAM_DRONE_IP=192.168.4.153
WIFI_CAM_VIDEO_PORT=8080
WIFI_CAM_COMMAND_PORT=8090
```

Implementation pieces:

- `models/wifi_cam_rc.py`
  - Can reuse the CooingDV-style stick center/range initially.
  - Needs explicit support for both 8-byte and 20-byte payload modes.
- `protocols/wifi_cam_rc_protocol_adapter.py`
  - Sends raw RC packets to UDP `8090`.
  - Starts with 8-byte mode unless camera-type probe says type `2`.
  - Builds checksums exactly like `BaseCmd.java`.
- `protocols/wifi_cam_video_protocol.py`
  - Opens a UDP socket to the device.
  - Sends `42 76` to `192.168.4.153:8080` on start and `42 77` on stop.
  - Receives `0x5c0` datagrams.
  - Handles camera-type responses before frame assembly.
  - Reassembles `0x5b8` JPEG chunks using the 8-byte native header.
  - Emits complete JPEG `VideoFrame` objects.
- `main.py` / `web_server.py`
  - Add `wifi_cam` selection and env defaults.
  - Wire the video adapter and RC adapter separately because ports differ.

Open implementation question:

- Where to route the native camera type notification. The cleanest Python design
  is for the video adapter to expose the detected camera type and for
  `web_server.py` / `VideoReceiverService` to pass that into the RC adapter, or
  for the RC adapter to default to 8-byte mode with an env override such as
  `WIFI_CAM_COMMAND_MODE=short|extended`.

## Validation Plan

Packet captures should confirm:

- App sends `42 76` to `192.168.4.153:8080` at live preview start.
- Device returns one of the `55 00 xx 00 00 00 xx 99` camera-type responses.
- App sends raw `66 ... 99` RC payloads to `192.168.4.153:8090`.
- Video datagrams are `0x5c0` bytes and payload chunks assemble into JPEG frames.
- Stop/disconnect sends `42 77` to `8080`.

If captures confirm the native decompile, this should become a new `wifi_cam`
backend rather than a variant of `cooingdv_jieli`.
