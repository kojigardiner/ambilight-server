#!/usr/bin/env python3

## Imports ###
import time
import os
from picamera import PiCamera
from picamera.array import PiYUVArray
import numpy as np
import set_gains
import AmbilightServer

RESOLUTION = (160, 128)          # downscale to this resolution for all other processing
FPS = 60

SCRIPT_NAME = os.path.splitext(__file__)[0]

def main():
  CAMERA = PiCamera(resolution=RESOLUTION,sensor_mode=7,framerate=FPS)
  time.sleep(2.0) # sleep just after setting up camera to ensure the following param sets work properly

  CAMERA.rotation = 180
  CAMERA.exposure_mode = 'off'
  CAMERA.shutter_speed = 10000    # note that framerate above will limit max shutter
  set_gains.set_gain(CAMERA, set_gains.MMAL_PARAMETER_ANALOG_GAIN, 6.0)   # 6x gain + 10ms exposure empirically seems ok
  CAMERA.awb_mode = 'off'         # turn off so we can apply manual settings
  CAMERA.awb_gains = (1.95, 1.25)  # empirically found to match "gray" on TV
  #camera.zoom = (0.1, 0.1, 0.8, 0.8)  # should match what was used in setup_camera.py

  raw_capture = PiYUVArray(CAMERA, size=RESOLUTION)   # create buffer for camera data

  before = time.perf_counter()
  deltas = []
  count = 0
  max_count = 201

  # server = AmbilightServer.AmbilightServer()
  # server.run()

  ### Main loop ###
  CAMERA.start_recording
  for image in CAMERA.capture_continuous(raw_capture, format='yuv', use_video_port=True):    # using video port true seems to cause exposure flicker but is way faster        
    after = time.perf_counter()
    deltas.append((after - before) * 1000)
    raw_capture.truncate(0)     # clear the frame array
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