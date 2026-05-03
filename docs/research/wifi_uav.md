# WiFi-UAV Protocol Research

This note captures findings from the decompiled WiFi-UAV Android app in
`wifi-uav-app-decompiled` and from native analysis of
`wifi-uav-app-decompiled/resources/lib/arm64-v8a/libuav_lib.so`.

The main takeaway is that "WiFi-UAV" is a drone family, not one protocol.
The app routes different SSID families to different backend SDKs.

## App Backend Variants

The app uses `defpackage.d00` as a dispatcher. It maps SSID prefixes onto two
backend families:

```java
put("FlOW_", f.Uav);
put("FLOW_", f.Uav);
put("WIFI_", f.Fld);
put("GD89Pro_", f.Fld);
put("WTECH-", f.Fld);
put("WTECH_", f.Fld);
```

The dispatcher then binds those backend enum values to concrete implementations:

```java
put(f.Fld, wz.X());
put(f.Uav, e00.i0());
```

Observed / inferred mapping:

| SSID prefix | App backend | Java class | Native dependency | Notes |
| --- | --- | --- | --- | --- |
| `WIFI_` | `Fld` | `defpackage.wz` | `com.lxProLib.lxSigPro` / `lxPro` | Classic WiFi-UAV path. |
| `GD89Pro_` | `Fld` | `defpackage.wz` | `com.lxProLib.lxSigPro` / `lxPro` | Same backend as `WIFI_`. |
| `WTECH-`, `WTECH_` | `Fld` | `defpackage.wz` | `com.lxProLib.lxSigPro` / `lxPro` | Same backend as `WIFI_`. |
| `FLOW_`, `FlOW_` | `Uav` | `defpackage.e00` | `com.example.sdk.UAVSDK` / `libuav_lib.so` | Native UAVSDK backend. |
| `DRONE_` | Not in app map | Turbodrone maps to `fld` | Appears K417-compatible with `fld` wire behavior | Added from K417 testing. |

## App Call Graph

The main flight screen is `com.lcfld.fldpublic.ActCtrl`. It owns:

- `d00 W = d00.Y()` as the selected drone backend.
- `xx X = new xx()` as the RC packet builder.

Control flow:

```text
ActCtrl
  -> d00 dispatcher
      -> wz / lxSigPro for Fld devices
      -> e00 / UAVSDK / libuav_lib.so for FLOW/Uav devices
  -> xx packet builder
      -> short 8-byte command for Fld-style control
      -> extended 20-byte command for UAV/FLOW when supported
```

`d00.g()` starts every registered backend, not just the currently selected one.
The selected backend is changed by successful callbacks:

- `wz` / `lxSigPro` connection state `5` calls `e0(f.Fld)`.
- `e00` posts a connected callback after MCU version data arrives and calls
  `e0(f.Uav)`.

`d00.h(byte[])` is the main command forwarding point. It sends the current RC
packet only to the active backend.

`ActCtrl` starts its own worker thread in `onCreate()`. The thread calls
`P1()` about every `50 ms`, updates PTZ visibility about once per second, and
also drives UI effects such as roll animation and water-ripple rendering.

The Android app version in the analyzed manifest is:

```text
versionName=2024.11.08
versionCode=135
package=com.lcfld.fldpublic
```

## Fld Backend

`defpackage.wz` wraps `com.lxProLib.lxSigPro`:

```java
public class wz extends tz {
    public lxSigPro d = lxSigPro.getInstance();
}
```

Important methods:

```java
public int g() { return this.d.Connect(0); }
public int h(byte[] bArr) { return this.d.DataForward(bArr, 0); }
public int i() { return this.d.DisConnect(); }
public int p() { return this.d.StPlay(0); }
public int q() { return this.d.StStop(); }
```

Implications:

- `Fld` has explicit connect / data-forward / disconnect / start-play /
  stop-play lifecycle in the app.
- Turbodrone does not call `lxSigPro`; it reconstructs the wire behavior in
  Python.
- K417 (`DRONE_*`) appears to use a wire path compatible with this family.

Additional `Fld` callbacks:

- `onStreamCbk()` forwards decoded video frames from `lxSigPro`.
- `onSrlDataCbk()` forwards serial/control data from the drone.
- `onCfgCbk()` forwards config responses.
- `onUpdateFwCbk()` forwards firmware update progress.

`wz.k()` initializes `lxSigPro` with `SetMid(1)`, `UidsInit(new int[]{0})`,
and `AStRecType = 0`.

`lxPro` loads `lxffmpeg` and `lxPro`. Ghidra analysis of
`resources/lib/arm64-v8a/liblxPro.so` shows this is a separate native stack
from `libuav_lib.so`.

Important `lxPro` native wrappers used by the app:

| Java call | Native wrapper | App use |
| --- | --- | --- |
| `Connect(0)` | `ntvConnectInt()` | Start FLD connection. |
| `DataForward(bytes, 0)` | `ntvDataForward()` | Forward RC bytes. |
| `DisConnect()` | `ntvDisConnect()` | Stop FLD connection. |
| `StPlay(0)` | `ntvStPlay()` | Start video stream. |
| `StStop()` | `ntvStStop()` | Stop video stream. |
| `SdCapture(1)` | `ntvSdCapture()` | Ask drone-side SD/photo capture. |
| `SdRecord(boolean)` | `ntvSdRecord()` | Ask drone-side SD/video record. |
| `SetCfg(json)` | `ntvSetCfg()` | Configure WiFi SSID and other SDK JSON commands. |

### Native FLD / lxPro Findings

`liblxPro.so` is an ARM64 ELF with DWARF/debug info. The relevant compile units
include:

- `lgProIntface/lxPro.c`
- `lgProIntface/lxProJni.c`
- `lgProSrc/lxProtocol.c`
- `lgProSrc/lgProDev.c`
- `lgPublicSrc/lxFFmpeg.c`

`lgCreate()` allocates a `0xa30` byte device context, creates command locks and
stats queues, initializes check/command/stream sockets to empty state, creates
an audio player, and starts `lgThreadTimming()`. The native version log in this
library is:

```text
v1.0.0(20201022)
```

`Connect(0)` flows through:

