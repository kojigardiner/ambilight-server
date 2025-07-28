# Ambilight Server

## Set Up
Follow the instructions below to set up the Ambilight Server on a [Raspberry Pi 4](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/) with a [Pimoroni Pan-Tilt Hat](https://shop.pimoroni.com/products/pan-tilt-hat?variant=22408353287) and [Camera Module V2](https://www.raspberrypi.com/products/camera-module-v2/).

1. Setup Raspberry Pi SD card using [Raspberry Pi Imager](https://www.raspberrypi.com/software/). Use 64-bit Raspberry Pi OS and select advanced options to set up WiFi credentials and SSH public key.
2. Insert SD card and boot Raspberry Pi. SSH into device and update OS:
```
sudo apt update
sudo apt upgrade
```
3. Install OpenCV. Do not use pip as it causes compatibility issues with QT.
```
sudo apt install -y python3-opencv
```
4. Clone this repository onto the Pi:
```
mkdir ~/repos; cd ~/repos
git clone git@github.com:kojigardiner/ambilight-server.git
```
6. Create a Python virtual environment with system packages (including picamera2) and activate it:
```
cd ~/repos/ambilight-server
python3 -m venv --system-site-packages env
source env/bin/activate
```
6. Install requirements:
```
python3 -m pip install -r src/requirements.txt
```
7. Enable I2C for pantilthat:
```
sudo raspi-config nonint do_i2c 0
```
8. Test scripts
```
python3 ps5_status.py
python3 ambilight.py
```
9. Set up camera position. SSH into the pi with X-forwarding, then run the setup script and follow the instructions.
```
ssh -X raspberrypi.local

python3 ambilight-server/src/setup_camera.py
```
10. Auto-start services
```
sudo cp ambilight-server/services/ambilight.service /etc/systemd/system
sudo cp ambilight-server/services/ps5-status.service /etc/systemd/system

sudo chmod +x /etc/systemd/system/ambilight.service
sudo chmod +x /etc/systemd/system/ps5-status.service

sudo systemctl enable ambilight.service
sudo systemctl enable ps5-status.service

sudo reboot
```

## Debug
- To setup VNC, run raspi-config:
```
sudo raspi-config

# Select "Interface Options" -> "VNC"
```
- To check the status of services:
```
sudo systemctl status ambilight.service
sudo systemctl status ps5-status.service
```
- To debug the camera, stop the service first:
```
sudo systemctl stop ambilight.service
```
- When finished, restart the service:
```
sudo systemctl start ambilight.service
```

## References
- https://github.com/iharosi/ps5-wake
- https://github.com/pimoroni/pantilt-hat
- https://github.com/supersaiyanmode/PyWebOSTV
