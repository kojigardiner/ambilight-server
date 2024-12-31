# Ambilight Server

## Set Up

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
4. Clone this repository onto the Pi.
5. Create a Python virtual environment with system packages (including picamera2) and activate it:
```
python3 -m venv --system-site-packages env
source activate env/bin/activate
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
9. Auto-start services
```
sudo cp ambilight.service /etc/systemd/system
sudo cp ps5-status.service /etc/systemd/system

sudo chmod +x /etc/systemd/system/ambilight.service
sudo chmod +x /etc/systemd/system/ps5-status.service

sudo systemctl enable ambilight.service
sudo systemctl enable ps5-status.service
```
10. Set up camera position. SSH into the pi with X-forwarding, then run the setup script and follow the instructions.
```
ssh -X raspberrypi.local

python3 ambilight-server/src/setup_camera.py
```

## Debug
- To setup VNC, run raspi-config:
```
sudo raspi-config

# Select "Interface Options" -> "VNC"
```


## References
- https://github.com/iharosi/ps5-wake
- https://github.com/pimoroni/pantilt-hat
- https://github.com/supersaiyanmode/PyWebOSTV
