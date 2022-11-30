#!/usr/bin/env python3

## Imports ###
import set_gains
from picamera import PiCamera
from picamera.array import PiYUVArray
import pantilthat as pth
import time
import cv2
import numpy as np
import json
import os
import pid_utils
import sys
sys.path.append("..")
import AmbilightServer

### Defines ###
NUM_ROWS = 22               # layout of LEDs defines a rectangular grid
NUM_COLS = 36
ZONE_SIZE = 6               # how many grid elements to average (see: https://docs.google.com/spreadsheets/d/1SJUuVqygsfONSyFsHIomGW3i-9cAV04BaVC1PwiqIyY/edit#gid=0)

GAMMA_R = 3.0               # gamma to use for color channels (see: https://drive.google.com/file/d/1v7AEu2hqfFiiNiP1ngT0oPzDP944fT0s/view?usp=sharing)
GAMMA_G = 3.3
GAMMA_B = 4.0

LUT_R = (((np.arange(256)/255) ** GAMMA_R) * 255).astype('uint8')
LUT_G = (((np.arange(256)/255) ** GAMMA_G) * 255).astype('uint8')
LUT_B = (((np.arange(256)/255) ** GAMMA_B) * 255).astype('uint8')

RESOLUTION = (160,128)          # downscale to this resolution for all other processing
FPS = 60
DEFAULT_ASPECT = 16/9
WIDE_ASPECT = 2.39/1

SCRIPT_NAME = os.path.splitext(__file__)[0]

def setup_camera():
  global CAMERA
  global ROI
  global FPS

  # Lock camera usage via pid
  pid_utils.update_pid_file("camera.pid")

  ### Setup PiCamera ###
  CAMERA = PiCamera(resolution=RESOLUTION,sensor_mode=7,framerate=FPS)
  time.sleep(2.0) # sleep just after setting up camera to ensure the following param sets work properly

  CAMERA.rotation = 180
  CAMERA.exposure_mode = 'off'

  CAMERA.shutter_speed = 10000    # note that framerate above will limit max shutter
  set_gains.set_gain(CAMERA, set_gains.MMAL_PARAMETER_ANALOG_GAIN, 6.0)   # 6x gain + 10ms exposure empirically seems ok
  CAMERA.awb_mode = 'off'         # turn off so we can apply manual settings
  CAMERA.awb_gains = (1.95,1.25)  # empirically found to match "gray" on TV
  #camera.zoom = (0.1, 0.1, 0.8, 0.8)  # should match what was used in setup_camera.py

  ### Read JSON settings file ###
  setup_filename = '/home/pi/scripts/Ambilight/setup.json'   # this file defines the camera setup (pan/tilt and roi)
  try:
      f = open(setup_filename)
  except OSError:
      print('Could not open setup file: ' + setup_filename)
      print('Make sure to run setup_camera.py first.')
      sys.exit(1)

  with open(setup_filename) as json_file:
      data = json.load(json_file)

  pan = data['pan']
  tilt = data['tilt']
  ROI = data['roi']

  print('Pan: ' + str(pan))
  print('Tilt: ' + str(tilt))
  print('ROI: ' + str(ROI))

  ### Adjust pantilt head ###
  pt = pth.PanTilt()
  pt.pan(pan)
  pt.tilt(tilt)

def apply_gamma(led_data):
  led_data[:,0] = np.transpose(cv2.LUT(led_data[:,0].astype('uint8'),LUT_R))
  led_data[:,1] = np.transpose(cv2.LUT(led_data[:,1].astype('uint8'),LUT_G))
  led_data[:,2] = np.transpose(cv2.LUT(led_data[:,2].astype('uint8'),LUT_B))
  
  return led_data

def camera_loop(aspect_ratio, server):
  global CAMERA
  global ROI

  last_time = 0   # for tracking duration of loop

  raw_capture = PiYUVArray(CAMERA, size=RESOLUTION)   # create buffer for camera data

  ### Main loop ###
  for image in CAMERA.capture_continuous(raw_capture, format='yuv', use_video_port=True):    # using video port true seems to cause exposure flicker but is way faster        
      # print((time.clock_gettime_ns(time.CLOCK_BOOTTIME)-last_time) / 1000)
      last_time = time.clock_gettime_ns(time.CLOCK_BOOTTIME)

      # Capture in YUV to avoid flicker, then convert ourselves to RGB
      frame = cv2.cvtColor(image.array, cv2.COLOR_YUV2RGB)

      # Uncomment this for debug of individual frames
      # frame = np.empty((128, 160, 3), dtype=np.uint8)    
      # CAMERA.capture(frame, 'rgb')    # this takes 100ms!!

      # Do the perspective transform        
      dst = [[0,0],[RESOLUTION[0],0],[RESOLUTION[0],RESOLUTION[1]],[0,RESOLUTION[1]]] # define corners of rectangle (UL, UR, LR, LL)
      M = cv2.getPerspectiveTransform(np.float32(ROI),np.float32(dst))    # 0.1ms
      crop = cv2.warpPerspective(frame,M,RESOLUTION)                      # 1.8ms
      
      if aspect_ratio == 'wide':
          crop_portion = int((1 - DEFAULT_ASPECT / WIDE_ASPECT)/2 * crop.shape[0])  # amount to crop from top/bottom
          crop = crop[crop_portion:crop.shape[0]-crop_portion,:]

      # Uncomment this to display frames to screen
      # cv2.imshow('test',cv2.cvtColor(crop))
      # if cv2.waitKey(1) == 27:
      #     break

      # Resize to the LED grid size
      led_array_resize = cv2.resize(crop,(NUM_COLS,NUM_ROWS))
      
      # Create the data array to write results to
      led_array = np.zeros((114,3),dtype='uint8')
      
      # Average across 6 rows/cols into the frame
      led_array_resize[:,0] = np.mean(led_array_resize[:,:ZONE_SIZE],axis=1)   # left side
      led_array_resize[:,-1] = np.mean(led_array_resize[:,NUM_COLS-1:NUM_COLS-1-ZONE_SIZE:-1],axis=1)   # right side
      led_array_resize[0,:] = np.mean(led_array_resize[:ZONE_SIZE,:],axis=0)   # top side
      led_array_resize[-1,:] = np.mean(led_array_resize[NUM_ROWS-1:NUM_ROWS-1-ZONE_SIZE:-1,:],axis=0)   # bottom side
      
      # Need to make this frame size agnostic
      led_array[0:17] = led_array_resize[-1,17:0:-1]          # bottom left (center to corner)
      led_array[17:39] = led_array_resize[::-1,0]             # left (bottom to top)
      led_array[39:75] = led_array_resize[0,:]                # top (left to right)
      led_array[75:97] = led_array_resize[:,-1]               # right (top to bottom)
      led_array[97:114] = led_array_resize[-1,35:18:-1]       # bottom right (corner to center)

      # # Convert from YUV to RGB
      # led_array = color_convert.convert_picamera_yuv2rgb(led_array)

      # Apply gamma luts
      led_array = apply_gamma(led_array)

      #print(led_array)
      
      server.send(led_array.tobytes())
      
      raw_capture.truncate(0)     # clear the frame array

def tv_color():
  server = AmbilightServer.AmbilightServer()
  server.run()

  setup_camera()  
  camera_loop("", server)

if __name__ == '__main__':
    tv_color()
    print('Exiting')