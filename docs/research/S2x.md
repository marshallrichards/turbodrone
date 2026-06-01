# Research for the S2x drones (S20, S29, PL FPV, REDRIE FLY, LOILEY FLY)

## Chipset

The S20 and S29 boards seem to use the [XR872AT](https://jlcpcb.com/partdetail/MACHINEINTELLIGENCE-XR872AT/C879208)
MCU, a Cortex-M4 ARM processor. The likely firmware SDK family is
https://github.com/XradioTech/xradio-skylark-sdk.

## App family

These drones belong to the `com.vison.macrochip` Android app family. Confirmed
apps so far:

- HiTurbo FPV: `com.vison.macrochip.hiturbo.fpv`, decompiled at
  `decompile-s2x-hiturbo-app`.
- PL FPV: `com.vison.macrochip.pl.fpv`, version `1.1.5`, decompiled at
  `decompiled-pl-fpv-1.1.5`.
- REDRIE FLY: `com.vison.macrochip.inporsa.fly`, version `1.0.5`,
  decompiled at `decompiled-redrie-fly-1.0.5`.
- LOILEY FLY: `com.vison.macrochip.loiley.fly`, version `1.0.3`,
  decompiled at `decompiled-loiley-fly-1.0.3`.
- Ruko Drone: `com.vison.macrochip.ruko.drone`, version `1.7.6`,
  decompiled at `decompiled-ruko-drone-1.7.6`.
- Ruko GIM: `com.vison.macrochip.sj.ruko.gim`, version `1.0.5`,
  decompiled at `decompiled-ruko-gim-1.0.5` (F11GIM3 gimbal drone).

PL FPV is compatible with TurboDrone's existing `s2x` implementation. A
Plegble PL-1515 that lists PL FPV in its guidebook was flown successfully with
`DRONE_TYPE=s2x`: RC controls, video, takeoff, land, and e-stop all worked.

REDRIE FLY should also be treated as part of the Macrochip/S2x app family, not
as a new TurboDrone implementation. Its package, app base classes, network
constants, VNDK bridge, video heartbeat, and HY RC packet builder all line up
with the existing S2x research, and the project README already lists a Redrie
X29 as tested with `DRONE_TYPE=s2x`. The notable caveat is that this app carries
both the current 20-byte HY packet builder and an older 8-byte Macrochip packet
builder; see "REDRIE FLY notes" below.

## Network shape

- Device target is the phone's Wi-Fi gateway. TurboDrone's default remains
  `172.16.10.1`, but app code uses the DHCP gateway rather than a hard-coded
  address.
- RC/control is UDP to port `8080`.
- Video is UDP on port `8888`.
- The app also opens TCP `8888` for some Macrochip variants, but the working
  S2x path is the UDP video path.
- There is an auxiliary UDP receive socket on `8081` in newer PL FPV / REDRIE
  base library code.

Video start/keepalive is a five-byte UDP command sent to port `8080`:

```text
08 <local-ipv4-byte0> <local-ipv4-byte1> <local-ipv4-byte2> <local-ipv4-byte3>
```

HiTurbo's `UdpRequestVideo` sends this every 1000 ms. PL FPV's and REDRIE's
`StreamUdpConnection` send the same shape every 1000 ms. TurboDrone currently
sends the same start payload every 2000 ms, which has worked on tested drones.

## RC packet

The stock apps use the 20-byte "HY" control packet for this family:

```text
66 14 RR PP TT YY F1 F2 00 00 00 00 00 00 00 00 00 00 XX 99
```

- Byte `0`: start marker `0x66`.
- Byte `1`: packet length/value `0x14`.
- Byte `2`: roll.
- Byte `3`: pitch.
- Byte `4`: throttle.
- Byte `5`: yaw.
- Byte `6`: one-shot flags.
- Byte `7`: mode/status flags.
- Bytes `8..17`: zero.
- Byte `18`: XOR of bytes `2..17`.
- Byte `19`: end marker `0x99`.

Observed flag bits:

- Byte `6`, bit `0`: one-key fly/land. Both takeoff and land use this same bit
  in the inspected HiTurbo and PL FPV code.
- Byte `6`, bit `1`: emergency stop.
- Byte `6`, bit `2`: calibration.
- Byte `6`, bit `3`: roll/flip in the inline HiTurbo thread variant.
- Byte `7`, bit `0`: headless.
- Byte `7`, bit `1`: always set by both inspected apps.
- Byte `7`, bit `2`: record state.
- Byte `7`, bit `3`: "rocker" UI/control bit.

TurboDrone has historically sent byte `7 = 0x0a` by default. Both inspected app
paths build `0x02` plus optional bits, but `0x0a` has worked on real S2x and
PL-1515 hardware. Treat byte `7` as a possible variant knob if a drone flies but
has odd mode behavior.

### REDRIE FLY notes

The REDRIE FLY decompile maps to the same Macrochip/S2x implementation:

- Android package: `com.vison.macrochip.inporsa.fly`.
- App label: `REDRIE FLY`.
- Main app class: `com.vison.macrochip.w.fpv.app.MyApplication`.
- Wi-Fi target: Android DHCP gateway, stored as `BaseApplication.hostIp`.
- RC/control sends through `BaseApplication.writeUDPCmd(...)` to UDP `8080`.
- Video setup references stream port `8888`, and `StreamUdpConnection` sends the
  same five-byte `08 <local-ipv4>` video heartbeat every 1000 ms.
- `MsgUdpReceiveConnection` binds the auxiliary UDP receive socket on `8081`.
- JNI bridge is still `com.vison.sdk.VNDK` loading `vison_main`, matching the
  Macrochip native video stack naming used by PL FPV.

The 20-byte HY path is in
`decompiled-redrie-fly-1.0.5/sources/com/vison/macrochip/w/fpv/rx/consumer/HyControlConsumer.java`.
It builds the same packet shape as TurboDrone's `s2x` adapter:

```text
66 14 RR PP TT YY F1 F2 00 00 00 00 00 00 00 00 00 00 XX 99
```

HY flag mapping in REDRIE FLY:

- Byte `6`, bit `0`: one-key fly. No separate HY land field is visible in this
  class.
- Byte `6`, bit `1`: emergency stop.
- Byte `6`, bit `2`: calibration.
- Byte `7`, bit `0`: headless.
- Byte `7`, bit `1`: always set.
- Byte `7`, bit `2`: record state.
- Byte `7`, bit `3`: rocker/control mode.

The app also contains an older 8-byte builder in
`decompiled-redrie-fly-1.0.5/sources/com/vison/macrochip/w/fpv/rx/consumer/ControlConsumer.java`:

```text
66 RR PP TT YY FF XX 99
```

Short-packet flag mapping:

- Byte `5`, bit `0`: one-key fly.
- Byte `5`, bit `1`: one-key land.
- Byte `5`, bit `2`: emergency stop.
- Byte `5`, bit `3`: roll/flip, emitted for about 10 control ticks after the
  right stick leaves center.
- Byte `5`, bit `4`: headless.
- Byte `5`, bit `6`: always set.
- Byte `5`, bit `7`: calibration.

The current TurboDrone `s2x` adapter implements the 20-byte HY path, which is
the path that matches tested S2x/PL hardware. The short 8-byte REDRIE builder is
best documented as a Macrochip legacy variant for now, not a reason to split
REDRIE FLY into a new backend. Add a variant knob only if a REDRIE-branded drone
is observed to ignore HY packets but respond to the short packet on UDP `8080`.

REDRIE's `MyApplication` sets `isHy = true` when it receives a 10-byte frame
starting with `0x66` over either TCP or UDP and then parses it through
`DataParse`. The decompiled output references `ControlActivity` in the manifest
and startup flow, but that activity source is missing from
`decompiled-redrie-fly-1.0.5/sources`; the exact runtime switch between
`ControlConsumer` and `HyControlConsumer` is therefore not visible in this pass.

### LOILEY FLY notes

LOILEY FLY is another OEM skin on the same Macrochip/S2x stack as REDRIE FLY and
PL FPV. Treat it as **`DRONE_TYPE=s2x`**, not a new TurboDrone backend.

App identity:

- Package: `com.vison.macrochip.loiley.fly`
- Version: `1.0.3` / `versionCode=3`
- App label: `Loiley Fly`
- Application: `com.vison.macrochip.w.fpv.app.MyApplication`
- Flight UI: `com.vison.macrochip.w.fpv.activity.ControlActivity` (present in
  this decompile, unlike REDRIE FLY 1.0.5)
- Decompile: `decompiled-loiley-fly-1.0.3/`

#### Family comparison

| Family | Match? | Notes |
|--------|--------|-------|
| **S2x / Macrochip** | **Yes** | Same `BaseApplication` ports, DHCP gateway target, `08` video heartbeat, 20-byte HY RC on UDP `8080` |
| **REDRIE FLY** | **Yes** | Same `w.fpv` package tree, `MyApplication.isHy`, `HyControlConsumer` / `ControlConsumer` sources, ST3 `sendFlowParam` |
| **PL FPV** | **Partial** | Same RC/network constants; video decode uses **FHSDK** here instead of `vison_main` / `VNDK` |
| **Ruko Drone** | **Partial** | Shares ST gimbal `FF 53 54` family; default RC is still 20-byte HY (not Ruko's HACK_FLY `68 01 0D` path) |
| **fld_pro / wifi_uav / cooingdv / rxdrone** | **No** | Different app publishers and transport stacks |

#### Network and RC

Same Macrochip network constants as other `w.fpv` OEM apps:

- Target: phone Wi-Fi DHCP gateway → `PlayInfo.targetIpAddr` /
  `BaseApplication.mDevAddr` (typically `172.16.10.1`)
- RC/command UDP: `8080` via `BaseApplication.writeUDPCmd(...)`
- Command UDP receive: `8081` (`DEV_UDP_PORT2`)
- Video stream port constant: `8888` (`DEV_TCP_PORT2`); TCP `8888` or UDP
  depending on `PlayInfo` device profile
- Video start/keepalive (UDP `8080`): `08 <local-ipv4×4>` every 1000 ms
  (`UdpRequestVideo`)

**Runtime RC path:** `ControlActivity.SendHuiYuanThread` builds and sends the
20-byte HY packet every **80 ms** (~12.5 Hz):

```text
66 14 RR PP TT YY F1 F2 00 00 00 00 00 00 00 00 00 00 XX 99
```

Source:
`decompiled-loiley-fly-1.0.3/sources/com/vison/macrochip/w/fpv/activity/ControlActivity.java`
(inner class `SendHuiYuanThread`).

HY flag mapping in the live thread (matches TurboDrone `s2x` adapter):

- Byte `6`, bit `0`: one-key fly (`toFlyValue`). Voice commands for fly/land
  also pulse this bit; land reuses fly, not a separate land bit.
- Byte `6`, bit `1`: emergency stop (`stopValue`)
- Byte `6`, bit `2`: calibration (`calibrationValue`)
- Byte `6`, bit `3`: roll/flip (`rollValue`) — present in `SendHuiYuanThread`
  but **not** in the co-located `HyControlConsumer.java` for this app
- Byte `7`, bit `0`: headless
- Byte `7`, bit `1`: always set (`| 2`)
- Byte `7`, bit `2`: record state
- Byte `7`, bit `3`: rocker/control mode

`HyControlConsumer` and `ControlConsumer` still exist under
`com.vison.macrochip.w.fpv.rx.consumer`, but **no references** to them appear
in this 1.0.3 decompile. They look like leftover RxJava builders from an older
control loop; the wired path is `SendHuiYuanThread` only.

The legacy 8-byte builder in `ControlConsumer.java` is the same REDRIE shape:

```text
66 RR PP TT YY FF XX 99
```

`MyApplication` sets `isHy = true` when a **10-byte** frame starting with
`0x66` arrives over TCP or UDP (`DataParse`), same as REDRIE FLY.

#### Video stack difference (FHSDK vs VNDK)

Unlike PL FPV / REDRIE FLY 1.0.5, this build decodes video through **FHSDK**
(`com.fh.lib.FHSDK`, native libs `FHDEV_Net`, `FHComponent`, `main`) in
`BaseFilterActivity`, not `com.vison.sdk.VNDK` / `vison_main`.

- `ControlActivity` extends `BaseFilterActivity` and uses OpenGL +
  `FHSDK.startPlay()` for the main preview path.
- When `PlayInfo.udpDevType == 7`, the app switches to **IJKPlayer** RTSP
  (`PlayInfo.RTSPUrl`) instead of the FHSDK GL path.
- TurboDrone's `s2x` video path (UDP `8888` + JPEG/H264 reassembly) is still
  the right RC companion; if a Loiley-branded drone only exposes RTSP, video may
  need a separate mode knob — RC on UDP `8080` should remain the same HY stream.

JNI present but secondary to flight video: `detector-lib` (gesture/object
detection via `JNIManage`), `pocketsphinx_jni` (voice control).

#### ST3 gimbal / lens switch

`MyApplication.sendFlowParam(cmd, param)` emits UDP:

```text
FF 53 54 33 <cmd> <param>
```

(`ST3` variant of the Macrochip `FF 53 54` gimbal family documented for S2x.)

Observed UI wiring in `ControlActivity`:

- On create: `sendFlowParam(18, 40)`
- Lens switch button: `sendFlowParam(18, 25)` when toggling dual-lens mode

This is the same ST-command family used in `experimental/s2x/s2x_ptz_helper.py`
for tilt probes on other Macrochip hardware. Auto ST3 sweep (includes values 25
and 40 for this param): see `experimental/s2x/README.md` — Quick start ST3 sweep.

#### Extra OEM features (not separate protocols)

Loiley-specific UI on top of the shared stack:

- Gesture mode (`GesOnSubscribe` / `btn_gestures`) feeding YUV into detection
- Voice commands (`VoiceUtils`, PocketSphinx)
- In-app music playback (`MusicUtils`)
- VR mode, photo filters, gravity-control mode
- Dual-lens switch (`btn_switch_lens`)

None of these change the underlying HY RC framing; they add parallel command
bytes or UI-side stick injection.

#### TurboDrone mapping

| Concern | LOILEY FLY | TurboDrone `s2x` |
|---------|-------------|------------------|
| RC packet | 20-byte HY on UDP `8080` | Same |
| Video heartbeat | `08 <phone-ipv4>` on UDP `8080` | Same (2 s interval in TurboDrone vs 1 s in app) |
| Video decode | FHSDK / optional RTSP | UDP `8888` native path |
| Gimbal/lens | `FF 53 54 33` via `sendFlowParam` | Use `s2x_ptz_helper.py` ST probes if needed |

#### Key source paths

| Topic | Path under `decompiled-loiley-fly-1.0.3/` |
|-------|-------------------------------------------|
| Manifest | `resources/com.vison.macrochip.loiley.fly.apk/AndroidManifest.xml` |
| Ports / `writeUDPCmd` | `sources/com/vison/baselibrary/base/BaseApplication.java` |
| Video heartbeat | `sources/com/vison/baselibrary/thread/UdpRequestVideo.java` |
| Live HY RC thread | `sources/com/vison/macrochip/w/fpv/activity/ControlActivity.java` (`SendHuiYuanThread`) |
| Alternate HY builder (unused) | `sources/com/vison/macrochip/w/fpv/rx/consumer/HyControlConsumer.java` |
| Legacy 8-byte builder (unused) | `sources/com/vison/macrochip/w/fpv/rx/consumer/ControlConsumer.java` |
| FHSDK video | `sources/com/vison/baselibrary/base/BaseFilterActivity.java` |
| ST3 commands | `sources/com/vison/macrochip/w/fpv/app/MyApplication.java` |

### Ruko Drone 1.7.6 notes

Ruko Drone is another `com.vison.macrochip` OEM app (publisher 纬盛 / Vison,
世季 SJ base library). It shares the Macrochip network stack and ST gimbal
protocol with PL FPV / REDRIE FLY, but its **default RC path is not the
20-byte `66 14 ... 99` packet** that TurboDrone's `s2x` backend sends.

App identity:

- Package: `com.vison.macrochip.ruko.drone`
- Version: `1.7.6` / `versionCode=76`
- Application: `com.vison.macrochip.app.MyApplication` → `SJBaseApplication`
- Launcher: `com.vison.macrochip.activity.WelcomeActivity`
- Flight UI: `ControlHyActivity` when `protocol == HACK_FLY` (default),
  else `ControlActivity`
- Decompile: `decompiled-ruko-drone-1.7.6/`

#### Family comparison

| Family | Match? | Notes |
|--------|--------|-------|
| **S2x / Macrochip** | **Yes** | Same `BaseApplication` ports, `vison_main` JNI, `08` video heartbeat, `FF 53 54` ST gimbal |
| **fld_pro / HACK_FLY** | **Partial** | Default RC is 17-byte `68 01 0D` via `LGDataUtils`, same shape as FLD Pro `hm.d()` |
| **cooingdv** | **No** | No UDP `7099`, no `03 66 ... 99` packets |
| **wifi_uav** | **Partial** | Command port `8080` overlaps; framing and video ports differ |
| **rxdrone / hk88** | **No** | Different stacks |

#### Network and video

Same Macrochip network constants as other S2x apps:

- Target: phone Wi-Fi DHCP gateway → `BaseApplication.hostIp` (typically
  `172.16.10.1`)
- RC/command UDP: `8080` (or `8088` for FF3519/Hisi-style frames)
- Command UDP receive: `8081` (`MsgUdpReceiveConnection`)
- Video stream: TCP or UDP port `8888` (`STREAM_PORT` / `DEV_TCP_PORT`)
- Video start/keepalive (UDP `8080`): `08 <local-ipv4×4>` every 1000 ms
  (`StreamUdpConnection`)
- Msg keepalive (UDP `8080`): `09 <local-ipv4×4>` every 1000 ms
  (`MsgUdpConnection`)

Transport modes are selected per device in `DeviceInfoManager` / `PlayInfo`:

| Mode | Path | Decode |
|------|------|--------|
| **UDP** (common S2x path) | `StreamUdpConnection` on `8888` + `08` heartbeat | `VNDK` + H264/H265/JPEG parsers (`VideoStreamHandle`) |
| **TCP** | `StreamTcpConnection` on `8888` | Same native decode stack |
| **RTSP** | `rtsp://172.16.10.1:554/livestream/12` (`RTSPClient`) | RTSP pull + app decoders |
| **USB** | `MsgUsbConnection` | Same handlers |

Native libraries (from Java `System.loadLibrary`, `.so` not in decompile tree):

- `vison_main` — video decode (`com.vison.sdk.VNDK`)
- `LGDataUtils` — HACK_FLY control encode/decode (`com.vison.macrochip.sdk.LGDataUtils`)
- `rtmp_live`, `detector-lib` — live stream / vision helpers

The UDP JPEG chunk format (`0x40 0x40` header, `##` trailer) documented under
"Native S2x UDP video parser" still applies when `PlayInfo.is872()` is true.

#### Protocol auto-detection

`SJBaseApplication` switches `protocol` based on inbound frames:

| Magic | Protocol | Detection site |
|-------|----------|----------------|
| `5A 5F` | `SJ` (世季) | `onTcpReceiveData` |
| `68` (`0x58` wire) | `HACK_FLY` (黑飞) | `onTcpReceiveData` |
| `FF 53 54` | ST / PTZ side channel | `onUdpReceiveData` / TCP |
| (implicit) | `FEI_SHA` (飞沙) | Used when not HACK_FLY |

Startup default: `ProtocolEnum.HACK_FLY` (`SJBaseApplication.java` L69).
`WelcomeActivity` routes to `ControlHyActivity` for HACK_FLY, `ControlActivity`
otherwise.

#### RC control — three parallel packet families

**A) HACK_FLY (default) — 17-byte native HY packet**

`SendHyControlThread` (`com.sj.baselibrary.thread.SendHyControlThread`) sends
every **100 ms** (control + 12-byte extend packet):

```text
68 01 0D <13-byte LGDataUtils.convertHyControl payload> <xor>
```

- Byte `0`: `0x68`
- Byte `1`: `0x01`
- Byte `2`: `0x0D` (13)
- Bytes `3..15`: native-encoded `LGControlHyBean` fields
- Byte `16`: XOR of bytes `1..15`

Extend packet (sport mode, sky/far/spiral fly, emergency RTH):

```text
68 0B 08 <8-byte convertExtend payload> <xor>
```

`LGControlHyBean` fields exposed to Java (`LGControlHyBean.java`): `rocker1..4`
(default **128** center), trims, `autoTakeoff`, `autoLand`, `goHome`, `stop`,
`lockUnlock`, `followMe`, `circleFly`, `PTZ_H`, `PTZ_V`, `VisionFollow`, etc.

In this decompile, outbound sticks are **mostly neutral** (`rocker1..3 = 128`);
only `rocker4 = rotate*2` and go-home point overrides change. Mode buttons drive
`BaseControlThread` flags. Physical RC stick positions appear to come back via
telemetry (`sjHyInfo9BBean`) for UI display only.

**Important:** No `66 14 ... 99` builder exists anywhere in the Ruko Java sources.
This is the same 17-byte `68 01 0D` family documented in `fld_pro.md`, not the
20-byte packet TurboDrone's `s2x` adapter currently sends. Treat Ruko hardware as
**unverified** on `DRONE_TYPE=s2x` until a capture confirms which packet shape
the board accepts.

**B) FEI_SHA (飞沙) — 12/14-byte control packet**

