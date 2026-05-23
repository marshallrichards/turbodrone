# FLD Pro 1.0.8 Protocol Research

This note captures findings from the decompiled FLD Pro Android app in
`decompiled-fld-pro-1.0.8`.

The app is from the same publisher family as WiFi-UAV:

- Package: `com.lcfld.fldpublicpro`
- Version: `1.0.8` / `versionCode=31`
- Main flight screen: `com.lcfld.fldpublicpro.NewControlActivity`
- Dispatcher: `defpackage.op0`

## Relationship To WiFi-UAV

FLD Pro shares a lot of app architecture with the WiFi-UAV app, but it should
not be treated as the same RC packet implementation.

Shared pieces:

- `op0` maps the same SSID prefixes:
  - `FLOW_` / `FlOW_` -> `Uav`
  - `WIFI_`, `GD89Pro_`, `WTECH-`, `WTECH_` -> `Fld`
- `so0` wraps `lxSigPro.getLogicInstance()` and sends bytes through
  `DataForward(bytes, 0)`.
- `qp0` wraps `UAVSDK`, starts it through `nativeStart()`, and sends control
  bytes through `nativeSendCtlMsg(bytes, len)`.

Different pieces:

- WiFi-UAV uses `defpackage.xx` for its short 8-byte `66 ... 99` packet and
  extended 20-byte `66 14 ... 99` packet.
- FLD Pro uses `defpackage.hm` for `op0.e.Hy` and `defpackage.sz` for
  `op0.e.New`.
- `NewControlActivity` chooses `Hy` unless the newer status path is alive or
  the connected SSID contains `Gps`.

So the transport family overlaps with WiFi-UAV, but the manual RC bytes are a
new implementation candidate.

## PTZ / Camera Tilt Evidence

FLD Pro has explicit PTZ UI and packet fields. No separate "servo", "steering
gear", or `舵机` label was found in the app-specific Java/resources during this
pass; the recovered app wording is `ptz`.

Important UI path:

- `lxGpsCtrlView` creates `lxPtzSlider` and a `ptz_btn_nor` / `ptz_btn_sel`
  button.
- `lxPtzSlider` is a spring-centered slider. On touch release it resets to the
  midpoint.
- `lxGpsCtrlView.getPtzUpDnState()` maps slider position to:
  - `0`: neutral
  - `1`: one tilt direction, when percent is above `0.5`
  - `2`: opposite tilt direction, when percent is below `0.5`
- `NewControlActivity.B1()` enables PTZ support for the `Hy` status path.
- `NewControlActivity.C1()` disables the visible PTZ support for the `New`
  status path, even though the `sz` packet builder still has a PTZ field.

Important send-loop path:

```text
NewControlActivity
  Hy path:
    Q.C = j.getPtzUpDnState()
    P.k(Q.d())

  New path:
    R.C = j.getPtzUpDnState()
    P.k(R.w())
```

The practical read is: confirmed Hy-mode camera tilt/PTZ support; New-mode has
a packet field but the stock UI hides PTZ in the recovered code path.

## Hy Control Packet

`hm.d()` builds a 17-byte recurring control packet:

```text
68 01 0d <axis0> <axis1> <axis2> <axis3> <trim0/trim1>
<flags0> <flags1> <flags2/ptz> <flags3> <ext0> <ext1> <ext2> <ext3> <xor>
```

Known fields:

- Byte `0`: `0x68`
- Byte `1`: `0x01`
- Byte `2`: `0x0d`
- Bytes `3..6`: four stick axes from the shared `po0.b(...)` scaler.
- Bytes `7..8`: packed trim / mode bits.
- Byte `9`: one-shot and mode flags including up, down, stop, roll, back, and
  related state.
- Byte `10`, bits `6..7`: PTZ / camera tilt state from `hm.C`.
- Byte `16`: XOR checksum over bytes `1..15`.

PTZ mapping in `hm.d()`:

```text
state 0 -> byte 10 bits 6..7 = 00b
state 1 -> byte 10 bits 6..7 = 01b -> 0x40
state 2 -> byte 10 bits 6..7 = 10b -> 0x80
```

This is not the WiFi-UAV `66 14 ... 99` extended packet. It is closer in shape
to the 17-byte `68 01 0d ...` HY-family packet documented in the Netopsun/HK88
research, but this app has its own builder and should be verified with captures
before reusing another backend's exact semantics.

The Ruko Drone app (`com.vison.macrochip.ruko.drone` 1.7.6,
`decompiled-ruko-drone-1.7.6`) uses the same `68 01 0D` + `LGDataUtils`
encode path as its default HACK_FLY control (`SendHyControlThread`). See
`docs/research/S2x.md` ("Ruko Drone 1.7.6 notes") for video, ST gimbal, and
tilt command details on that Macrochip stack.

## New / GPS Control Packet

`sz.w()` builds a shorter framed packet for `op0.e.New`:

```text
a5 0b 2f 07 <axis0> <axis1> <axis2> <axis3> <ptz> <xor> 5a
```

Known fields:

- Byte `0`: `0xa5`
- Byte `1`: packet length, `0x0b`
- Byte `2`: command id, `0x2f`
- Byte `3`: payload length plus two, `0x07`
- Bytes `4..7`: four normalized axis bytes from `sz.f(...)`.
- Byte `8`: PTZ / camera tilt field from `sz.C`.
- Byte `9`: XOR checksum over bytes `2..8`.
- Byte `10`: `0x5a`

PTZ mapping in `sz.w()`:

```text
state 0 -> byte 8 = 0x00
state 1 -> byte 8 = 0x40
state 2 -> byte 8 = 0xc0
```

Because `NewControlActivity.C1()` disables visible PTZ support for this mode,
the field should be treated as latent until a real New/GPS-mode capture proves
that hardware acts on it.

## Implementation Notes

Recommended split:

- Add a new `fld_pro` research/implementation candidate instead of folding this
  into the current WiFi-UAV `66 14 ... 99` command builder.
- Reuse WiFi-UAV transport knowledge cautiously: the app still uses `lxSigPro`
  and `UAVSDK` wrappers, but the recurring manual RC payloads are different.
- Start with Hy mode if the target hardware exposes PTZ in the stock UI. That is
  the strongest app-level evidence for camera tilt support.
- Keep `camera_tilt_state` frontend semantics aligned with existing TurboDrone
  conventions: `0=neutral`, `1=down/one direction`, `2=up/opposite direction`.

Capture checklist before coding/flying:

- Idle Hy packet.
- PTZ slider above midpoint, below midpoint, and released.
- Takeoff, landing, stop, return, headless, and speed/mode toggles.
- A New/GPS-mode session, if the drone SSID or firmware selects `op0.e.New`.
- Whether the transport is the FLD/lxSigPro path or the UAVSDK path for the
  actual SSID.
