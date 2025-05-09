# Turbodrone
API and client for controlling the Hiturbo S20 camera drone from a computer instead of the closed-source mobile app.

![S20 Drone Short Clip](docs/images/s20-drone-short-clip-small.gif)

## Introduction
Nowadays, there are incredibly cheap "toy" drones available on Amazon that are basically paired-down clones of the early DJI mavic. $45 to have a 1080p camera, tiny downard-facing optical flow sensor, and a well tuned flight profile out-of-the-box. The only problem with drones like this is that they run closed-source firmware and are locked to only being controlled by a custom mobile app. I thought it would be cool to free one of these from its "jail" and write an API for accessing the video feed and sending control commands down to the drone by reverse-engineering how the mobile app works. That way you can turn a highly capable $45 "toy" drone into something that can be programmatically controlled and used for all sorts of applications and experiments.

## Hardware
* S20 foldable drone from Hiturbo: https://www.amazon.com/dp/B0BBVZ849G 
  * Other OEMs for the "S20" drone _may_ work but its likely the controls and video feed come over a slightly different protocol.
* WiFi Dongle ([recommend ALFA Network AWUS036ACM](https://www.amazon.com/Network-AWUS036ACM-Long-Range-Wide-Coverage-High-Sensitivity/dp/B08BJS8FXD) or similar) 
  * S20 drone broadcasts its own WiFi network so your computer will have to connect to it.


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

Make sure WiFi Dongle is plugged in, drone is turned on, connect to the "Hiturbo-S20-XXXXXX" network, and then run the script
```
python receive_video.py
```



## Status
Currently only video feed is working. 
TODO: controls in progress.


## Development
To follow along with development, download the Hiturbo APK from a mirror site and decompile to java files with jadx.
From there, explore the java files like `HyControlConsumer.java` to understand the implemenetation of the protocols.
Additionally, Wireshark is your friend for understanding the raw data packets being sent and received.





