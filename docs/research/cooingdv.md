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
