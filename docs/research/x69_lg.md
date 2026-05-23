# X69 / LG Drone Protocol Research

This note documents the decompiled X69 DRONE Android app from
`decompiled-x69-drone-1.0.13`.

## Executive Summary

X69 DRONE should be treated as a separate research family for now, not mapped to
an existing TurboDrone implementation.

Primary evidence:

- Android package: `com.lg.drone`.
- App label: `X69 DRONE`.
- App class: `com.lg.drone.MyApplication`.
- Launcher: `com.lg.drone.activity.SplashActivity`.
- Main start screen: `com.lg.drone.activity.StartActivity`.
- Active flight path from the start screen: `com.lg.drone.activity.MainActivityUDP`.

The active path is not the Vison/Macrochip `s2x` app family. It does use a
familiar 20-byte `66 14 ... 99` control packet, but it sends through LG-specific
native socket code to a different network target and uses a different video
transport. Treat it as `x69_lg` / `lg_udp` research until captures prove a
closer reusable backend boundary.

TurboDrone implementation status:

- `DRONE_TYPE=x69_lg`
- RC/control implemented in:
  - `backend/models/x69_lg_rc.py`
  - `backend/protocols/x69_lg_rc_protocol_adapter.py`
- Camera tilt/servo direction bits are implemented.
- Video is implemented experimentally in:
  - `backend/protocols/x69_lg_video_protocol.py`
- The video adapter sends the native stream commands, reassembles H.265 frames
  from UDP `1234`, and pipes them through `ffmpeg` to produce JPEG frames for the
  existing MJPEG web pipeline.

## Existing Implementation Fit

Current TurboDrone fit:

- Not S2x unchanged:
  - X69 package is `com.lg.drone`, not `com.vison.macrochip`.
  - Active control host is `172.16.11.1`, not the usual S2x gateway/default
    `172.16.10.1`.
  - Control is sent by native `JNICMD` / `native_socket`, not by the Java
    Macrochip `BaseApplication.writeUDPCmd(...)` path.
  - Video is handled through `UDPCMDManage` with local UDP ports `23459` and
    `1234`, not the S2x UDP `8888` frame parser.
  - X69 uses byte `7` bits `3` and `4` for camera tilt/servo direction; those
    bits are not part of TurboDrone's current S2x semantics.
- Not CooingDV:
  - No `192.168.1.1:7099` control plus RTSP `7070` classic path.
- Not WiFi_CAM:
  - No `192.168.4.153` plus UDP `8080`/`8090`, `42 76` stream start, or
    `libCamera.so` command path.
- Not WiFi-UAV:
  - No `lxPro`/`UAVSDK` dispatcher or Jieli `FLYING_CTRL` transport.
- Not HK88/Netopsun:
  - No `com.netopsun` device/protocol abstraction; this is an LG-specific app
    with `JNICMD`, `UDPCMDManage`, `ProtocolAnalysisUtil`, and
    `TrinityProtocolUtil`.

## App Flow

Relevant activity flow:

```text
SplashActivity
  -> StartActivity
      -> MainActivityUDP
```

The manifest also includes older or alternate flight screens:

- `MainActivityNew`
- `MainActivityDecode`
- `MainActivityRTSP`
- `TrinityActivity`
- `MainActivity`

However, `StartActivity`'s main fly button launches `MainActivityUDP` directly.
The other activities are useful for shared-code clues, but `MainActivityUDP` is
the primary path for this app build.

## Active Network Shape

`MainActivityUDP` initializes native control like this:

```text
JNICMD.initUDP("172.16.11.1")
```

The app's connection check also expects the phone IP to contain:

```text
172.16.11
```

Java-side UDP video/control helper:

- `UDPCMDManage` target host: `172.16.11.1`
- local control socket: UDP `23459`
- local stream socket: UDP `1234`
- `UDPCMDTool.GetOpenOrCloseCMD(...)`: native stream open/close command
- `UDPCMDTool.GetIFrameCMD()`: native I-frame request command

