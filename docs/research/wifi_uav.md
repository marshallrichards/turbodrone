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

K417 captures showed video fragments arrive at the ephemeral ACK socket, not at
`10010` or `10011`.

### Native Startup Packet

The startup packet is:

```text
ef 00 04 00
```

The BL618 startup path sends this repeatedly during startup.

## Video Packet Format

K417 captures and native `handle_mcu_msg_frag*()` agree on this layout:

| Offset | Size | Meaning |
| --- | ---: | --- |
| `0` | 1 | `0x93` |
| `1` | 1 | message type; `0x01` means JPEG fragment |
| `2` | 2 | total packet length, little-endian |
| `4` | 4 | message sequence / id |
| `8` | 8 | image sequence |
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
- corrected WiFi-UAV extended land/e-stop semantics
- native-shaped ACK/request packet builder
- native fragment parser
- ACK state tracking
- duplicate delivered-frame guard
- startup/request burst moved after RX thread startup

Remaining possible work:

- Full native four-slot state machine parity, if needed.
- More `wifi_uav_uav` / FLOW hardware testing.
- Proper Windows firewall documentation or setup helper.
- Frontend capability refinement: WiFi-UAV takeoff/land is really one-key
  takeoff/land, not independent commands.
