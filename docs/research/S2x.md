# Research for the S2x drones (S20, S29)


## Chipset
They both seem to use the [XR872AT](https://jlcpcb.com/partdetail/MACHINEINTELLIGENCE-XR872AT/C879208) MCU which is a Cortex-M4 ARM processor.
This seems to be the main SDK for developing firmware for the XR872: https://github.com/XradioTech/xradio-skylark-sdk




## Notes
`nmap` on all TCP ports yielded only 8888 being open. Likely a backup for the main video feed over UDP.