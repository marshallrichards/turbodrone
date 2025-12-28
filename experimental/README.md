# Experimental
This directory contains early-stage support for drones that are not yet integrated into the main Turbodrone architecture.

Each subdirectory corresponds to a mobile app and contains control and video protocols.

## Drones and Apps

| App Name              | Supported Drones | Notes |
|-----------------------|------------------|-------|
| RC_UFO | E88 pro | PyQt5 app for flying it with a computer |

## Running the E88 Pro Controller in WSL

The `test_e88pro.py` script provides a desktop controller for the E88 Pro drone. Running it in WSL requires specific networking and GUI configuration.

### Prerequisites

- Windows 11 with WSL2 installed
- WSLg (GUI support) enabled
- Your E88 Pro drone

### 1. System Dependencies (WSL)

Install required X11 and Qt libraries for PyQt5:

```bash
sudo apt-get update
sudo apt-get install -y \
  libxcb1 libxcb-xinerama0 libxkbcommon-x11-0 \
  libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
  libxcb-shape0 libxcb-xfixes0 libxcb-sync1 libxcb-shm0 \
  libxrender1 libxi6 libxtst6 libgl1 \
  libegl1 libopengl0
```

### 2. Python Environment

Create a virtual environment and install Python dependencies:

```bash
cd experimental
python -m venv .venv-e88
source .venv-e88/bin/activate
pip -r requirements.txt
```

### 3. WSL2 Networking (Required for Video)

The E88 Pro streams video over RTSP with UDP RTP packets. WSL2’s default NAT blocks inbound UDP, so you must enable **mirrored networking**.

Create/edit `%UserProfile%\.wslconfig` on Windows:

```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true
firewall=true
autoProxy=true
```

Then restart WSL from an **Administrator PowerShell**:

```powershell
wsl --shutdown
```

After restarting WSL, your Linux instance will share the Windows network interface, allowing the drone’s UDP video packets to reach the app.

### 4. Qt GUI Backend

WSLg supports Wayland. Set the Qt platform before running:

```bash
export QT_QPA_PLATFORM=wayland
```

### 5. Connect and Run

1. Connect your Windows machine to the drone’s Wi‑Fi network.
2. In WSL, run the controller:

```bash
python test_e88pro.py
```

### 6. Controls

- **Z**: Takeoff
- **X**: Land (can be abrupt)
- **C**: Calibrate gyro
- **W/S**: Throttle
- **A/D**: Yaw
- **Arrow Keys**: Pitch/Roll
- **F**: Flip (combine with direction)
- **H**: Toggle headless mode
- **1/2**: Switch camera (unreliable)

### Troubleshooting

- **Qt fails to start**: Ensure you installed the system libraries from step 1 and run with `export QT_QPA_PLATFORM=wayland`.
- **Video shows no frames**: Verify you have enabled mirrored networking in `.wslconfig` and restarted WSL. Confirm Windows is connected to the drone Wi‑Fi.
- **Drone doesn’t respond to controls**: Ensure you are on the drone’s Wi‑Fi. The script sends UDP commands to `192.168.1.1:7099`. If the drone still doesn’t respond, your E88 variant may use a different control protocol.
