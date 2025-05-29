# WIFI UAV app
Reverse-engineered protocol support for the [WiFi UAV](https://play.google.com/store/apps/details?id=com.lcfld.fldpublic) android app.

### Status
- ✅ Video feed
- 🚧 Control commands

### Findings
- **Start Command**: The video stream is triggered by sending a specific UDP payload `0xEF 0x00 0x04 0x00` to port 8800.
- **Packet Structure**
  - Each frame is split across multiple UDP packets.
  - Each packet has a **56-byte custom header**, followed by the actual image fragment.
  - **Byte 3** in the header marks the last packet of a frame.
  - **Byte 32** indicates the fragment index within a frame.
  - **Bytes 16-17** increment with each frame, acting as frame number.
- **JPEG Decoding**
  - The image data lacks standard JPEG headers.
  - The headers are added manually (SOI, SOF, DQT, SOS, EOI).
- **Frame Requests**
  - After the initial "start video" request, the drone expects custom "next frame" requests to continue streaming at higher frame rates (~20 FPS).
  - These request packets must include an incrementing frame index in multiple locations.

### Reference
- [Reversing write up](https://guillesanbri.com/drone-video/)