`UDPCMDManage` receives stream datagrams on UDP `1234`. It expects a 32-byte
packet header beginning:

```text
c6 6c a5 5a
```

Recovered stream header fields:

- Bytes `0..3`: stream magic `c6 6c a5 5a`.
- Bytes `4..7`: little-endian frame length.
- Bytes `8..11`: little-endian frame number.
- Byte `17`: I-frame flag / frame type as consumed by Java.
- Bytes `20..21`: little-endian total packet count.
- Bytes `22..23`: little-endian packet index.
- Bytes `24..27`: little-endian payload offset.
- Bytes `28..31`: little-endian payload length.
- Bytes `32..`: video payload.

`VideoDecodeUDP` initializes Android `MediaCodec` as HEVC/H.265 in the active
path:

```text
mediacodecInit(2, 1280, 720, null, null, null)
```

So this app's active UDP video path is H.265-oriented, not S2x JPEG chunking.
TurboDrone's `x69_lg` adapter reassembles these H.265 frames and runs them
through `ffmpeg` as an HEVC bytestream. Offline testing of
A local `.h265` capture under `backend/dumps_x69/` (gitignored) decoded successfully. The live
pipeline needs normal buffering (`-fflags +genpts`) rather than the earlier
low-latency/nobuffer settings; the latter produced only the first JPEG and then
FFmpeg missed reference frames.

The backend transcodes to smaller MJPEG frames for the web UI. Defaults:

- `X69_LG_OUTPUT_WIDTH=640`
- `X69_LG_OUTPUT_FPS=15`
- `X69_LG_JPEG_QUALITY=12`

For FFmpeg's MJPEG encoder, lower `q:v` means higher quality/larger frames and
higher values mean fuzzier/smaller frames.

Native `libudpcmdtool.so` confirms the Java command-byte helpers:

- Open stream command, sent to `172.16.11.1:23459`:

  ```text
  a8 8a 20 00 08 00 00 00 01 00 02 00 00 00 d2 04
  ```

- Close stream command, sent to `172.16.11.1:23459`:

  ```text
  a8 8a 21 00 06 00 00 00 01 00 00 00 00 00
  ```

- I-frame request command, sent to `172.16.11.1:23459`:

  ```text
  a8 8a 24 00 02 00 00 00 01 00
  ```

## Active RC Packet

`MainActivityUDP` sets `f960r0 = true`, so the active RC payload is `U`, a
20-byte optical-flow packet:

```text
66 14 RR PP TT YY F1 F2 00 00 00 00 00 00 00 00 00 00 XX 99
```

Initialization in `MainActivityUDP`:

- Byte `0`: `0x66`
- Byte `1`: `0x14`
- Byte `2`: roll, centered at `0x80`
- Byte `3`: pitch, centered at `0x80`
- Byte `4`: throttle/accelerator, centered at `0x80`
- Byte `5`: yaw, centered at `0x80`
- Byte `6`: one-shot and mode flags
- Byte `7`: extended flags, including camera tilt
- Bytes `8..17`: zero in the active Java initializer
- Byte `18`: XOR checksum over bytes `2..17`
- Byte `19`: `0x99`

This shape is very close to Macrochip/S2x HY packets, but the app owns it
through LG native socket code and assigns different meaning to byte `7`.

Native `libnative_socket.so` confirms that this 20-byte payload is not sent raw.
`JNICMD.sendControlData(...)` wraps it before UDP transmit:

```text
ca 47 d5 00 14 00 00 00 <20-byte 66 14 ... 99 payload>
```

The wrapped 28-byte control datagram is sent to:

```text
172.16.11.1:23458
```

`JNICMD.SendD1()` sends a once-per-second keepalive to the same destination:

```text
ca 47 d1 00 00 00 00 00
```

Known active flag bits:

- Byte `6`, bit `1` (`0x02`): emergency stop in `MainActivityUDP.h()`.
- Byte `7`, bit `3` (`0x08`): camera tilt/servo up.
- Byte `7`, bit `4` (`0x10`): camera tilt/servo down.

