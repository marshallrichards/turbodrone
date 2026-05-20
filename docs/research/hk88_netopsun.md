# HK88 / Netopsun Protocol Research

This note documents the decompiled HK88 DRONE Android app from
`decompiled-hk88-drone-1.0.8`.

## Executive Summary

HK88 DRONE should be treated as a new research family for now, not mapped to an
existing TurboDrone implementation.

Primary evidence:

- Android package: `com.netopsun.hk88drone`.
- App label: `HK88 DRONE`.
- App class: `com.netopsun.drone.MyApplication`.
- Main flight screen: `com.netopsun.drone.control_activity.ControlActivity`.
- Core control abstraction: `com.netopsun.rxtxprotocol.base.RxTxProtocol`.
- Device abstraction layer: `com.netopsun.deviceshub.DevicesHub`.

This is a broad Netopsun app stack. It can open several device backends and
several RC protocols:

- Device backends observed in this decompile: MR100, W8028, JR, XR872, FH,
  JLLW, and USB storage.
- RC protocols observed in this decompile: `HYBlueLightGPSProtocol`,
  `BlueLightGPSProtocol`, `SnapBlueLightGPSProtocol`, `DFSGPSProtocol`,
  `F200GPSProtocol`, `LWGPSProtocol`, `SimpleDroneProtocol`, and
  `OpticalFlowDroneProtocol`.

The app default is `HYBlueLightGPSProtocol`, stored in `Constants` as the default
`rxtx_protocol_name`. A recognizer can switch among HY, BlueLight, F200, and DFS
based on telemetry signatures, but this still does not line up with any current
TurboDrone backend as a whole.

## Existing Implementation Fit

HK88 is not a direct match for current TurboDrone implementations:

- Not CooingDV: no classic `192.168.1.1:7099` control plus
  `rtsp://192.168.1.1:7070/webcam` stack.
- Not WiFi_CAM: no `192.168.4.153` plus UDP `8080`/`8090`, `42 76` stream
  start, or `libCamera.so`-style command split.
- Not WiFi-UAV: no `lxPro`/`UAVSDK` dispatcher or `FLYING_CTRL`/CTP/Jieli path
  as the primary app architecture.
- Not S2x as an app family: HK88 is `com.netopsun`, not `com.vison.macrochip`.
  It carries one `OpticalFlowDroneProtocol` with a familiar `66 14 ... 99`
  control packet, but the app's default and recognizer target Netopsun's
  HY/BlueLight/F200/DFS families.

Practical implication: do not add a TurboDrone backend yet from this decompile
alone. If support is added later, it should likely start as a `netopsun_hk88` or
more specific `netopsun_hy` / `netopsun_f200` implementation after hardware
captures identify the active device/protocol combination.

## Device Selection

`DevicesUtil.initDevices(...)` selects the device backend from the phone's Wi-Fi
IP/subnet:

- `192.168.201.*` -> `mr100://`
- `192.168.208.*` -> `mr100://rtspip=192.168.208.1&rxtxmode=udp`
- `192.168.218.*` ->
  `mr100://rtspip=192.168.218.1&rxtxmode=udp&encryptvideo=false&format=auto`
- `192.168.210.*` ->
  `w8028://rtspip=192.168.210.1&rxtxmode=udp&encryptvideo=false&format=auto`
- `192.168.28.*` -> `xr872://`
- `192.168.99.*` -> `jr://`
- `172.19.*` -> `fh://baudRate=115200`
- `192.168.0.*` -> `jllw://`
- USB accessory present -> `ustorage://`

Important backend network constants:

- MR100:
  - Default IP `192.168.201.1`.
  - Command port `6699`.
  - RxTx TCP port `50000`.
  - RxTx UDP mode binds/sends on UDP `9999`.
  - RTSP path `rtsp://<ip>:<port>/H264VideoSMS`.
- W8028:
  - Default IP `192.168.210.1`.
  - Command port `6699`.
  - RxTx TCP port `50000`.
  - RxTx UDP mode binds/sends on UDP `7080`.
  - RTSP path `rtsp://<ip>/`.
- JR:
  - Default IP `192.168.99.1`.
  - UDP command port `7777`.
  - TCP command port `5000`.
  - RxTx port `1024`.
  - RTSP path `rtsp://<ip>:<port>/webcam`.
- XR872:
  - Default IP `192.168.28.1`.
  - RxTx port `7080`.
- FH:
  - Default IP `172.19.10.1`.
  - Device API port `8866`.
  - Uses `FHDEV_Net`/`FHExtraJni` native APIs.

The `resources/config.arm64_v8a.apk` split present in this unpack contains only
split metadata, not extracted `.so` files. Java references native libraries such
as `FHDEV_Net`, `FHExtraJni`, `UStorageDeviceFS`, IJK/Live555 libraries, and
OpenCV helpers, so complete native analysis will require recovering the actual
ABI split libraries.

## Protocol Selection

`Constants.getRxTxProtocolName(...)` defaults to:

```text
HYBlueLightGPSProtocol
```

`RxTxProtocolFactory.createByName(...)` can instantiate:

- `HYBlueLightGPSProtocol`
- `BlueLightGPSProtocol`
- `SnapBlueLightGPSProtocol`
- `DFSGPSProtocol`
- `F200GPSProtocol`
- `LWGPSProtocol`
- `SimpleDroneProtocol`
- `OpticalFlowDroneProtocol`

`RxTxProtocolRecognizer` probes by sending:

```text
HY request:   68 01 0d 80 80 80 80 ... checksum
F200 request: 42 54 3c 01 66 01 66
```

It classifies received byte signatures:

- `58 8b 0e` or `58 8b 0f` -> `HYBlueLightGPSProtocol`
- `58 8b 0b` -> `BlueLightGPSProtocol`
- `42 54 3e` -> `F200GPSProtocol`
- `a5 2a 1d 26` -> `DFSGPSProtocol`

## Primary HY Control Packet

`HYBlueLightGPSProtocol.notifySend()` builds a 17-byte packet:

```text
68 01 0d RR PP TT YY 20 S1 S2 S3 S4 00 00 00 00 XX
```

Known fields:

- Byte `0`: `0x68`
- Byte `1`: `0x01`
- Byte `2`: `0x0d`
- Byte `3`: roll, centered at `0x80`
- Byte `4`: pitch, centered at `0x80`
- Byte `5`: throttle/accelerator, centered at `0x80`
- Byte `6`: yaw, centered at `0x80`
- Byte `7`: constant `0x20`
- Byte `8`: speed/headless/normal-mode flags, base `0x08`
- Byte `9`: calibration/unlock/takeoff/landing/flyback/e-stop/follow flags
- Byte `10`: around/waypoint/photo/record/camera-tilt flags
- Byte `11`: rocker/test-info flags
- Bytes `12..15`: zero or extension space in this code path
- Byte `16`: XOR checksum over bytes `1..15`

Camera tilt in this packet:

- Byte `10`, bit `6` (`0x40`): camera position value is positive.
- Byte `10`, bit `7` (`0x80`): camera position value is negative.

The UI feeds this through:

```text
PTZControlSlider.onTouchMidpointChange(f)
  -> rxTxProtocol.setCameraPositionValue((-f) * 180.0f)
```

This is the clearest camera tilt/PTZ evidence found in any decompiled app so
far. It is a continuous UI slider, but HY encodes only direction as positive vs
negative one-bit states in the recurring RC packet.

## Other Tilt Encodings

`SimpleDroneProtocol` supports camera position only for the `LS_Drone` model
flag:

```text
66 RR PP TT YY FF XX 99
```

For `LS_Drone`, byte `5` includes:

- Bit `4` (`0x10`): camera position value is positive.
- Bit `5` (`0x20`): camera position value is negative.

`F200GPSProtocol` supports an analog servo-style channel in its rocker packet:

```text
42 54 3c 0c 6b RR RR PP PP YY YY TT TT CC CC dc 05 XX
```

Where:

- Bytes `5..6`: roll, little-endian PWM-like value centered near `1500`.
- Bytes `7..8`: pitch.
- Bytes `9..10`: yaw.
- Bytes `11..12`: throttle/accelerator.
- Bytes `13..14`: camera position, little-endian
  `((cameraPositionValue / 100.0) * 500) + 1500`.
- Bytes `15..16`: fixed `1500`.
- Byte `17`: XOR checksum over bytes `3..16`.

`LWGPSProtocol` overrides `setCameraPositionValue(...)`, but its `notifySend()`
does not write `cameraPositionValue` into the recovered `rockerBytes`, so no
wire-level tilt mapping is visible there.

No camera tilt use was found in `OpticalFlowDroneProtocol`, even though it uses
a 20-byte `66 14 ... 99` packet shape similar to Macrochip/S2x.

## Video / Media Notes

HK88 is mostly RTSP/Live555/IJK-driven for Wi-Fi device families:

- MR100 opens `rtsp://<device-ip>:<rtsp-port>/H264VideoSMS`.
- W8028 opens `rtsp://<device-ip>/`.
- JR opens `rtsp://<device-ip>:<rtsp-port>/webcam`.
- FH uses native `FHDEV_Net` APIs and extra JNI.
- USB storage uses `UStorageDeviceFS` / `AOADeviceCameraData`.

This is not currently compatible with TurboDrone's S2x UDP video parser,
WiFi_CAM native UDP/JPEG parser, CooingDV RTSP/UDP control pairing, or WiFi-UAV
FLD/UAV/Jieli stacks without a new backend design.

## Recommended Next Steps

For future implementation work, capture first:

- Phone IP/subnet while connected to the HK88 drone, to identify active device
  backend.
- Active `rxtx_protocol_name` after app recognition.
- RC packets while moving sticks.
- PTZ slider packets while sliding up/down.
- Video stream URL and codec.

Most promising implementation split:

- `netopsun_hy`: default HK88 path, 17-byte `68 01 0d ...` packet with tilt
  flags in byte `10`.
- `netopsun_f200`: if captures show `42 54 3c` traffic; this has the strongest
  analog camera tilt channel.
- `netopsun_simple_ls`: only if captures show short `66 ... 99` LS-style packets
  with tilt in byte `5`.