`SendControlThread` sends every **80 ms** when `protocol != HACK_FLY`:

```text
5A 55 08 02 <flags> 7F 7F 80 <rotate*2> 20 20 <xor>
```

| Offset | Value | Meaning |
|--------|-------|---------|
| 0–1 | `5A 55` | FEI_SHA magic |
| 2 | `08` | payload length |
| 3 | `02` | control subcommand |
| 4 | flags | bit0 takeoff, bit1 land, bit2 goHome, bit7 stop |
| 5–7 | `7F 7F 80` | stick channels (fixed neutral in app) |
| 8 | `rotate*2` | yaw from follow/home logic |
| 9–10 | `20 20` | trim placeholders |
| 11 | XOR | bytes 2–10 |

Lock/surround variant adds bytes 11–12 and XOR at byte 13 (14-byte packet).

**C) ST / PTZ side channel — `FF 53 54` prefix**

Sent on UDP `8080` (most commands) or TCP `8888` via `writeTCPCmd` for tilt set
on non-Hisi boards. Prefix: `FF 53 54` ("ST") + command byte `[3]` + payload.

#### Camera tilt / PTZ (confirmed in Ruko)

Unlike REDRIE FLY's decompile-only ambiguity, Ruko has explicit PTZ UI and
command builders.

**UI path** (`ControlActivity` / `ControlHyActivity`):