```text
Java_com_lxProLib_lxPro_ntvConnectInt()
  -> lgConnect()
  -> lgConnectPort(dev, ip, 0x49c1)
```

`0x49c1 == 18881`. If the app passes IP `0`, `lgConnectPort()` defaults to:

```text
192.168.100.1:18881
```

That is different from the `libuav_lib.so` / BL608/BL618 transport, which uses
`192.168.169.1:8800` and `:8801`.

`lgConnectPort()` starts the FLD control/check path:

- creates `0x400000` byte buffers for command and check sockets
- configures the check socket as TCP
- starts `lgThreadCmdParse`
- starts `lgThreadCekClient`

`lgThreadCekClient()` calls `lgOnSocketResv()` on the check socket. The socket
logic uses Java-configured connection cycle/timeout values, with minimums of
`500 ms` cycle and `100 ms` connect timeout.

The FLD command parser accepts native packets with:

```text
start marker: f5 e2 e3 cb
end marker:   e3 a5 cb cc
```

`lgPackCmdSend()` builds this envelope:

| Offset | Size | Meaning |
| --- | ---: | --- |
| `0` | 4 | start marker `f5 e2 e3 cb` |
| `4` | 4 | `DgCmdId_e` command id |
| `8` | 4 | payload size |
| `12` | var | payload |
| `12 + payload_size` | 4 | end marker `e3 a5 cb cc` |

`DataForward(bytes, 0)` is not a length bug. JNI ignores the Java-side `0`
for length, obtains the actual byte-array length, and calls:

```c
lgDataForward(dev, data, array_length, isTcp);
```

With `isTcp == 0`, `lgDataForward()` selects UDP and sends:

```text
lgPackCmdSend(dev, eDgSrlOspf, rc_bytes, rc_len, eSckTypeUdp)
```

So the short/extended `xx` RC bytes are nested inside the FLD native command
envelope as an `eDgSrlOspf` payload.

`lgSendCJsonData()` creates JSON and sends it as:

```text
lgPackCmdSend(dev, eDgCmdJson, json_with_trailing_nul, len + 1, eSckTypeTcp)
```

Examples from native decompilation:

- `lgStPlay(Rel)` sends JSON with `cmd`, `StRelIdx=Rel`, and `vopen=1`, then
  starts stream threads.
- `lgStStop()` sends JSON with `cmd` and `vopen=0`, then starts a delayed
  stream-thread destroy path.
- `lgSdRecord(start)` sends JSON with `cmd` and `record=(start != 0)`.
- `lgGetCfg(Kid)` sends JSON with only `cmd=Kid`.
- `lgSetCfg(json)` forwards the Java JSON string directly through `lgSetCfg()`
  and logs the result.

`lgStartStThread()` creates a `5,000,000` byte stream buffer, initializes video
and audio packet lists, then starts:

- `lgThreadStClient`
- `lgStDecodeThread`
- `lgVideoDecodeThread`
- `lgAudioDecodeThread`

`lgThreadStClient()` receives stream socket data through `lgOnSocketResv()` and
registers `onStRecvCbk()` for stream receive stats. `lgVideoDecodeThread()`
creates an H.264 FFmpeg decoder and dispatches packet payloads based on a byte
at packet offset `0x0f`; decoded output eventually reaches the Java
`lgStreamCbk()` / `onStreamCbk()` path as `lgFrameInFo`.

FLD stream packets use a separate stream frame marker:

```text
a5 a5 ef cc
```

`lgGetCompleteOneFrame()` searches for that marker, requires a `0x14` byte
stream header, then expects one of these end markers after `Size + 0x14`:

```text
e3 a5 cb cc
a5 a5 ef cc
```

Bad/misaligned frames increment `BadFrameCount` and advance the ring-buffer
read pointer. This is separate from the UAVSDK `0x93 0x01` JPEG-fragment
transport.

FLD decode path:

- stream bytes are buffered by `lgOnSocketResv()`
- complete stream frames are parsed by `lgGetCompleteOneFrame()`
- video packets are queued into `VStList`
- `lgVideoDecodeThread()` pops video packets
- packet byte `0x0f` selects a decoder entry in `lxAVDcMap`
- decoded H.264 output is copied to Java preview buffers by
  `lxGeneratePreview()`

`lxGeneratePreview()` lays out preview YUV as planar Y, U, V:

```text
Y plane: offset 0, size w*h
U plane: offset w*h, size (w/2)*(h/2)
V plane: offset w*h*5/4, size (w/2)*(h/2)
```

So `FrameType == 2` on the Java side is consistent with planar YUV420 output
from the FLD FFmpeg decode path.

Implication: the FLD backend is not just a raw `xx` packet UDP sender. It is a
full P2P-ish native protocol with TCP JSON/check traffic, UDP serial forwarding,
and a separate H.264-oriented stream decode pipeline.

`lxPro.lgFrameInFo` is the common Java frame envelope for FLD and UAV video:

| Field | Meaning |
| --- | --- |
| `FrameBuf` | Frame bytes. JPEG for `FrameType == 1`; YUV420p-like bytes for `FrameType == 2`. |
| `FrameType` | App dispatches `1` as JPEG bitmap and `2` as YUV data. |
| `W`, `H` | Frame dimensions. |
| `FrameNum`, `FrameRate`, `Pts`, `DisplayMs`, `StType`, `UserId`, `RecTimes` | Metadata forwarded by native SDK. |

## Uav / FLOW Backend

`defpackage.e00` wraps `com.example.sdk.UAVSDK`:

```java
public class e00 extends tz implements UAVSDK.DataListener {
    public UAVSDK f = UAVSDK.getInstance();
}
```

Important methods:

```java
public int g() {
    if (this.n) return 0;
    this.n = true;
    this.f.nativeStart();
    return 0;
}

public int h(byte[] bArr) {
    this.f.nativeSendCtlMsg(bArr, bArr.length);
    return 0;
}

public int i() {
    this.q = 0L;
    this.h.f();
    this.o = false;
    this.p = true;
    if (this.n) {
        this.n = false;
        this.f.nativeStop();
    }
    return 0;
}
```

`UAVSDK` loads:

```java
System.loadLibrary("uav_lib");
System.loadLibrary("upcnn-cpu");
if (Build.VERSION.SDK_INT >= 24) {
    System.loadLibrary("upcnn-gpu");
}
```

