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

# Building RPi-Enclosure SD card and configuring the OS

Image the SD card

```
xzcat 2023-05-03-raspios-bullseye-arm64-lite.img.xz | sudo dd bs=1M of=/dev/sdb
```

- Connect HDMI and USB keyboard
- Select keyboard format
- Create user:
  - pienc
  - pienclosure42069
- Login

```
sudo raspi-config
```

- Interfaces...
  - Enable SSH
  - Enable SPI
  - Enable I2C
- Localization...
  - Locale: en_US.UTF-8 UTF-8
  - Timezone: US Eastern
  - WLAN Country: US

Get IP address

```
$ ip addr list
```

Authorize *local* SSH key

```
[user@localdev]$ ssh-copy-id -i ~/.ssh/id_rsa.pub pienc@192.168.0.31
```

Test SSH key login

Update, upgrade, install packages

```
$ sudo apt update && sudo apt upgrade && sudo apt install vim python3-pip
```

Disable GUI

```
sudo systemctl set-default multi-user.target
```

Install python dependencies

```
$ cd /media/asustor/MushroomFarm/services && pip3 install -r requirements.txt
```

Edit `/etc/fstab`

```
192.168.0.120:/volume1/Backup/data	/media/asustor	nfs	nofail,x-systemd.automount,x-systemd.requires=network-online.target,x-systemd.device-timeout=10s	0 0
```

Create and start enclosure service

```
$ sudo cp /media/asustor/MushroomFarm/services/enclosure.service /etc/systemd/system/
$ sudo systemctl daemon-reload
$ sudo systemctl enable enclosure
$ sudo systemctl start enclosure
```

Verify that it's running

```
$ journalctl -xe
```

# Improvements / TODO

  - Buzzer alarm
  - Upgrade jumper wires to plugs and cables
  - Set one outlet to always-on (bonus points if it can switch between relay and always-on)
  - Single components board
  - Move camera down for better view, or use fish-eye lens
    - Maybe also a camera the does IR to see through the fog? 
    - Perhaps https://www.adafruit.com/product/5660
  - LCD display for data output, mounted to lid
  - [DONE] Data overlay on images
  - [DONE] Graphs / Charts
  - HTTP API controller
  - Soil moisture sensor
  - Sensor enclosure / protection to prevent moisture from destroying the breakout board
  - Mounted LED lighting through (?) roof
  - Config files / mushroom profiles
  - The humidifier drips water into the enclosure from above. Would be better if the port was horizontal and the unit below so excess water drips back into the device instead of enclosure.
    - There really is a lot of water. On day 4 there's like an inch of standing water.
    - The port should go... in the side? I would really like to have it come up through the bottom, with the humidifier underneath, and an extension tube to go up through the substrate (if any), but that's kind of stupid.
    - For a side-hole in the lid, the port would need an elbow pointing up, to make sure the excess water drains back inside
  - The mushrooms seem to be favoring the side away from the fan. Perhaps direct air onto the block is causing this.
    - Possible to create a baffle to disperse air, maybe sideways?
  - The humidity is dropping below minimum due to velocity of the data point. It reaches 80% before the humidifier can raise it, despite being set to 85%.
    - [DUMB] Solution 1: Change the humidity profile to 90% instead of 85%
    - [SMRT] Solution 2: Code the monitor to track velocity of data points, as well as delay in mechanism's affect. Use this info to compensate.

