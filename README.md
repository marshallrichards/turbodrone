
<div align="right">
  <details>
    <summary >🌐 Language</summary>
    <div>
      <div align="center">
        <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=en">English</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=zh-CN">简体中文</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=zh-TW">繁體中文</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=ja">日本語</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=ko">한국어</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=hi">हिन्दी</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=th">ไทย</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=fr">Français</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=de">Deutsch</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=es">Español</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=it">Italiano</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=ru">Русский</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=pt">Português</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=nl">Nederlands</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=pl">Polski</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=ar">العربية</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=fa">فارسی</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=tr">Türkçe</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=vi">Tiếng Việt</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=id">Bahasa Indonesia</a>
        | <a href="https://openaitx.github.io/view.html?user=marshallrichards&project=turbodrone&lang=as">অসমীয়া</
      </div>
    </div>
  </details>
</div>

# Turbodrone
Reverse-engineered API and client for controlling some of the best-selling ~$50 "toy" drones on Amazon from a computer replacing the closed-source mobile apps they come with.

![S20 Drone Short Clip](docs/images/s20-drone-short-clip-small.gif)

## Introduction
Nowadays, there are incredibly cheap "toy" drones available on Amazon that are basically pared-down clones of the early DJI mavic. Only ~$50 to have a 1080p camera for FPV and recording, tiny downward-facing optical flow sensor for position and altitude hold, and a well-tuned flight profile out-of-the-box. The only problem with drones like this is that they run closed-source firmware and are locked to only being controlled by a custom mobile app. I thought it would be cool to free some of these drones from their "jail" and write an API and client for accessing the video feed and sending control commands down to the drone by reverse-engineering how the mobile apps work. That way you can turn a highly capable $50 "toy" drone into something that can be programmatically controlled and used for all sorts of applications and experiments.