`UAVSDK` exposes JNI methods including:

```java
nativeCreate();
nativeDestroy();
nativeGetVersion();
nativeInit();
nativeSendCtlMsg(byte[] data, int len);
nativeSendCustomMsg(byte[] data, int len);
nativeSetCameraIndex(int index);
nativeSetCameraRotate180(int value);
nativeSetQPara(int q1, int q2, int t1, int t2);
nativeStart();
nativeStop();
```

### Java UAV Lifecycle

`e00.k()` initializes the native layer:

```java
this.g.h();
this.f.nativeInit();
this.f.setDataListener(this);
g0();
```

`nativeInit()` caches JNI callback method IDs for:

- `cbJpegFromNative([BJBI)V`
- `cbCtlMsgFromNative([BJ)V`
- `cbUpdateFromNative(II)V`
- `cbTrackFromNative(I[F)V`

The native SDK version logged by this build is:

```text
V2.2.1 20240428
```

`e00.g()` calls `nativeStart()` once. `e00.i()` clears connection state and
calls `nativeStop()` if the native backend is running.

The app's UAV liveness check is stricter than "socket exists":

```java
public boolean u() {
    return this.o && System.currentTimeMillis() - this.q < 1500;
}
```

`o` becomes true after a recognized MCU version/control message. `q` is updated
by `handleJpeg()`, so the Java app considers the UAV backend connected only
while JPEG frames are arriving.

`e00.handleJpeg()` wraps native JPEG bytes into `lxPro.lgFrameInFo` through
`d00.e()`:

```java
lgframeinfo.FrameType = 1;
lgframeinfo.FrameBuf = bArr;
```

The native callback's `quality` and `is_normal_pic` parameters are not copied
into `lgFrameInFo` by the Java bridge, so `ActCtrl` sees the same frame shape
for UAV JPEGs that it sees for FLD JPEGs.

### Java UAV Control Messages

`e00.handleCtlMsg()` interprets native control callbacks:

| Native payload | Java effect |
| --- | --- |
| `[1, 101, ...]` | MCU version string. Parses board/capabilities, marks UAV connected, and probes extra commands when supported. |
| `[1, 103, ...]` | SSID/config response. Parses scene/camera information. |
| `[1, 105]` | MCU busy. |
| `[1, 106]` | MCU disconnected. Clears version/state and posts a disconnect. |

`e00.l` parses version strings into:

- board family, resolution token, firmware version, build date, and extra flags
- flow-device markers: `FLOW...` / `(FLOW)...`
- no-flow marker: `(NOFLOW)...`
- extended command support when the parsed build date is `>= 20211218`
- optional `I=<hex>` image/capability bitfield

The Java custom-command helpers are string based:

| Java method | Custom payload string |
| --- | --- |
| `Q()` | `cmd=2` |
| `P()` | `cmd=3` |
| `W()` | `cmd=4` |
| `T(scene)` | `cmd=<scene << 8 | 1>` |
| `k0(imgfunc)` | `imgfunc=<hex>` |
| `o(ssid)` | `<i=2^bf_ssid=<ssid>>` |

These are wrapped as custom native messages, not as joystick bytes.

### UAV Capability Bitfield

`e00.j` parses the optional `I=<hex>` capability field from the MCU version
string. It stores nibbles and flags as:

| Bits | Java field | Observed app use |
| --- | --- | --- |
| `0..3` | `b` | Mirror/camera command value used by `E(true)` / main camera. |
| `4..7` | `c` | Mirror/camera command value used by `E(false)` / flow camera. |
| `8..11` | `d` | Scene/current camera-ish capability. |
| `12..15` | `e` | Resolution selector for flow/secondary camera. |
| `16..19` | `f` | Resolution selector for main/primary camera. |
| `20..23` | `g` | Extra image capability nibble. |
| `24..27` | `h` | Extra image capability nibble. |
| `28` | `i` | Camera/mirror behavior flag. |
| `29` | `j` | Camera/mirror behavior flag. |
| `30` | `k` | Front/back camera support flag; `x()` returns true when `k == 1`. |

`e00.z()` means the `I=<hex>` field exists. `e00.y()` means custom image
commands are supported, scene/camera state is `1`, and front/back camera
support is not already active.

## Native UAVSDK Findings

`libuav_lib.so` is an ARM64 ELF shared object. It is not stripped and contains
debug info, so Ghidra headless analysis is useful.

Exports of interest:

- `Java_com_example_sdk_UAVSDK_nativeStart`
- `Java_com_example_sdk_UAVSDK_nativeStop`
- `Java_com_example_sdk_UAVSDK_nativeSendCtlMsg`
- `Java_com_example_sdk_UAVSDK_nativeSendCustomMsg`
- `mjpeg_ndk_start`
- `mjpeg_ndk_stop`
- `mjpeg_ndk_command_send`
- `mjpeg_ndk_custom_cmd_send`
- `mjpeg_ndk_start_bl618`
- `mjpeg_ndk_stop_bl618`
- `mjpeg_ndk_command_send_bl618`
- `mjpeg_ndk_custom_cmd_send_bl618`
- `handle_mcu_msg_frag`
- `handle_mcu_msg_frag_bl618`
- `build_send_ack`
- `build_send_ack_bl618`

### Native Start Behavior

`nativeStart()` starts two internal native backends:

```c
context = mjpeg_ndk_start("192.168.169.1", "8800", NULL);
mjpeg_ndk_frame_callback_register(context, callback_jpeg, context);
mjpeg_ndk_ctlmsg_cb_register(context, callback_ctlmsg, context);
mjpeg_ndk_track_set_sdk(context, sdk);
mjpeg_ndk_track_callback_register(context, callback_track, context);

context_bl618 = mjpeg_ndk_start_bl618(NULL, "192.168.169.1", "8801");
mjpeg_ndk_frame_callback_register_bl618(context_bl618, callback_jpeg, context_bl618);
mjpeg_ndk_ctlmsg_cb_register_bl618(context_bl618, callback_ctlmsg, context_bl618);
mjpeg_ndk_track_set_sdk_bl618(context_bl618, sdk);
mjpeg_ndk_track_callback_register_bl618(context_bl618, callback_track, context_bl618);
```