- `ptz_up_btn` / `ptz_down_btn` adjust `ptz_seek_bar` by ±5
- Each press calls `MyApplication.setPTZData(progress)`
- Telemetry syncs seek bar from `NOTIFY_TYPE_PTZ_ANGLE` / `flyInfo.getZTP()`

**Tilt set commands** (`SJBaseApplication.setPTZData(int angle)`):

| Board path | Packet | Angle byte |
|------------|--------|------------|
| Hisi | `FF 53 54 32 01 <angle>` | byte `[5]` |
| HACK_FLY | `68 07 01 <angle> <xor>` | byte `[3]` |
| FEI_SHA | `5A 55 02 14 <angle> <xor>` | byte `[4]` |

Non-Hisi tilt uses `writeTCPCmd` → TCP port **8888**.

**Other PTZ commands** (UDP `8080` unless noted):

| Cmd `[3]` | Payload | Function |
|-----------|---------|----------|
| 2 | `[4]=1/2` | PTZ off/on |
| 7 | `[4]=1` | PTZ ready status |
| 15 | `[4]=0` | start distance calibration |
| 16 | `[4]=roll, [5]=pitch` | PTZ trim (defaults 128) |
| 18 | `0` | reset PTZ |
| 21 | `[4]=1` | get PTZ angle |
| 32 | `[4]=1, [5]=angle` | set PTZ angle (Hisi `setPTZData`) |
| 38 | yaw byte | yaw trim |

