# Turbodrone
Reverse-engineered API and client for controlling some of the best-selling ~$50 "toy" drones on Amazon from a computer replacing the closed-source mobile apps they come with.

![S20 Drone Short Clip](docs/images/s20-drone-short-clip-small.gif)

## Introduction
Nowadays, there are incredibly cheap "toy" drones available on Amazon that are basically paired-down clones of the early DJI mavic. Only ~$50 to have a 1080p camera for FPV and recording, tiny downard-facing optical flow sensor for position and altitude hold, and a well tuned flight profile out-of-the-box. The only problem with drones like this is that they run closed-source firmware and are locked to only being controlled by a custom mobile app. I thought it would be cool to free some of these drones from their "jail" and write an API and client for accessing the video feed and sending control commands down to the drone by reverse-engineering how the mobile apps work. That way you can turn a highly capable $50 "toy" drone into something that can be programmatically controlled and used for all sorts of applications and experiments.

## Hardware
* Camera Drone:
  * Hiturbo S20 foldable drone: https://www.amazon.com/dp/B0BBVZ849G 
    * This is currently the only drone supported, but having decompiled the APKs of other best-selling camera drones on Amazon, a lot of them use the exact same libraries and protocols under-the-hood (if not the _exact_ same codebase: see [Loiley Drone](https://www.amazon.com/dp/B0D53Z84BW) and [its app](https://play.google.com/store/apps/details?id=com.vison.macrochip.loiley.fly&hl=en_US) for an example on how it shares the exact same `com.vision.macrochip.X` package as the Hiturbo app).
* WiFi Dongle ([recommend ALFA Network AWUS036ACM](https://www.amazon.com/Network-AWUS036ACM-Long-Range-Wide-Coverage-High-Sensitivity/dp/B08BJS8FXD) or similar) 
  * drone broadcasts its own WiFi network so your computer will have to connect to it.


## Setup
Move to the `src` directory
```
cd src
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

Make sure WiFi Dongle is plugged in, drone is turned on, connect to the "Hiturbo-S20-XXXXXX" network, and then run the script
```
python receive_video.py
```



## Status
Currently only video feed is working. 
TODO: controls are close to being done.

Also working on adding support for more drones from [Amazon's best-selling drone list](https://www.amazon.com/best-selling-drones/s?k=best+selling+drones).


## Development
To follow along with development, download the [Hiturbo APK](https://play.google.com/store/apps/details?id=com.vison.macrochip.hiturbo.fpv&hl=en_US) from a mirror site and decompile to java files with [jadx](https://github.com/skylot/jadx).
From there, explore the java files like `HyControlConsumer.java` and `UDPHeartbeat.java` to understand the implemenetation of the protocols.
Additionally, Wireshark is your friend for understanding the raw data packets being sent and received.