Implications:

- Native UAVSDK probes both the normal path and the BL618 path.
- Normal backend targets `192.168.169.1:8800`.
- BL618 backend targets `192.168.169.1:8801`.
- Turbodrone's `wifi_uav_uav` mode now mirrors this by sending RC and video
  startup/request traffic to both ports.

### Native Socket Setup

Normal `create_instance()`:

- creates an ACK/socket bound to `0.0.0.0` on an ephemeral local port
- sets MCU target to `192.168.169.1:8800`
- creates a side UDP socket using `NetworkSocket_Create(Network_UDP, 0x271a)`
- `0x271a == 10010`

BL618 `create_instance_bl618()`:

- creates an ACK/socket bound to `0.0.0.0` on an ephemeral local port
- sets MCU target to `192.168.169.1:8801`
- creates a side UDP socket using `NetworkSocket_Create(Network_UDP, 0x271b)`
- `0x271b == 10011`
- logs the ephemeral ACK socket with `getsockname()`

K417 captures showed video fragments arrive at the ephemeral ACK socket, not at
`10010` or `10011`.

The native build strings in the analyzed library are:

- normal path: `BL608_V20240426`
- BL618 path: `BL618_V20240426`

### Native Startup Packet

The startup packet is:

```text
ef 00 04 00
```

Both native paths send this repeatedly during startup until receive state is
established.

Normal timer behavior:

- before first frame/control receive, sends the startup packet about every
  `> 100 ms`
- after receiving data, sends ACK/request packets about every `> 24 ms`
- if no activity for about `3001 ms`, emits a two-byte callback and resets
  native receive state

BL618 timer behavior:

- before first receive, sends the startup packet about every `> 200 ms`
- after receiving data, sends ACK/request packets about every `> 50 ms`
- only sends an ACK packet when at least one ACK slot is present
- has an extra device-config update path that packages SSID/channel/user bytes
  with the marker string `oGMcOfyZdIurm2kS`

### Native Command Queueing

`nativeSendCtlMsg(byte[], len)` does not immediately `sendto()` the joystick
packet. It copies commands shorter than `65` bytes into each backend's
`user_msg_ctx`:

```c
mjpeg_ndk_command_send(context, data, len, &seq);
mjpeg_ndk_command_send_bl618(context_bl618, data, len, &seq);
```

Normal `mjpeg_ndk_command_send()` accepts commands only when:

- context is non-null and alive
- command length is `<= 64`
- backend is enabled
- `has_received != 0`

BL618 is similar but allows `<= 128` bytes at the lower native layer. The JNI
wrapper still limits `nativeSendCtlMsg()` to `< 65` bytes.

The queued command is embedded into the next ACK/request packet:

- `user_msg_ctx.seq`
- `user_msg_ctx.length`
- up to `64` bytes of user command data

`nativeSendCustomMsg()` is different. It wraps the payload in an immediate
custom packet:

```text
ef 20 <len:u16 little-endian> <custom-payload...>
```

but it still requires the backend to be enabled and to have received data.

There are native JNI declarations for camera index, rotation, and quality
parameters:

```java
nativeSetCameraIndex(int index);
nativeSetCameraRotate180(int value);
nativeSetQPara(int q1, int q2, int t1, int t2);
```

Ghidra export of these functions confirms:

- `nativeSetCameraIndex(index)` fans out to both BL608 and BL618:
  `mjpeg_ndk_set_active_camera_index(context, index)` and
  `mjpeg_ndk_set_active_camera_index_bl618(context_bl618, index)`.
- `nativeSetCameraRotate180(value)` fans out to both tracking pipelines:
  `mjpeg_ndk_track_set_rgb_rotate_180*()`.
- `nativeSetQPara(q1, q2, t1, t2)` updates only the normal/BL608 context in
  this exported function: `mjpeg_ndk_set_QPara(context, ...)`.

Their effects are visible in exported state:

- `build_send_ack*()` places quality bytes and `active_cam_idx` into every
  ACK/request packet.
- `handle_mcu_msg_frag()` uses `active_cam_idx` to choose whether main-camera
  or flow-camera status is passed to the JPEG callback.
- Java calls `nativeSetCameraIndex(0)` on stream start for UAV and
  `nativeSetCameraIndex(z ? 1 : 0)` for camera switching.

`handle_mcu_msg_ack_bl618()` is present, but decompiles to a no-op apart from
stack checking. BL618 type `0x02` ACK messages are recognized by the receive
thread but ignored in this build.

`callback_jpeg()` has one important backend-selection behavior: once either the
normal context or BL618 context produces JPEG frames, it stops the other
context. This is how the dual-probe `nativeStart()` collapses to the working
backend at runtime.

`callback_ctlmsg()` attaches to the JVM, copies native bytes into a Java
`byte[]`, and calls `cbCtlMsgFromNative`. The native callback carries the MCU
sequence; Java's decompiled `UAVSDK` then forwards the byte array to
`e00.handleCtlMsg()`.

## Video Packet Format

K417 captures and native `handle_mcu_msg_frag*()` agree on this layout:

| Offset | Size | Meaning |
| --- | ---: | --- |
| `0` | 1 | `0x93` |
| `1` | 1 | message type; `0x01` means JPEG fragment |
| `2` | 2 | total packet length, little-endian |
| `4` | 4 | message sequence / id |
| `8` | 8 | image sequence |
| `16` | 8 | observed duplicate/secondary sequence; K417 captures match image sequence, exported native frag handler does not read this field |
| `24` | 8 | last-finished / acked-ish sequence field |
| `32` | 4 | fragment index |
| `36` | 4 | fragment count |
| `40` | 4 | frame body length |
| `44` | 2 | width |
| `46` | 2 | height |
| `48` | 1 | quality |
| `52` | 1 | main camera status |
| `53` | 1 | flow camera status |
| `56+` | var | JPEG payload fragment |

Observed K417 traffic:

- drone sends from `192.168.169.1:1234`
- PC receives on the ephemeral socket used to send ACK/request packets
- typical packet length: `1088` bytes
- quality: `50`
- about `10-19` fragments per frame
- about `15 fps` in a working capture