**Responses** (`AnalysisUtils.ptz`):

- cmd `97` → `NOTIFY_TYPE_PTZ_ANGLE` bytes `[4],[5]`
- cmd `21` → `NOTIFY_TYPE_UPDATE_PTZ_ANGLE` byte `[5]`

`SendHyControlThread.setPtzV()` exists but has **no callers** in this decompile;
stock tilt goes through `setPTZData` / ST commands, not the HY `PTZ_V` field.

For TurboDrone tilt experiments on Ruko hardware, prefer `s2x_tilt_probe.py`
**`st3` mode** (`ff 53 54 33 <param> <value>`) and direct ST cmd `32` shape
above, not HY bytes 8–17 (those are zero-filled in the 20-byte `66 14` path
this app does not even build).

#### Key source files (Ruko)

| Topic | Path under `decompiled-ruko-drone-1.7.6/sources/` |
|-------|---------------------------------------------------|
| Manifest | `resources/com.vison.macrochip.ruko.drone.apk/AndroidManifest.xml` |
| Ports / egress | `com/vison/baselibrary/base/BaseApplication.java` |
| HACK_FLY RC | `com/sj/baselibrary/thread/SendHyControlThread.java` |
| FEI_SHA RC | `com/sj/baselibrary/thread/SendControlThread.java` |
| Protocol routing | `com/sj/baselibrary/base/SJBaseApplication.java` |
| PTZ commands | `com/sj/baselibrary/base/SJBaseApplication.java` (`setPTZData`, etc.) |
| PTZ parse | `com/sj/baselibrary/utils/AnalysisUtils.java` (`ptz`) |
| Video decode | `com/vison/baselibrary/connect/stream/VideoStreamHandle.java` |
| Video heartbeat | `com/vison/baselibrary/connect/wifi/StreamUdpConnection.java` |
| Tilt UI | `com/vison/macrochip/activity/ControlActivity.java` L689–706 |
| Native HY encode | `com/vison/macrochip/sdk/LGDataUtils.java` |

