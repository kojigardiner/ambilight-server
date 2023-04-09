#!/usr/bin/env python3

## Imports ###
import time
import os
from picamera2 import Picamera2, Preview
from libcamera import Transform
import numpy as np
import set_gains

RESOLUTION = (160, 128)          # downscale to this resolution for all other processing
FPS = 90

SCRIPT_NAME = os.path.splitext(__file__)[0]

def main():
  picam2 = Picamera2()
  picam2.preview_configuration.main.size = RESOLUTION
  picam2.preview_configuration.main.format = "XBGR8888"
  picam2.preview_configuration.queue = False
  picam2.preview_configuration.controls.FrameRate = FPS
  picam2.preview_configuration.controls.AeEnable = False
  picam2.preview_configuration.controls.ExposureTime = 10000
  picam2.preview_configuration.controls.AnalogueGain = 6.0
  picam2.preview_configuration.controls.ColourGains = (1.95, 1.25)
  picam2.preview_configuration.transform = Transform(vflip=1, hflip=1)
  picam2.preview_configuration.align()  # adjust resolution if needed
  if picam2.preview_configuration.main.size != RESOLUTION:
    print(f"picamera2 changed the configured resolution from {RESOLUTION} to {picam2.preview_configuration.main.size}!")


  # CAMERA = PiCamera(resolution=RESOLUTION,sensor_mode=7,framerate=FPS)
  # time.sleep(2.0) # sleep just after setting up camera to ensure the following param sets work properly

  # CAMERA.rotation = 180
  # CAMERA.exposure_mode = 'off'
  # CAMERA.shutter_speed = 10000    # note that framerate above will limit max shutter
  # set_gains.set_gain(CAMERA, set_gains.MMAL_PARAMETER_ANALOG_GAIN, 6.0)   # 6x gain + 10ms exposure empirically seems ok
  # CAMERA.awb_mode = 'off'         # turn off so we can apply manual settings
  # CAMERA.awb_gains = (1.95, 1.25)  # empirically found to match "gray" on TV
  # #camera.zoom = (0.1, 0.1, 0.8, 0.8)  # should match what was used in setup_camera.py

  # raw_capture = PiYUVArray(CAMERA, size=RESOLUTION)   # create buffer for camera data

  before = time.perf_counter()
  deltas = []
  count = 0
  max_count = 201

  # server = AmbilightServer.AmbilightServer()
  # server.run()

  ### Main loop ###
  picam2.start()
  # for image in CAMERA.capture_continuous(raw_capture, format='yuv', use_video_port=True):    # using video port true seems to cause exposure flicker but is way faster        
  while True:
    frame = picam2.capture_array()
    after = time.perf_counter()
    deltas.append((after - before) * 1000)
    before = time.perf_counter()
    count += 1
    if (count == max_count):
      break
  deltas.pop(0) # remove first, junk reading due to init
  deltas = np.array(deltas)
  print(f"frames: {len(deltas)}")
  print(f"expected ms: {1 / FPS * 1000}")
  print(f"avg ms: {np.average(deltas)}")
  print(f"stdev ms: {np.std(deltas)}")
  print(f"min: {np.min(deltas)}")
  print(f"max: {np.max(deltas)}")

if __name__ == '__main__':
    main()