Short capture validation from `captures/k417_wifi_uav_fld.pcapng` and
`captures/k417_wifi_uav_live_after_parser.pcapng`:

- outbound flow: `192.168.169.2:<ephemeral> -> 192.168.169.1:8800`
- inbound flow: `192.168.169.1:1234 -> 192.168.169.2:<ephemeral>`
- startup packets: `ef 00 04 00`
- request packets alternate between `88` and `124` byte `ef 02` packets
- `ef 20` custom packets were not present in these short captures
- inbound fragments were `0x93 0x01`, usually `1080` bytes each
- observed frame header values: `640x360`, quality `50`, fragment count `20`
- the 124-byte request tail decodes as two ACK slots, for example:

```text
seq=9  status=1  len=20  bitmap=ff ff ff ff
seq=9  status=3  len=16
```

Those slots match the current Turbodrone fallback/request behavior and the
native ACK slot layout.

## ACK / Request Packet Format

Native `build_send_ack()` and `build_send_ack_bl618()` emit this broad shape:

| Offset | Size | Meaning |
| --- | ---: | --- |
| `0` | 1 | `0xef` |
| `1` | 1 | `0x02` |
| `2` | 2 | packet length, little-endian |
| `4` | 4 | constant `02 02 00 01` |
| `8` | 1 | ACK slot count |
| `9` | 3 | padding |
| `12` | 4 | queued user-command sequence |
| `16` | 2 | queued user-command length |
| `18` | 64 | queued user-command data |
| `82` | 1 | quality1 |
| `83` | 1 | quality2 |
| `84` | 1 | q_threshold1 |
| `85` | 1 | q_threshold2 |
| `86` | 1 | active camera index |
| `87` | 1 | padding |
| `88+` | var | ACK slot records |

Each ACK slot:

| Offset | Size | Meaning |
| --- | ---: | --- |
| `0` | 8 | image sequence |
| `8` | 4 | status |
| `12` | 4 | slot record length |
| `16+` | var | optional fragment ACK bitmap |

Status values inferred from native:

- `0`: receiving / partial
- `1`: complete / delivered
- `2`: dropped
- `3`: future/request slot

Turbodrone now generates native-shaped ACK packets and tracks in-flight frame
state using `WifiUavAckState`.

### Native Frame State Machine

The native receiver uses four frame slots:

```c
slot_idx = (image_sequence + 3) & 3;
```

Internal native slot statuses are distinct from the ACK status values:

| Internal status | Meaning | ACK status emitted |
| --- | --- | --- |
| `0` | empty / unused | none or future slot |
| `1` | receiving fragments | `0` |
| `2` | all fragments received, ready to deliver | `1` |
| `3` | delivered | `1` |
| `4` | dropped / skipped | `2` |

For a new frame, `handle_mcu_msg_frag()`:

- updates `last_finished` from the header's offset `24` field
- updates `max_recv_seq`
- initializes the slot's fragment count, body length, width, height, and
  quality
- records main/flow camera status from offsets `52` and `53`
- initializes a fragment ACK bitmap and sets the received fragment bit
- copies payload from offset `56` into the frame buffer

When all fragments are present, the frame moves to the native image queue. The
queue has three entries but keeps at most two queued frames; if it is full, the
oldest queued frame is dropped before adding the next one.

The native `thread_ctl` then drains queued frames into Java/native callbacks:

- normal path sleeps roughly `38 ms` per loop, with an extra `19 ms` wait when
  no frame is queued
- BL618 path sleeps roughly `16 ms` per loop
- both paths also call `UPUAVSDK_UpdateJPEGData()` for the tracking pipeline

BL618 adds a frame-drop/recovery path that the normal BL608 path does not show
in the exported decompilation. If no frame was delivered and the image queue is
empty, BL618 can mark an in-progress frame at `seq_to_deliver` as dropped
(`status = 4`) so later complete frames can advance.

### Native Control Callback Format

Native `thread_recv()` accepts only packets with:

- byte `0`: `0x93`
- bytes `2..3`: packet length matching the datagram size

Message type `0x01` is JPEG fragment data. Message type `0x04` is MCU/control
data.

For MCU/control packets, native code forwards:

- payload pointer: `data + 0x0c`
- payload length: little-endian `uint16` at offset `8`
- sequence: little-endian `uint32` at offset `4`

There are special cases for photo/record callbacks with 9-byte payloads shaped
like `<p....>` or `<r....>` plus XOR checksum. These are collapsed into
two-byte Java callbacks so the Java layer sees `UAV_Flight_Ctl_Picture` or
`UAV_Flight_Ctl_Record`.

## Control Packet Semantics

The app has two control builders:

- `xx.f()` short 8-byte layout
- `xx.g()` extended 20-byte layout

Turbodrone embeds the extended layout (`66 14 ...`) in the longer `ef 02 ...`
packet wrapper.

In `xx.g()`, takeoff and land share the same one-key bit:

```java
bArr[6] = (takeoff ? 1 : 0)
        | (land    ? 1 : 0)
        | (stop    ? 2 : 0)
        | (gyro    ? 4 : 0)
        | (roll    ? 8 : 0)
        | ((ptz & 3) << 6);
```

Meaning for Turbodrone's current WiFi-UAV extended command layout:

| Action | Byte 6 bit |
| --- | ---: |
| takeoff / land one-key action | `0x01` |
| emergency stop | `0x02` |
| gyro/calibration | `0x04` |
| flip/roll | `0x08` |

K417 testing confirmed:

- app land button descends gracefully
- Turbodrone previously mapped land to `0x02`, causing motor cutoff
- Turbodrone now maps both takeoff and land to `0x01`, and e-stop to `0x02`

### App Control Loop Details

`ActCtrl.P1()` is the app's recurring RC send loop. It runs only when:

```java
this.W.u() && this.W.f() == 1
```

For the UAV backend, `f()` always returns `1`. For the FLD backend, `f()` is
`lxSigPro.AppCtrlSt()`.

When the on/off control is disabled, the app sends a neutral FLD-style packet a
few times:

```java
{ 0x66, 0x80, 0x80, 0x80, 0x80, 0x40, 0x40, 0x99 }
```

For the UAV backend, after having sent active controls, it also sends an
eight-byte all-zero packet once when turning controls off.