### Ruko GIM 1.0.5 notes (F11GIM3)

Ruko GIM is a **dedicated gimbal-drone OEM app** for the **F11GIM3** (also
referenced in class/tutorial assets as F11GIM2). It uses the same **世季 SJ GPS
Pro + HACK_FLY** stack as Ruko Drone 1.7.6, not the `w.fpv` PL FPV tree.

App identity:

- Package: `com.vison.macrochip.sj.ruko.gim`
- Version: `1.0.5` / `versionCode=5`
- Application: `com.vison.macrochip.sj.gps.pro.app.MyApplication` →
  `SJBaseApplication`
- Launcher: `com.vison.macrochip.sj.gps.pro.activity.WelcomeActivity`
- Flight UI: `com.vison.macrochip.sj.gps.pro.activity.ControlHyActivity`
  (HACK_FLY only; `WelcomeActivity` forces `ProtocolEnum.HACK_FLY`)
- Product selector: single entry `F11GIM3` → `SJBaseApplication.DRONE_TYPE = 9`
- Decompile: `decompiled-ruko-gim-1.0.5/`
- Backend API host: `websiteapi.rukotoy.com` (Ruko branding in log upload:
  `"RUKO GIM"`)

#### TurboDrone mapping (existing implementation, not new)

| Layer | Maps to | Notes |
|-------|---------|-------|
| **Video / network** | **S2x / Macrochip** | Same `BaseApplication` ports, `08` heartbeat, UDP/TCP `8888`, `vison_main` / VNDK path |
| **RC sticks / flight** | **fld_pro Hy / HACK_FLY** | 17-byte `68 01 0D` via `SendHyControlThread` + `LGDataUtils` — **not** TurboDrone's 20-byte `66 14 ... 99` `s2x` adapter |
| **Camera tilt** | **Ruko PTZ side channel** | `setPTZData` + ST `FF 53 54` family; see below and `s2x_ptz_helper.py` |

**Conclusion:** Do **not** add a new TurboDrone backend. Treat F11GIM3 like Ruko
Drone: Macrochip video on `DRONE_TYPE=s2x` may work, but **RC is unverified**
until a capture confirms whether the board accepts `66 14` or requires
`68 01 0D`. For **tilt**, use confirmed `setPTZData` / ST shapes from this
decompile (`s2x_ptz_helper.py`), not HY bytes 8–17.

`ModuleUtils.isRuko()` in the shared SJ library lists `ruko.drone`, `ruko.drone.f11`,
and `ruko.bwine` only — **`sj.ruko.gim` is omitted**, so Ruko-specific calibration
branches keyed on `isRuko()` may not run in this package even though the app is
Ruko-branded.

#### Differences vs Ruko Drone 1.7.6

| Topic | Ruko GIM 1.0.5 | Ruko Drone 1.7.6 |
|-------|----------------|------------------|
| Package / UI shell | `sj.gps.pro` + `sj.ruko.gim` | `macrochip` + `ruko.drone` |
| Default product | F11GIM3 only (`DRONE_TYPE=9`) | Multi-product selector |
| PTZ UI | Rich: `new_ptz_layout`, `ptz_top`/`ptz_bottom`, `new_ptz_seek_bar`, `VerticalScaleMarqueeView`, legacy `ptz_up_btn`/`ptz_down_btn` | Simpler `ptz_seek_bar` + up/down buttons |
| `SendHyControlThread.setPtzV` | **Called** from `VSollbar` progress (`setPtzV(1/2/0)`) while scrolling | Method exists; **no Java callers** in decompile |
| `sendFlowParam` / ST3 `FF 53 54 33` | Not present in this decompile | Present in some Macrochip `w.fpv` apps |

RC packet layout, `setPTZData` byte shapes, and ST command table are **the same**
as documented under "Ruko Drone 1.7.6 notes" (`SJBaseApplication.setPTZData`,
`getPTZAngle`, `resetPTZ`, etc.).

#### Camera pitch / gimbal tilt (confirmed)

This app is built around a **physical camera gimbal**. Evidence is stronger than
generic S2x OEM apps and matches Ruko Drone's PTZ command family, with extra UI.

**UI controls** (`ControlHyActivity`):

- `ptz_up_btn` / `ptz_down_btn` — step `ptz_seek_bar` by ±5, call
  `MyApplication.setPTZData(progress)`
- `ptz_top` / `ptz_bottom` — hold-to-repeat every **50 ms**, angle
  `90 - seekBar.getProgress()` via `SJBaseApplication.setPTZData`
- `new_ptz_seek_bar` — on release: `setPTZData(90 - progress)` (inverted 0–90°
  mapping)
- `VerticalScaleMarqueeView` — drag scale; `onPtzChange` → `setPTZData(i)` when
  `lastPtZadj == 0`
- `VSollbar` — while adjusting, sets `SendHyControlThread.setPtzV(1|2|0)` on the
  **recurring HY stream** (secondary path alongside discrete `setPTZData`)
- Settings: `PTZFragment` with `pitch_btn`, `roll_btn`, `yaw_btn`, calibration,
  reset (`SJBaseApplication.resetPTZ`, `setPTZTrim`, etc.)
- `PTZDialog` — same `setPTZData` entry point as Ruko Drone

**Telemetry / sync:**

- `getPTZAngle()` polled on connect and when `lgPlaneHyBean.Brightness` changes
- `lgPlaneHyBean.PTZadj` (decoded label: **云台上下调节** / gimbal up-down adjust)
  drives `VerticalScaleMarqueeView` continuous scroll when non-zero
- `AnalysisUtils` ST responses: `NOTIFY_TYPE_PTZ_ANGLE` (cmd `97`),
  `NOTIFY_TYPE_UPDATE_PTZ_ANGLE` (cmd `21`)

**Wire commands** (unchanged from Ruko Drone — see table above):