Additional one-shot bits for takeoff, landing, calibration, flips, photo, and
record are present in repeated decompiled click-handler blocks, but many of
those blocks were heavily duplicated/obfuscated by JADX. Packet captures should
be used before promoting a complete flag table into implementation code.

## Camera Tilt / Servo

X69 has explicit camera servo controls in the active UI:

- `content_rtsp.xml` defines `btDGUp` and `btDGDown`.
- `MainActivityUDP.onCreate(...)` attaches touch listeners:
  - `btDGUp` -> `MainActivityUDP.n(...)`
  - `btDGDown` -> `MainActivityUDP.m(...)`

Recovered mapping:

```text
MainActivityUDP.n(activity, pressed)
  pressed:  U[7] |=  0x08
  release:  U[7] &= ~0x08
  label:    "舵机上行" / servo up

MainActivityUDP.m(activity, pressed)
  pressed:  U[7] |=  0x10
  release:  U[7] &= ~0x10
  label:    "舵机下行" / servo down
```

This is confirmed app-level camera tilt/servo support. It is momentary rather
than absolute-position based: the bit stays set while the button is pressed and
is cleared on touch release.

## Native Libraries

The decompile references these app-specific/native libraries:

- `native_socket` via `com.lg.drone.rtsp.JNICMD`
- `udpcmdtool` via `com.lg.drone.udp.UDPCMDTool`
- `protocolparse` via `com.lg.drone.ProtocolAnalysisUtil`
- `trinityprotocolparse` via `com.lg.drone.TrinityProtocolUtil`
- `mjpegdec` via `com.lg.drone.PictureAndVideoUtil`
- `yuvutil`, `ffplay-lib`, `opencv_api`, IJK, and other media helpers

Native analysis status:

- Ghidra 12.0.4 and reusable headless scripts are available under `tools/`.
- `libnative_socket.so` and `libudpcmdtool.so` were analyzed with Ghidra
  headless.
- Outputs:
  - `tools/ghidra_out/x69_libnative_socket_functions_all.txt`
  - `tools/ghidra_out/x69_libnative_socket_decompiled/`
  - `tools/ghidra_out/x69_libudpcmdtool_functions_all.txt`
  - `tools/ghidra_out/x69_libudpcmdtool_decompiled/`

Remaining native follow-ups:

- `libprotocolparse.so` / `libtrinityprotocolparse.so`: alternate protocol
  packet wrappers and whether they share the same servo bits as `MainActivityUDP`.
- Additional H.265 tuning if live testing shows latency or reference-frame
  issues on other firmware revisions.

## Alternate / Legacy Paths

The app includes several alternate paths:

- `MainActivityRTSP` and `MainActivityNew` carry similar control arrays and
  older RTSP/decoder paths.
- `TrinityActivity` uses `TrinityProtocolUtil.initUDPSocket("172.16.11.1")` and
  `trinityprotocolparse`.
- `ProtocolAnalysisUtil` exposes native methods for `sendControlDataXL`,
  `sendOpticalFlowDataCMD`, follow/circle/point data, and parsing.

These paths reinforce that X69 belongs to an LG/native protocol family. They
should not be treated as separate TurboDrone backends until hardware captures
show which one is active for a given drone/firmware.

## Recommended Next Steps

For implementation work later, capture:

- Repeating 20-byte `66 14 ... 99` control packets while idle and while moving
  each stick.
- `btDGUp` and `btDGDown` press/release packets to verify byte `7` bits `3` and
  `4` on real hardware.
- Takeoff, landing, calibration, photo, record, and flip packets to complete the
  flag table.
- Longer video captures from multiple flights to tune buffering/latency and
  confirm that the 32-byte `c6 6c a5 5a` header remains stable.
- `libprotocolparse.so` and `libtrinityprotocolparse.so` details for alternate
  app paths if those modes prove active on other firmware.

Backend name selected: `x69_lg`.