During active control, `ActCtrl` fills `xx` from the UI:

| `xx` field | Source |
| --- | --- |
| `a` | `getTrSliderYpercent()` or hand/track override |
| `b` | `getTrSliderXpercent()` or hand/track override |
| `c` | `getEaSliderXpercent() + getPathPercentX()` or trim override |
| `d` | `getEaSliderYpercent() + getPathPercentY()` or trim override |
| `e/f/g/h` | trim/tuning sliders |
| `i` | up / one-key takeoff flag |
| `j` | down / one-key land flag |
| `k` | stop flag |
| `l` | roll/flip flag |
| `m` | back flag |
| `n` | headless flag |
| `o` | gyro/check flag |
| `p` | high/low mode flag |
| `q` | hand-flow active |
| `r` | tracking active |
| `s` | speed index |
| `v` | PTZ up/down state; likely camera tilt servo in practice |

The app chooses the packet shape with:

```java
int extended = (this.W.d0() && this.W.L()) ? 1 : 0;
byte[] packet = extended != 0 ? this.X.g() : this.X.f();
```

So `xx.g()` is used only for the UAV backend when the version string says this
is a FLOW device. Otherwise the app uses the short `xx.f()` packet.

Both packet builders use an XOR checksum:

- short packet: XOR bytes `1..5` into byte `6`, terminator `0x99`
- extended packet: XOR bytes `2..17` into byte `18`, terminator `0x99`

The app also parses a serial/status packet in `xx.j()`:

```text
88 00 <fly-state> <battery> <flags> ... <xor> 55
```

The status flags byte exposes speed, RC-control support, PTZ support,
headless/photo/video/light flags, and is forwarded through `xx.a`.

### RC Packet Layouts

`xx.f()` short packet:

| Offset | Meaning |
| --- | --- |
| `0` | Constant `0x66`. |
| `1` | Rudder / yaw axis: `h(c, g, s, true)`. |
| `2` | Elevator / pitch axis: `h(d, h, s, true)`. |
| `3` | Throttle axis: `h(a, e, 2, p)`. |
| `4` | Aileron / roll axis: `h(b, f, s, true)`. |
| `5` | Button bitfield. |
| `6` | XOR checksum over bytes `1..5`. |
| `7` | Terminator `0x99`. |

Short packet byte `5`:

| Bit | Java source | Meaning |
| ---: | --- | --- |
| `0x01` | `i` / `getUpBtnState()` | Takeoff/up. |
| `0x02` | `j` / `getDownBtnState()` | Land/down. |
| `0x04` | `k` / `getStopBtnState()` | Stop. |
| `0x08` | `l` / `getRollBtnState()` | Flip/roll. |
| `0x10` | `n` / `getHeadlessBtnState()` | Headless. |
| `0x20` | `m` / `getBackBtnState()` | Back/return. |
| `0x40` | `p` / `getHlBtnState()` | High/low or throttle-center mode. |
| `0x80` | `o` / `getGyoCheckBtnState()` | Gyro/calibration/check. |

`xx.g()` extended packet:

| Offset | Meaning |
| --- | --- |
| `0` | Constant `0x66`. |
| `1` | Constant length `0x14`. |
| `2` | Rudder / yaw axis: `h(c, g, s, true)`. |
| `3` | Elevator / pitch axis: `h(d, h, s, true)`. |
| `4` | Throttle axis: `h(a, e, 2, p)`. |
| `5` | Aileron / roll axis: `h(b, f, s, true)`. |
| `6` | Primary button/PTZ bitfield. |
| `7` | Secondary mode bitfield. |
| `8..17` | Zero in this app build. |
| `18` | XOR checksum over bytes `2..17`. |
| `19` | Terminator `0x99`. |

Extended packet byte `6`:

| Bits | Java source | Meaning |
| ---: | --- | --- |
| `0x01` | `i` or `j` | Shared one-key takeoff/land action. |
| `0x02` | `k` | Emergency stop. |
| `0x04` | `o` | Gyro/calibration/check. |
| `0x08` | `l` | Flip/roll. |
| `0xc0` | `v << 6` | PTZ up/down state; likely tilt up/down. |

Extended packet byte `7`:

| Bit | Java source | Meaning |
| ---: | --- | --- |
| `0x01` | `n` | Headless. |
| `0x02` | `p` | High/low or throttle-center mode. |
| `0x04` | `r` | Person tracking active. |
| `0x80` | `q` | Hand-flow active. |

Axis scaling uses `xx.h(float f, float trim, int speed, boolean centered)`.
Speed indexes map to:

| Speed index | Scale |
| ---: | ---: |
| `0` | `0.30` |
| `1` | `0.60` |
| `2` | `1.00` |
| `3` | `0.25` |

For centered axes, neutral is approximately `127.5`, stick movement is
`(f - 0.5) * scale * 255`, and trim adds `(trim - 0.5) * 63`.

For non-centered throttle mode, the app uses `f * scale * 255` plus the same
trim term. In practice `xx.f()` and `xx.g()` pass `p` as the throttle
`centered` argument, so high/low mode also changes throttle centering behavior.

### UI Button To Command Map

`lxCtrlView` switches between `lxFldCtrlView` and `lxUavCtrlView`. Both expose
the same `lxBasicView` state getters, but their visible controls differ.

`lxFldCtrlView` mappings:

| UI control | Getter / field | RC effect |
| --- | --- | --- |
| `takeoff_nor` button | `getUpBtnState()` / `m` | Short packet bit `0x01`. |
| `landing_nor` button | `getDownBtnState()` / `n` | Short packet bit `0x02`. |
| `Stop` button | `getStopBtnState()` / `o` | Short packet bit `0x04`. |
| `roll360` button | `getRollBtnState()` / `l` | Short packet bit `0x08`; XY roll direction can override axis byte. |
| `nohead` button | `getHeadlessBtnState()` / `F` | Short packet bit `0x10`. |
| `hl` button | `getHlBtnState()` / `w` | Short packet bit `0x40`; also hides takeoff/land/stop/roll when off. |
| `checkout` button | `getGyoCheckBtnState()` / `G` | Short packet bit `0x80`. |
| `record` button | `getRecordBtnState()` / `s` | Local recording state; also `ActCtrl.f()` starts/stops local record. |
| `photo` button | calls `ActCtrl.q()` | Triggers local snapshot path. |
| `speed` button | `getSpeedBtnState()` / `M` | Cycles speed index `0..2`. |
| `path` / gyro / mirror / VR | view state | Affects axes, rendering, or mode bits where applicable. |