| Path | Packet | When |
|------|--------|------|
| HACK_FLY (default) | `68 07 01 <angle> <xor>` via `writeTCPCmd` | `setPTZData` on non-Hisi boards |
| Hisi | `FF 53 54 32 01 <angle>` | `PlayInfo.isHisi()` |
| FEI_SHA | `5A 55 02 14 <angle> <xor>` | if protocol switches away from HACK_FLY |
| ST side | `FF 53 54 15` trim, `18` reset, `21` get angle, etc. | UDP `8080` |
| HY stream | `LGControlHyBean.PTZ_V` via `setPtzV` | `VSollbar` while user adjusts scale |

No separate `舵机` / `servo` string was required to establish tilt — the app uses
**PTZ** / **云台** wording and dedicated gimbal calibration UI.

For TurboDrone on F11GIM3 hardware: **`s2x_ptz_helper.py`** (`st-set`, `st-get`,
`st-reset`) is the best match to stock `setPTZData` / ST traffic while keeping a
neutral HY or HACK_FLY stream if you later add a `68 01 0D` RC adapter.

#### Key source files (Ruko GIM)

| Topic | Path under `decompiled-ruko-gim-1.0.5/sources/` |
|-------|------------------------------------------------|
| Manifest | `resources/AndroidManifest.xml` |
| Product / HACK_FLY default | `com/vison/macrochip/sj/gps/pro/activity/WelcomeActivity.java` |
| Flight + PTZ UI | `com/vison/macrochip/sj/gps/pro/activity/ControlHyActivity.java` |
| Vertical tilt control | `com/vison/macrochip/sj/gps/pro/view/VerticalScaleMarqueeView.java` |
| HACK_FLY RC | `com/sj/baselibrary/thread/SendHyControlThread.java` |
| PTZ commands | `com/sj/baselibrary/base/SJBaseApplication.java` |
| PTZ parse | `com/sj/baselibrary/utils/AnalysisUtils.java` |
| Gimbal settings UI | `com/sj/baselibrary/fragment/PTZFragment.java` |
| Telemetry field | `com/vison/macrochip/mode/LGPlaneHyBean.java` (`PTZadj`) |

Additional app-level features spotted in REDRIE FLY that do not change the
S2x wire implementation:

- Voice assets and recognition helpers (`VoiceUtils`, `VoiceRecognizer`,
  `SpeechRecognizerThread`).
- Music-selection UI and bundled music asset initialization.
- Gravity/tilt control helpers.
- Follow/track classes (`TrackView`, `FollowView`, `TrackCalculationThread`) that
  feed adjusted stick values into the same RC packet builders.
- USB accessory/media paths and remote media album screens.
- Device probing for many Macrochip camera board variants, including JPEG,
  H.264/H.265, RTSP, TCP, UDP, Hisi, GK, and multi-camera cases. These are
  inherited from the broad Vison base library and should be treated as supported
  app code paths, not separate TurboDrone backends without matching hardware
  captures.

The REDRIE decompile contains ABI split metadata, but no native `.so` files were
present under `decompiled-redrie-fly-1.0.5/resources/config.arm64_v8a.apk` in
this unpack. Because Java still loads `vison_main`, PL FPV's native
`libvison_main.so` analysis remains the best current native evidence for the
S2x video parser.

Camera tilt / PTZ note:

Ruko Drone 1.7.6 and **Ruko GIM 1.0.5 / F11GIM3** (see sections above)
**confirm** camera tilt via dedicated PTZ UI and `setPTZData(angle)` on three
paths: ST `FF 53 54 32`, HACK_FLY `68 07 01`, and FEI_SHA `5A 55 02 14`.
Ruko GIM additionally drives `SendHyControlThread.setPtzV` from its vertical
scale control. Stock discrete tilt does **not** rely on the 20-byte `66 14`
HY packet TurboDrone's `s2x` adapter sends.

For PL FPV / REDRIE FLY / other Macrochip apps without visible tilt UI, the same
ST side channel is still the best hypothesis:

- `ff 53 54 <cmd> ...` on UDP `8080` (cmd `32` for angle set on Hisi boards)
- `ff 53 54 33 <param> <value>` flow-param commands (`sendFlowParam`,
  `WifiCommandHelper.getCameraIndex`)

REDRIE FLY's `66 14` HY bytes `8..17` remain zero-filled in Java; do not assume
tilt lives there without a capture. Use `s2x_tilt_probe.py` **`st3` mode** or
replay Ruko's `setPTZData` packet shapes when probing tilt on Macrochip hardware.

## Hardware UART bridge: WiFi board → flight controller (sniffed)

Everything above this point is derived from app decompilation. This section is
the first **on-the-wire** confirmation, captured from physical hardware on a
**LOILEY S29** (S2x family).

### Setup

