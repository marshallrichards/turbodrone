# Turbodrone
Reverse-engineered API and client for controlling some of the best-selling ~$50 "toy" drones on Amazon from a computer replacing the closed-source mobile apps they come with.

![S20 Drone Short Clip](docs/images/s20-drone-short-clip-small.gif)

## Introduction
Nowadays, there are incredibly cheap "toy" drones available on Amazon that are basically paired-down clones of the early DJI mavic. Only ~$50 to have a 1080p camera for FPV and recording, tiny downard-facing optical flow sensor for position and altitude hold, and a well tuned flight profile out-of-the-box. The only problem with drones like this is that they run closed-source firmware and are locked to only being controlled by a custom mobile app. I thought it would be cool to free some of these drones from their "jail" and write an API and client for accessing the video feed and sending control commands down to the drone by reverse-engineering how the mobile apps work. That way you can turn a highly capable $50 "toy" drone into something that can be programmatically controlled and used for all sorts of applications and experiments.

## Hardware
* WiFi Camera Drone (ranked in order of recommendation):

    | Brand      | Model Number(s)    | Compatibility | Purchase Link                                               | Notes |
    |------------|-----------------|---------------|-------------------------------------------------------------|-------|
    | Loiley     | S29             | Tested    | [Amazon](https://www.amazon.com/Beginners-Altitude-Gestures-Adjustable-Batteries/dp/B0CFDVKJKC)                  | Best build quality, has servo for tilting camera(_not implemented in API yet_)|
    | Hiturbo    | S20             | Tested    | [Amazon](https://www.amazon.com/dp/B0BBVZ849G), [Alternate Amazon Listing](https://www.amazon.com/Beginners-Foldable-Quadcopter-Gestures-Batteries/dp/B0D8LK1KJ3)                  | Original test platform, great build quality|
    | ? | D16/GT3/V66 | Tested | cheapest on [Aliexpress](https://www.aliexpress.us/item/3256808590663347.html), [Amazon](https://www.amazon.com/THOAML-Batteries-Altitude-Headless-360%C2%B0Flip/dp/B0F1D6F62J/) | 20% smaller DJI Neo clone. Only good for indoor flight really. 
    | Several Brands | E58 | Tested* | [Amazon](https://www.amazon.com/Foldable-Quadcopter-Beginners-Batteries-Waypoints/dp/B09KV8L7WN/) | Atleast video feed has been tested physically with this drone. Very likely will work though. |
    | Karuisrc | K417 | Tested* | [Amazon](https://www.amazon.com/Electric-Adjustable-AIdrones-Quadcopter-Beginners/dp/B0CYPSJ34H/) | |
    | Several Brands | E88/E88 Pro | Suspected | [Amazon](https://www.amazon.com/Foldable-Camera-Quadcopter-Altitude-Beginner/dp/B0DZCLFQXN) | |
    | Several Brands | E99/E99 Pro | Suspected | [Amazon](https://www.amazon.com/LJN53-Foldable-Drone-Dual-Cameras/dp/B0DRH9C6RF) | |
    | Swifsen | A35 | Suspected | [Amazon](https://a.co/d/bqKvloz) | Very small "toy" drone|
    | Unknown | LSRC-S1S | Suspected | | mentioned in another reverse-engineering effort for the WiFi UAV app|
    | Velcase    | S101            | TODO | [Amazon](https://www.amazon.com/Foldable-Beginners-Quadcopter-Carrying-Positioning/dp/B0CH341G5F/)  | lower quality build, smaller battery and props than S29 & S20|

    _**Tested** means the drone has been physically run with turbodrone to ensure its compatibility._

  _**Suspected** means the APK for the drone appears to use the exact same packages and libraries as one of the tested drones._

  _**TODO** means the APK operates with different byte packets and protocols and will have to be added as a new implementation in the API._

* WiFi Dongle ([recommend ALFA Network AWUS036ACM](https://www.amazon.com/Network-AWUS036ACM-Long-Range-Wide-Coverage-High-Sensitivity/dp/B08BJS8FXD) or similar) 
  * drone broadcasts its own WiFi network so your computer will have to connect to it.


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
DRONE_TYPE=s2x
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

Make sure to fly in a safe area, preferably outdoors with little wind. And note that the "Land" button _currently_ is more of a E-stop button that will stop the drone motors immediately.


## Status
Reconnection logic was solved recently.

Video feed: solid.

Controls: improved greatly via the web client. 

Web Client: first version is out now.

Also working on adding support for more drones from [Amazon's best-selling drone list](https://www.amazon.com/best-selling-drones/s?k=best+selling+drones).


## Contribute
To contribute a new "toy" drone, download the APK the drone uses on a mirror site and start reverse engineering it by decompiling to java files with [jadx](https://github.com/skylot/jadx).
From there, look for entry points into the app like `MainActivity` or `BaseApplication` and look for port usage or protocol usage explicitly mentioned like TCP or UDP.
Additionally, Wireshark is your friend for understanding the raw data packets being sent and received by the app. Watch this [video](https://x.com/marshallrichrds/status/1923165437698670818) for an overview into the reverse engineering process used for adding support for the first drone.

Once you have the protocols for RC and video figured out, make a small test program and add it to `experimental` directory at that point if you'd like.
After that, you can work on an implementation that is compatible with the existing back-end architecture; examples of this are the s2x and wifi_uav reverse-engineered implementations.


## Experimental Support
For drones and apps with limited support that are not fully integrated into Turbodrone, see the `experimental` directory.