`lxUavCtrlView` mappings:

| UI control | Getter / field | RC/custom effect |
| --- | --- | --- |
| `btn_flight_mode` | `getOnoffBtnState()` / `r` | Enables periodic RC sending. |
| takeoff/land shared button | `getUpBtnState()` and `getDownBtnState()` / `S` | Extended packet shared one-key bit `0x01`. |
| `btn_stop` | `getStopBtnState()` / `s` | Extended packet e-stop bit `0x02`. |
| `roll360` | `getRollBtnState()` / `t` | Extended packet roll bit `0x08`; XY roll direction can override axis bytes. |
| `btn_gyocheck` | `getGyoCheckBtnState()` / `I` | Extended packet gyro bit `0x04`. |
| `btn_headless_mode` | `getHeadlessBtnState()` / `J` | Extended packet byte `7` bit `0x01`. |
| `btn_body` / hand-flow | `getHandFlowState()` / `D` | Extended packet byte `7` bit `0x80`; starts/stops palm tracking through `nativeStartPalmTrack()` / `nativeStopPalmTrack()`. |
| person-flow button | `r` flag | Extended packet byte `7` bit `0x04`; starts person tracking through `nativeStartPersonTrack(x,y)`. |
| PTZ slider | `getPtzUpDnState()` / `B` | Extended packet byte `6` bits `6..7`: `1` down/one tilt direction, `2` up/other tilt direction, `0` neutral. |
| `btn_hvcam` | `getHvCamBtnState()` / `v` | Triggers custom command sequence through `W()`, `P()`, and `Q()` depending on capability state. |
| `btn_scene` | scene state / `w.j` | Calls `T(scene)` when scene capability is known, otherwise probes with `Q()`. |
| front/back camera button | `setFbCamBtnState()` | Calls `ActCtrl.R()`, which uses `W.W()` when supported. |
| camera switch | `getSwCamBtnState()` / `k` | Calls `e00.t(z)`, which sets `nativeSetCameraIndex(z ? 1 : 0)`. |
| record/photo/speed/mirror/VR/scale | view state or `ActCtrl` callbacks | Local record/snapshot/render controls plus possible SDK custom commands. |

PTZ / Camera Tilt Note:

```java
getPtzUpDnState() == 0 -> neutral
getPtzUpDnState() == 1 -> extended byte 6 bits 6..7 = 01b
getPtzUpDnState() == 2 -> extended byte 6 bits 6..7 = 10b
```

The app labels this as PTZ, but the decompiled UI only exposes an up/down
state. Based on observed toy drone hardware, this should be treated first as a
camera tilt servo command, not full pan/tilt/zoom:

- no pan axis has been identified in the Java UI or native command path
- no optical zoom command has been identified
- any "zoom" seen in the app is likely software/render zoom through
  `lxEglView` scaling, not a drone-side camera command
- the likely hardware action is camera pitch/tilt up or down

The app only samples this tilt/PTZ value into `xx.v`; it does not send a
separate custom PTZ message. Therefore Turbodrone tilt support should be
implemented as a persistent or momentary field in the extended `66 14 ...` RC
command for UAV/FLOW-style devices. FLD views report no PTZ state in the
decompiled app, even though some hardware may expose camera tilt through other
SDK-specific paths.

The click handlers call `lxBtn.e()`, which toggles the selected state and
records the selection timestamp. The main RC loop then samples the selected
states on its next `P1()` tick.

### Photo And Record Paths

There are two separate concepts:

- local phone snapshot/recording through `lxEglView`
- drone-side SD capture/record commands through the backend SDK

Local snapshot:

```text
ActCtrl.g2()
  -> choose output file under lxConfig.ePhotoFolder
  -> choose resolution through d00.Z(...)
  -> lxEglView.snapshot(width, height, 1, jpg_path)
  -> W.l(1)
```

For `Fld`, `W.l(1)` maps to `wz.l(1)` and then `lxSigPro.SdCapture(1)`.
For `Uav`, `e00.l()` returns `-1`, so the local snapshot is the effective
behavior unless a native photo callback arrives.

Local recording:

```text
ActCtrl.c2()
  -> W.m(true)
  -> lxEglView.startARecord(width, height, mime_or_profile, mp4_path, false, cb)
  -> lxEglView.snapshot(..., mp4_path + ".pic")
```

`lxEglView.startARecord()` creates a Java hardware encoder (`zz`) and passes
the encoder surface to native `lxEglView.ntvStartRec()`. If the preferred
resolution fails with `-2`, the app retries `4096x2160`, `3840x2160`,
`2560x1440`, `1920x1080`, then `1280x720`.

For `Fld`, `W.m(true/false)` maps to `lxSigPro.SdRecord(boolean)`. For `Uav`,
`e00.m()` returns `-1`, so local MP4 recording is the effective behavior.

Backend callbacks can also toggle UI photo/record state:

- FLD JSON config callback keys `lgDevCbkPic` and `lgDevCbkRec`.
- UAV serial/control callbacks `[0, 113]` for picture and `[0, 114]` for
  record.
- UAV nested command `[0, 102, ..., status]` with status `2` for picture and
  `4` for record.

### Video Feed Rendering Path

All backend video frames converge at `ActCtrl.V(tz, lxPro.lgFrameInFo)`.

For `FrameType == 1`:

```text
FrameBuf JPEG bytes
  -> BitmapFactory.decodeByteArray(...)
  -> lxEglView.set(Bitmap)
  -> lxEglView.requestRender()
```

The app may rotate JPEG frames before rendering:

- small frames (`min(width,height) < 320`) from a backend reporting
  `tz.v() == true` are rotated `-90` unless BRoll rendering is active
- custom UAV camera/mirror state can add another `+90`
- mirror state is synchronized through `a2()`

For `FrameType == 2`:

```text
FrameBuf YUV bytes
  -> lxEglView.set(byte[], width, height)
  -> native ntvSetYuv420p(...)
  -> requestRender()
```