The XR872AT WiFi/camera board exposes a 4-wire UART to the flight controller
(silkscreen labels are from the WiFi board's perspective):

- **blue** = WiFi board **TX** → flight-controller RX (the command stream)
- **white** = WiFi board **RX** ← flight-controller TX (telemetry/back-channel)
- **red** = VCC, **black** = GND

Passive sniff rig: WiFi board TX (blue) → Arduino Mega2560 **RX1 (pin 19)**,
GND↔GND, board powered from the Mega's 3V3. The Mega runs a UART sniffer sketch
that groups bytes into frames on a 5 ms idle gap and dumps them over USB at
2,000,000 baud. Decoding the board's TX as **115200 8N1** produces clean,
structured, checksum-valid frames, so the board↔FC link is **115200 8N1**.

PC joined the drone's WiFi (drone `172.16.10.1`, PC `172.16.10.2`) and replayed
S2x control packets to UDP `8080` while sniffing the FC-bound UART, then
correlated the two. The autonomous correlation harness used for this
(`s2x_bridge_probe.py`: baseline → distinctive-signature → per-axis sweeps →
flag tests, logging every timestamped UART frame) lives in a standalone `recon/`
workspace folder, not committed to this repo.

### Key finding: the WiFi board is a transparent UDP → UART bridge

Control packets the app/TurboDrone send to UDP `172.16.10.1:8080` are re-emitted
**byte-for-byte** on the board's TX line to the flight controller, including the
XOR checksum. The board does not re-pack, re-checksum, or rate-shape the control
payload.

Distinctive-signature proof (sent a unique R/P/T/Y so it can't be confused with
an idle/app frame):

```text
UDP out : 66 14 11 22 33 44 00 0A 00 00 00 00 00 00 00 00 00 00 4E 99
UART in : 66 14 11 22 33 44 00 0A 00 00 00 00 00 00 00 00 00 00 4E 99   (~17 ms later)
```

Per-axis sweeps (`0x00→0xFF`) confirmed the on-wire byte positions match the
documented HY layout exactly, with the other three axes pinned at `0x80`:

| Axis | UART byte | Sweep result |
|------|-----------|--------------|
| Roll | `[2]` | exact passthrough |
| Pitch | `[3]` | exact passthrough |
| Throttle | `[4]` | exact passthrough |
| Yaw | `[5]` | exact passthrough |

Byte `6` command flags also pass through unchanged: takeoff/land `0x01`,
e-stop `0x02`, calibrate `0x04` were each observed verbatim on the FC line. This
hardware-validates the byte-2..5 ordering and the byte-6 flag map that were
previously only inferred from decompiled Java, and confirms TurboDrone's
`s2x_rc_protocol_adapter` builds the exact bytes the FC actually receives
(`speed=0x14`, `byte7=0x0a`).

The passthrough covers the **entire 20-byte frame**, not just the sticks: byte-1
(speed) and byte-7 were also forwarded verbatim across arbitrary values
(`speed` swept incl. `0x00`/`0x28`/`0xFF`; `byte7` incl. `0x0b`/`0x0e`/`0x55`).
The board performs no interpretation of the control payload at all.

### Baseline / idle behavior (what the FC sees before any stick input)

There are **two independent streams** on the board's TX line:

1. **`77 0E` optical-flow report** (also serves as a keepalive) — 14 bytes:
   `0x77` start, `0x0E`=length 14, 10 payload bytes, XOR checksum, `0x99` end. The
   board emits this **continuously at ~22 Hz (median gap ~45 ms)** regardless of
   whether any app is connected. The payload is **all-zero only while the drone is
   stationary**; when the optical-flow sensor sees motion it carries flow vectors
   (decoded under "Optical-flow" below). With the phone off and the drone sitting
   still, this all-zero frame is the only thing on the wire — which is why it first
   looked like a plain heartbeat.
2. **`66 14` control** — only present when something is actively sending UDP to
   `8080`. The board forwards each control packet as it arrives.

So the answer to "does the board send a baseline thing before throttle input?":
- The board itself contributes only the `77` heartbeat. It does **not** generate
  a control packet on its own and does **not** appear to emit a special
  "app connected" announcement to the FC — when UDP control starts, the board
  simply begins forwarding (first forwarded frame seen ~17 ms after send start).
- The continuous **centered** control packet (`66 14 80 80 80 80 00 0A … 99`) that
  the FC sees while an app is connected but idle originates from the *controller*
  (the stock app streams centered sticks at ~12–20 Hz even with no input), not
  from the board. The board just relays it.

Implication: a centered idle `66 14 80 80 80 80 …` stream is effectively the
"armed-link / sticks-neutral" baseline the FC expects, and the `77` heartbeat is
the lower-level "I'm alive" signal.

### Implication for replacing the WiFi board (ESP32-S3)

To impersonate the stock board on the FC side at 3.3 V / 115200 8N1, the
replacement firmware reproduces **both** streams on its TX → FC RX:

1. Emit the `77 0E …` frame at ~22 Hz, always (independent of control). For a
   first version this can be the **constant all-zero** flow report
   `77 0E 00 00 00 00 00 00 00 00 00 00 00 99` — i.e. "sensor sees no motion".
2. Emit `66 14 RR PP TT YY F6 0A 00×10 XOR 99` control frames (built exactly like
   `s2x_rc_protocol_adapter.build_control_packet`) at the app's ~12–30 Hz cadence,
   centered when idle.

**v1 design decision (optical flow omitted):** the ESP32-S3 replacement will send
the all-zero `77` report rather than reading the flow sensor. This is acceptable
because the airframe flies normally with the flow camera covered (observed on
hardware) — the FC simply runs without optical-flow position-hold (slightly more
hover drift), exactly as it does when the sensor is blocked. Real flow can be
added later by populating bytes 2–6 of the `77` frame (see decode below). The
`77` frame must still be sent (not omitted): it doubles as the board's link
keepalive to the FC, and dropping it entirely is uncharacterized.

### Open questions / TODO (hardware)

- **Reverse channel:** sniff the FC → board direction (white wire → Arduino
  **RX2 / pin 17**) to recover telemetry (battery, status, stick echo). Only the
  board→FC direction has been captured so far.
- **`77` flow axis/scale:** the message is decoded (see "Optical-flow" below), but
  the X/Y axis-to-direction mapping, polarity, units/scale, and the exact meaning
  of byte 6 (quality vs height) still need a guided motion capture.

Resolved by follow-up hardware tests (no rewiring needed):

- **Failsafe — RESOLVED:** when the UDP control stream stops, the board emits
  **zero** control frames; it does **not** latch or repeat the last command. Only
  the `77` heartbeat continues (~22 Hz). Link-loss failsafe therefore lives on
  the **flight controller**, not the WiFi board — the board simply stops relaying.
- **Byte 7 / speed — RESOLVED:** both are forwarded **verbatim** (see "full
  20-byte passthrough" above); the board does not act on them. Any FC behavior
  change from byte-7 bits or the speed byte is a property of the FC firmware.

### Optical-flow sensor: the `77` message is the flow channel (RESOLVED)

On this airframe the optical-flow sensor plugs into the **WiFi/camera board**,
not directly into the FC. The question was whether the XR872 (a) relays flow data
to the FC, or (b) runs the position-hold loop itself and injects roll/pitch
corrections into the `66 14` control stream.

**Answer: (a).** The `77` message *is* the optical-flow report from the board to
the FC. Capturing the board→FC TX while moving the drone over a textured floor
(then setting it back on a table) showed the `77` payload fill with structured
flow data during motion and return to all-zero when stationary. The board never
modified the `66` control stream (bytes 2–5 stayed exactly as sent), so the FC —
not the WiFi board — closes the position-hold loop. The board's role is: relay
control UDP→UART verbatim, and report flow sensor data upstream to the FC.

Decoded `77` frame (14 bytes):

```text
77 0E  FXlo FXhi  FYlo FYhi  QQ  00 00 00 00 00  CK  99
```

| Byte | Field | Notes |
|------|-------|-------|
| `0` | `0x77` | start marker |
| `1` | `0x0E` | length = 14 |
| `2..3` | flow X | signed 16-bit little-endian; 0 when stationary |
| `4..5` | flow Y | signed 16-bit little-endian; 0 when stationary |
| `6` | quality/height | non-zero only when flow active (e.g. `0xFF` then `0x6F..0xCF`); exact meaning — surface quality vs height — not yet pinned down |
| `7..11` | reserved | always `0x00` observed so far |
| `12` | checksum | XOR of bytes `2..11` (same scheme as the `66` packet) |
| `13` | `0x99` | end marker |

Sample (moving over floor): `77 0E 56 FE B0 FF FF 00 00 00 00 00 18 99`
→ flowX = `0xFE56` = -426, flowY = `0xFFB0` = -80, quality = `0xFF`,
checksum `56^FE^B0^FF^FF = 0x18`. Stationary: `77 0E 00 00 00 00 00 00 00 00 00 00 00 99`.

**Implication for an ESP32-S3 replacement:** to be a faithful stand-in the
replacement must *also* read the same flow sensor and emit the `77` flow report
at ~22 Hz, or the FC loses optical-flow position-hold. A control-only bridge will
fly but without flow stabilization.

**Still to characterize:** sign/axis convention (which int16 is forward/right and
its polarity), units/scale, and the exact meaning of byte 6 (quality vs height).
A guided capture — log the decoded `77` stream while sliding the drone a known
direction/distance and raising/lowering it — would settle these.

## RC timing and feel

The inspected stock app paths send RC packets every 50 ms:

- HiTurbo `SendHuiYuanThread` sleeps `50L` between packets.
- PL FPV subscribes to `RxManager.getObservable(0L, 50L)` for
  `HyControlConsumer`.
- REDRIE's recovered control builders are RxJava `Consumer<Long>` classes, but
  the referenced `ControlActivity` source is missing from this decompile, so its
  exact scheduling interval is not visible in the recovered Java.

TurboDrone's S2x backend sends RC packets at 80 Hz by default, so perceived lag
is unlikely to be caused by a lower packet rate. More likely causes:

- Frontend `inc` mode is intentionally ramped by `IncrementalStrategy`.
- Gamepad/absolute mode should feel closer to the app because it uses
  `DirectStrategy`.
- Browser input is forwarded to the backend at 30 Hz, while the backend repeats
  the latest state at the configured control rate.
- Debug control logging can add small overhead when enabled.

## Speed tiers

The HY stock app paths do not use byte `1` as a speed selector; byte `1` stays
`0x14`. Instead, the app scales roll and pitch around center before sending the
packet.

Observed speed scales:

- HiTurbo: speed `0` = `0.6`, speed `1` = `0.8`, speed `2` = `1.0`.
- PL FPV: speed `0` = `0.7`, speed `1` = `0.8`, speed `2` = `1.0`.
- REDRIE FLY HY path: speed `0` = `0.6`, speed `1` = `0.8`, speed `2` =
  `1.0`.
- REDRIE FLY short path: speed `0` = `0.3`, speed `1` = `0.6`, speed `2` =
  `1.0`.

TurboDrone now keeps S2x default behavior at full scale (`speed_index = 2`) and
supports lower S2x speed tiers via `set_speed_index`.

## Native libraries

PL FPV's `config.arm64_v8a.apk` split contains native libraries under
`resources/config.arm64_v8a.apk/lib/arm64-v8a`. The important app-specific
libraries are:

- `libvison_main.so`: implements `com.vison.sdk.VNDK` JNI methods such as
  `addVideoStream`, `add872Stream`, `createVideoStream`,
  `getVideoOneFrameArray`, `convertJPEGToI420`, `convertNV12ToI420`, and
  FFmpeg/H.265 decode helpers. Printable symbols include `_872StreamBuf`,
  `udp_pack`, `MJPGToI420`, and the Java `VNDK` exports. This looks like the
  native video parser/decoder bridge, not the RC command transport.
- `libdetector-lib.so`: implements `com.vison.macrochip.sdk.JNIManage` for
  hand detection, follow/track, obstacle detection, image stitching, and
  OpenCV/ncnn/ONNX helpers. This is vision/autonomy support and does not appear
  to own the RC packet format.
- `librxffmpeg-*`, `libav*`, `libsw*`, `libHW_H265dec_Andr.so`,
  `libturbojpeg.so`, `libjpeg.so`: codec, FFmpeg, and JPEG support.

String-level inspection did not find hard-coded S2x IPs or ports in
`libvison_main.so`; the network target and control socket behavior still appear
to be owned by the Java `BaseApplication` / connection classes. This supports
keeping TurboDrone's S2x RC implementation as a Java-level packet match while
using native findings mostly to understand video parsing.

### Native S2x UDP video parser

Ghidra decompilation of `libvison_main.so` shows that PL FPV's Java
`VNDK.add872Stream(byte[], int)` calls a native `analysis(int, char*, char*&)`
function before writing a completed image into the internal BLB frame buffer.
That function is the best match for TurboDrone's S2x UDP packet parser.

Observed native packet rules:

- Bytes `0..1`: sync marker `0x40 0x40`.
- Bytes `2..3`: little-endian 16-bit frame/image id.
- Byte `4`: total chunks in the frame. The native parser rejects `0`.
- Byte `5`: chunk index. The native parser rejects values above `100`.
- Bytes `6..7`: little-endian datagram length, which must equal the received
  packet length.
- Bytes `8..packet_len-3`: JPEG payload data.
- Bytes `packet_len-2..packet_len-1`: two-byte trailer, normally `##`.

The native parser keeps two frame slots, accepts out-of-order chunks, stores
each chunk at `chunk_id * 0x56e`, tracks a per-frame chunk bitmap, and emits the
frame as soon as all chunk ids `0..total_chunks-1` have arrived. This is better
than waiting for the next frame id to know the previous frame is complete.

TurboDrone's S2x video parser now mirrors the important parts of this behavior:
it uses the 16-bit frame id, validates total chunks and declared packet length,
strips the `##` trailer, and emits a frame immediately once all declared chunks
are present. It still keeps a frame-id rollover fallback for older captures or
unexpected variants.

## TurboDrone implementation notes

Current matching files:

- `backend/models/s2x_rc.py`
- `backend/protocols/s2x_rc_protocol_adapter.py`
- `backend/protocols/s2x_video_protocol.py`
- `backend/models/s2x_video_model.py`

Implementation parity notes:

- RC packet shape matches the Macrochip HY 20-byte packet.
- Video start command matches the app's `0x08 + local IPv4` command.
- Video receive port and native `0x40 0x40` chunk header match the S2x stream
  behavior.
- `S2X_SWAP_YAW_ROLL` is available as a variant knob in the web backend.
- S2x speed tiers are supported as a model-level knob; the default remains full
  scale to preserve existing flight feel.

## Notes

`nmap` on all TCP ports yielded only `8888` open. This is likely a backup or
variant path for the main video feed over UDP.