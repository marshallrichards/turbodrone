# Turbodrone
Reverse-engineered API and client for controlling some of the best-selling ~$50 "toy" drones on Amazon from a computer replacing the closed-source mobile apps they come with.

![S20 Drone Short Clip](docs/images/s20-drone-short-clip-small.gif)

## Introduction
Nowadays, there are incredibly cheap "toy" drones available on Amazon that are basically paired-down clones of the early DJI mavic. Only ~$50 to have a 1080p camera for FPV and recording, tiny downard-facing optical flow sensor for position and altitude hold, and a well tuned flight profile out-of-the-box. The only problem with drones like this is that they run closed-source firmware and are locked to only being controlled by a custom mobile app. I thought it would be cool to free some of these drones from their "jail" and write an API and client for accessing the video feed and sending control commands down to the drone by reverse-engineering how the mobile apps work. That way you can turn a highly capable $50 "toy" drone into something that can be programmatically controlled and used for all sorts of applications and experiments.

## Hardware
* WiFi Camera Drone (ranked in order of recommendation):

    | Brand      | Model Number    | Compatibility | Purchase Link                                               | Notes |
    |------------|-----------------|---------------|-------------------------------------------------------------|-------|
    | Loiley     | S29             | Tested    | [Amazon](https://www.amazon.com/dp/B0D53Z84BW)                  | Best build quality, has servo for tilting camera(_not implemented in API yet_)|
    | Hiturbo    | S20             | Tested    | [Amazon](https://www.amazon.com/dp/B0BBVZ849G), [Alternate Amazon Listing](https://www.amazon.com/Beginners-Foldable-Quadcopter-Gestures-Batteries/dp/B0D8LK1KJ3)                  | Original test platform, great build quality|
    | Velcase    | S101            | TODO | [Amazon](https://www.amazon.com/Foldable-Beginners-Quadcopter-Carrying-Positioning/dp/B0CH341G5F/)  | lower quality build, smaller battery and props than S29 & S20|

  _Suspected means the APK for the drone appears to use the exact same packages and libraries as one of the tested drones._

  _TODO means the APK operates with different byte packets and protocols and will have to be added as a new implementation in the API._
  
  Also note that S20, S29 drones _appear_ to be from the same OEM ("Overflew" is usually written somewhere on the drone) and use the same underlying mobile app just re-badged/whitelabeled by different companies selling on Amazon so you may see that same model number sold by a different company and it _likely_ will still be compatible.

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

Launch the backend: 
```
uvicorn web_server:app
```

Launch the frontend web client:
```
npm run dev
```

Open the web client which will be at `http://localhost:5173` and you should see the drone video feed and be able to control it.

To control via a gaming controller, plug it in and move the sticks around for it to be detected and then push the toggle button to switch between keyboard and controller control.

Make sure to fly in a safe area, preferably outdoors with little wind. And note that the "Land" button _currently_ is more of a E-stop button that will stop the drone motors immediately.


## Status
Video feed: solid.

Controls: improved greatly via the web client. 

Web Client: first version is out now.

Also working on adding support for more drones from [Amazon's best-selling drone list](https://www.amazon.com/best-selling-drones/s?k=best+selling+drones).


## Development
To follow along with development, download the [Hiturbo APK](https://play.google.com/store/apps/details?id=com.vison.macrochip.hiturbo.fpv&hl=en_US) from a mirror site and decompile to java files with [jadx](https://github.com/skylot/jadx).
From there, explore the java files like `HyControlConsumer.java` and `UDPHeartbeat.java` to understand the implemenetation of the protocols.
Additionally, Wireshark is your friend for understanding the raw data packets being sent and received. Watch this [video](https://x.com/marshallrichrds/status/1923165437698670818) for an overview into the reverse engineering process used.





