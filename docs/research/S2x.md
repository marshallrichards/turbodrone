# Research for the S2x drones (S20, S29, PL FPV)

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

PL FPV is compatible with TurboDrone's existing `s2x` implementation. A
Plegble PL-1515 that lists PL FPV in its guidebook was flown successfully with
`DRONE_TYPE=s2x`: RC controls, video, takeoff, land, and e-stop all worked.

## Network shape

- Device target is the phone's Wi-Fi gateway. TurboDrone's default remains
  `172.16.10.1`, but app code uses the DHCP gateway rather than a hard-coded
  address.
- RC/control is UDP to port `8080`.
- Video is UDP on port `8888`.
- The app also opens TCP `8888` for some Macrochip variants, but the working
  S2x path is the UDP video path.
- There is an auxiliary UDP receive socket on `8081` in newer PL FPV base
  library code.

Video start/keepalive is a five-byte UDP command sent to port `8080`:

```text
08 <local-ipv4-byte0> <local-ipv4-byte1> <local-ipv4-byte2> <local-ipv4-byte3>
```

HiTurbo's `UdpRequestVideo` sends this every 1000 ms. PL FPV's
`StreamUdpConnection` sends the same shape every 1000 ms. TurboDrone currently
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

## RC timing and feel

The inspected stock app paths send RC packets every 50 ms:

- HiTurbo `SendHuiYuanThread` sleeps `50L` between packets.
- PL FPV subscribes to `RxManager.getObservable(0L, 50L)` for
  `HyControlConsumer`.

TurboDrone's S2x backend sends RC packets at 80 Hz by default, so perceived lag
is unlikely to be caused by a lower packet rate. More likely causes:

- Frontend `inc` mode is intentionally ramped by `IncrementalStrategy`.
- Gamepad/absolute mode should feel closer to the app because it uses
  `DirectStrategy`.
- Browser input is forwarded to the backend at 30 Hz, while the backend repeats
  the latest state at the configured control rate.
- Debug control logging can add small overhead when enabled.

## Speed tiers

The stock apps do not use byte `1` as a speed selector; byte `1` stays `0x14`.
Instead, the app scales roll and pitch around center before sending the packet.

Observed HY speed scales:

- HiTurbo: speed `0` = `0.6`, speed `1` = `0.8`, speed `2` = `1.0`.
- PL FPV: speed `0` = `0.7`, speed `1` = `0.8`, speed `2` = `1.0`.

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