## Hardware
* WiFi Camera Drone (ranked in order of recommendation):

    | Brand      | Model Number(s)    | Compatibility | Purchase Link                                               | Notes |
    |------------|-----------------|---------------|-------------------------------------------------------------|-------|
    | Karuisrc | K417 | Tested | [Amazon](https://www.amazon.com/Electric-Adjustable-AIdrones-Quadcopter-Beginners/dp/B0CYPSJ34H/) | My favorite right now. Only one on the list with brushless motors! Build quality is fantastic. |
    | Loiley     | S29             | Tested    | [Amazon](https://www.amazon.com/Beginners-Altitude-Gestures-Adjustable-Batteries/dp/B0CFDVKJKC)                  | Best build quality, has servo for tilting camera(_not implemented in API yet_)|
    | Hiturbo    | S20             | Tested    | [Amazon](https://www.amazon.com/dp/B0BBVZ849G), [Alternate Amazon Listing](https://www.amazon.com/Beginners-Foldable-Quadcopter-Gestures-Batteries/dp/B0D8LK1KJ3)                  | Original test platform, great build quality|
    | FlyVista | V88 | Tested | [Amazon](https://www.amazon.com/dp/B0D5CXY6X8) | |
    | ? | D16/GT3/V66 | Tested | cheapest on [Aliexpress](https://www.aliexpress.us/item/3256808590663347.html), [Amazon](https://www.amazon.com/THOAML-Batteries-Altitude-Headless-360%C2%B0Flip/dp/B0F1D6F62J/) | 20% smaller DJI Neo clone. Only really good for indoor flight. 
    | Several Brands | E58 | Tested | [Amazon](https://www.amazon.com/Foldable-Quadcopter-Beginners-Batteries-Waypoints/dp/B09KV8L7WN/) |  |
    | Several Brands | E88/E88 Pro | Suspected | [Amazon](https://www.amazon.com/Foldable-Camera-Quadcopter-Altitude-Beginner/dp/B0DZCLFQXN) | |
    | Several Brands | E99/E99 Pro | Suspected | [Amazon](https://www.amazon.com/LJN53-Foldable-Drone-Dual-Cameras/dp/B0DRH9C6RF) | |
    | Swifsen | A35 | Suspected | [Amazon](https://a.co/d/bqKvloz) | Very small "toy" drone|
    | Unknown | LSRC-S1S | Suspected | | mentioned in another reverse-engineering effort for the WiFi UAV app|
    | Velcase    | S101            | TODO | [Amazon](https://www.amazon.com/Foldable-Beginners-Quadcopter-Carrying-Positioning/dp/B0CH341G5F/)  | lower quality build, smaller battery and props than S29 & S20|
    | Redrie | X29 | TODO | [Amazon](https://www.amazon.com/Adults-1080P-Foldable-Altitude-Auto-Follow-Batteries/dp/B0CZQKNYL5) | Working on this one now|

    _**Tested** means the drone has been physically run with turbodrone to ensure its compatibility._

  _**Suspected** means the APK for the drone appears to use the exact same packages and libraries as one of the tested drones._

  _**TODO** means the APK operates with different byte packets and protocols and will have to be added as a new implementation in the API._

* WiFi Dongle ([recommend ALFA Network AWUS036ACM](https://www.amazon.com/Network-AWUS036ACM-Long-Range-Wide-Coverage-High-Sensitivity/dp/B08BJS8FXD) or similar) 
  * Drone broadcasts its own WiFi network so your computer will have to connect to it.
  * Not strictly necessary because you can use your computer's built-in WiFi radio to connect to the drone's network, but nice to have that way you can stay connected to the internet while flying the drone.


## Setup
Move to the `backend` directory
```
cd backend
```

Add venv
```
python -m venv venv
source venv/bin/activate
```

Install the dependencies
```
pip install -r requirements.txt
```

_If_ you are on Windows, you will need to manually install the `curses` library.
```
pip install windows-curses
```

Open a new terminal window and install the dependencies for the frontend.
_Make sure you have Node.js 20+ installed._
```
cd frontend
npm install
```

Make sure WiFi Dongle is plugged in, drone is turned on, connect to the "BRAND-MODEL-XXXXXX" network before proceeding.

Create a `.env` file in the `backend` directory. Add a DRONE_TYPE based on which drone you have:
```
# For "com.vison.macrochip" (s2x) based drones like S20 and S29:
DRONE_TYPE=s2x
# For WiFi UAV-based drones like V88 and D16:
# DRONE_TYPE=wifi_uav 
```

Launch the backend: 
```
uvicorn web_server:app
```

In a separate terminal, launch the frontend web client:
```
npm run dev
```

Open the web client which will be at `http://localhost:5173` and you should see the drone video feed and be able to control it.

To control via a gaming controller, plug it in and move the sticks around for it to be detected and then push the toggle button to switch between keyboard and controller control.

Make sure to fly in a safe area, preferably outdoors with little wind. And note that the "Land" button _currently_ is more of an E-stop button that will stop the drone motors immediately.


## Status
Reconnection logic was solved recently.

Video feed: solid.

Controls: improved greatly via the web client. The implementation for WiFi UAV-based drones could use some fine-tuning.

Web Client: support for various inputs like keyboard, gamepad controllers, and ThinkPad TrackPoint mouse(lol).

Working on adding support for more drones from [Amazon's best-selling drone list](https://www.amazon.com/best-selling-drones/s?k=best+selling+drones).


## Contribute
To contribute support for a new "toy" drone, download the APK the drone uses on a mirror site and start reverse engineering it by decompiling to Java files with [jadx](https://github.com/skylot/jadx).
From there, look at the `AndroidManifest.xml` and see if you can find the classes that are entry points for the app. Look for port usage or protocol usage explicitly mentioned like TCP or UDP. Most of these apps will do the actual communication and video feed processing in native C++ libraries that will be embedded inside the APK. You can use a tool like Ghidra to decompile the native libraries and see if you can discover anything useful. For video feed processing you want to figure out what format it uses e.g. JPEG, YUV, etc. and also if it uses compression and what the byte structure looks like when its reforming an image frame from packets.
Additionally, Wireshark is your friend for understanding the raw data packets being sent and received by the app. Watch this [video](https://x.com/marshallrichrds/status/1923165437698670818) for an overview into the reverse engineering process used for adding support for the Hiturbo S20 drone.

Once you have the protocols and processing for RC and video figured out, make a small test program and add it to the `experimental` directory at that point if you'd like others to be able to try it out.
After that, you can work on an implementation that is compatible with the existing back-end architecture; examples of this are the `s2x` and `wifi_uav` reverse-engineered implementations.


## Experimental Support
For drones and apps with limited support which are not yet fully integrated into Turbodrone, see the `experimental` directory.
