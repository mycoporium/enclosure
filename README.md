# Enclosure Automation

Files needed to run the automation service for an enclosure.

## Prerequisites

Currently requires a storage drive mounted at `/media/asustor` containing project directory `MushroomFarm`.

Full path to the current directory containing this README is assumed to be `/media/asustor/MushroomFarm/enclosure`

To install supporting python libraries, use pip to install the `requirements.txt` file.

```
pip3 install -r requirements.txt
```

## enclosure.py

The control program that runs the enclosure automation. It is a multiprocessing script that collects data from the sensor and takes pictures.

The enclosure environment is controller by reading the sensor data and checking whether or not the values are within the defined range.

Depending on the values, an 8-bit value string may be modified. This bit mask is sent to the shift register to control the outlet relay bank.

The relay bank controls physical A/C power outlets which have various devices plugged into them. The script has knowledge of which devices are plugged into which outlet, and can turn them on or off the achieve the range of accepted values for the sensor measurements.

Currently, there are 4 devices controller by the shift register:
  - 12v FAE fan
  - Humidifier
  - Heater
  - Lights

## enclosure.service

For Raspberry Pi or other Linux deployments running systemd, this file defines the enclosure service which run `enclosure.py` at startup, and requires `/media/asustor` to be a mount point.

## shift_reg.py

A class used to control the shift register signalling to store data based on a string of bit values.

An example string might look like '00010011', which might indicate that the lights, humidifier, and fan are ON, while the heater and all unused outlets are off.