`lxEglView` is a native OpenGL surface wrapper:

- creates native state with `ntvCreate(LXLIB_SIGKEY)`
- sends surface lifecycle into `ntvSurfaceCreated/Changed/Destroyed`
- auto-renders from an internal thread by calling `ntvRequestRender()`
- draws bitmap frames through `ntvSetBitmap()`
- draws YUV frames through `ntvSetYuv420p()` or `ntvSetYuv()`
- handles mirror, rotate, roll, scale, VR/split-screen, filters, snapshots, and
  recording in native `lxEglView`

This means Turbodrone should treat decoded frame assembly separately from app
rendering: the app's transport delivers JPEG/YUV frame payloads, and
`lxEglView` handles presentation, local capture, and MP4 encoding.

## K417 Notes

Observed K417 SSID:

```text
DRONE_4C8172
```

This prefix is not present in the decompiled app's dispatcher, but testing shows
it is compatible with the `fld`-style wire path:

```env
DRONE_TYPE=wifi_uav_fld
```

Working capture summary:

- inbound: `192.168.169.1:1234 -> 192.168.169.2:<ephemeral>`
- outbound: `<ephemeral> -> 192.168.169.1:8800`
- `4527` video packets in about `20s`
- `295` frame sequences
- `294` complete frames
- approximately `15 fps`

Windows Firewall can block inbound video because the drone replies from UDP
source port `1234`, not from `8800`. Packet capture may show traffic even if
Python does not receive it. During testing, disabling firewall allowed Python
to receive and assemble frames.

## Turbodrone Implementation State

Current related files:

- `backend/protocols/wifi_uav_rc_protocol_adapter.py`
- `backend/protocols/wifi_uav_video_protocol.py`
- `backend/utils/wifi_uav_packets.py`
- `backend/utils/wifi_uav_ack_state.py`
- `backend/utils/wifi_uav_variants.py`

Implemented:

- `DRONE_TYPE=wifi_uav`, `wifi_uav_fld`, `wifi_uav_uav`
- best-effort SSID mapping
- `DRONE_` maps to `fld`
- `wifi_uav_uav` probes `8800` and `8801`
- internal WiFi-UAV capability profiles for `fld` and `uav`
- corrected WiFi-UAV extended land/e-stop semantics
- WiFi-UAV speed tier field (`speed_index`) using the app's speed scale table
- native-shaped ACK/request packet builder
- native fragment parser
- ACK state tracking
- duplicate delivered-frame guard
- startup/request burst moved after RX thread startup

Recommended implementation cleanup:

- Split WiFi-UAV RC packet builders by variant instead of using the extended
  UAV/FLOW packet shape for every WiFi-UAV device.
- Keep `wifi_uav_uav` / FLOW on the native-shaped `ef 02` ACK/request packet
  with embedded extended `66 14 ...` command.
- Treat `wifi_uav_fld` / K417 as the empirically working compatibility path,
  but document that the stock app's native FLD stack actually wraps RC bytes in
  the `f5 e2 e3 cb ... e3 a5 cb cc` `eDgSrlOspf` envelope and targets
  `192.168.100.1:18881`.
- Add explicit model fields for:
  - `flip_flag`
  - `camera_tilt_state` / `ptz_state` (`0`, `1`, `2`) with the UI wording
    biased toward "tilt" unless hardware proves full PTZ
  - `camera_index` or camera-switch command
- Add frontend controls for `speed_index` and camera tilt once the hardware
  behavior is tested.
- Build the extended command bytes from the documented `xx.g()` structure
  rather than from fixed packet constants, then pass that command into
  `build_native_ack_packet()`.
- Consider a capability object per WiFi-UAV variant so the frontend can show:
  - one-key takeoff/land vs independent takeoff/land
  - camera tilt available or not
  - camera-switch available or not
  - FLOW/UAV dual-port probing vs FLD/K417 single-port behavior

Remaining possible work:

- Full native four-slot state machine parity, if needed.
- More `wifi_uav_uav` / FLOW hardware testing, especially PTZ and camera
  switch behavior.
- Proper Windows firewall documentation or setup helper.
- Frontend capability refinement: WiFi-UAV takeoff/land is really one-key
  takeoff/land, not independent commands.

## Completeness Assessment

The app-level map is now strong for:

- Java UI-to-RC mapping.
- `xx.f()` and `xx.g()` command byte layouts.
- `d00` backend dispatch and lifecycle.
- UAVSDK / `libuav_lib.so` startup, command queueing, ACK/request, fragment
  parsing, and Java callback flow.
- App rendering, local snapshot, and local recording behavior.
- K417 `DRONE_*` capture behavior for the FLD-compatible wire path.

The remaining unknowns require artifacts not currently present in this
workspace, or another hardware/capture pass:

| Gap | Why it matters | What would close it |
| --- | --- | --- |
| Deeper `lxPro` packet decode functions | `lgPackCmdSend()` and top-level parser are mapped, but individual `DFuntc` decoders behind `lxCmdMaps` still need function-pointer/xref work. | Export/decompile the `lxCmdMaps` targets or inspect them in the saved Ghidra project. |
| Native rodata constants referenced as `DAT_*` in Ghidra output | Startup/timeout bytes are known from captures for `ef 00 04 00`, but not every timeout/status string/constant is byte-exact from the export snippets. | Ghidra data export or direct binary string/rodata inspection. |
| Real FLOW/UAV hardware capture | Current hardware captures are K417/`DRONE_*` FLD-compatible. | PCAP from `FLOW_` or `FlOW_` hardware, especially ports `8800` and `8801`. |
| Takeoff vs land UI distinction in `lxUavCtrlView` | Decompiled Java shows both `getUpBtnState()` and `getDownBtnState()` returning the same field; behavior matches one-key action, but original intent is ambiguous. | Runtime test or cleaner decompilation/original unobfuscated source. |

So the current map is complete enough to implement and debug the observed K417
path, model the UAVSDK transport shape, and understand the major FLD/lxPro
native architecture. The remaining gaps are narrower: exact FLD decoder
callbacks behind `lxCmdMaps`, byte-exact rodata constants, and FLOW hardware
captures.
