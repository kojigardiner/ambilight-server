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
import AmbilightServer
import proto.ambilight_pb2 as ambilight_pb2
from multiprocessing import Process, Queue

### Defines ###
DEBUG = False

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
FPS = 90
DEFAULT_ASPECT = 16/9
WIDE_ASPECT = 2.39/1

SCRIPT_NAME = os.path.splitext(__file__)[0]

CAMERA_SETUP_PATH = '/home/pi/scripts/ambilight-server/src/setup.json'

def read_setup_json():
  """
  Reads the calibration values stored in the setup.json file and returns a
  3-element tuple with (pan, tilt, roi).
  """
  ### Read JSON settings file ###
  setup_filename = CAMERA_SETUP_PATH   # this file defines the camera setup (pan/tilt and roi)
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
  roi = data['roi']

  print('Pan: ' + str(pan))
  print('Tilt: ' + str(tilt))
  print('ROI: ' + str(roi))

  return (pan, tilt, roi)


def setup_camera():
  """
  Initializes the camera and pan-tilt head, and applies the proper settings. 
  Returns the camera object and the ROI (region of interest).
  """

  # Lock camera usage via pid
  pid_utils.update_pid_file("camera.pid")

  ### Setup PiCamera ###
  camera = PiCamera(resolution=RESOLUTION,sensor_mode=7,framerate=FPS)
  time.sleep(2.0) # sleep just after setting up camera to ensure the following param sets work properly

  camera.rotation = 180
  camera.exposure_mode = 'off'

  camera.shutter_speed = 10000    # note that framerate above will limit max shutter
  set_gains.set_gain(camera, set_gains.MMAL_PARAMETER_ANALOG_GAIN, 6.0)   # 6x gain + 10ms exposure empirically seems ok
  camera.awb_mode = 'off'         # turn off so we can apply manual settings
  camera.awb_gains = (1.95,1.25)  # empirically found to match "gray" on TV
  #camera.zoom = (0.1, 0.1, 0.8, 0.8)  # should match what was used in setup_camera.py

  ### Adjust pantilt head ###
  pan, tilt, roi = read_setup_json()
  pt = pth.PanTilt()
  pt.pan(pan)
  pt.tilt(tilt)

  return camera, roi

def apply_gamma(led_data):
  """
  Applies the gamma LUT to the given array of led data. Returns the
  gamma-applied array.
  """

  led_data[:,0] = np.transpose(cv2.LUT(led_data[:,0].astype('uint8'),LUT_R))
  led_data[:,1] = np.transpose(cv2.LUT(led_data[:,1].astype('uint8'),LUT_G))
  led_data[:,2] = np.transpose(cv2.LUT(led_data[:,2].astype('uint8'),LUT_B))
  
  return led_data

def camera_loop(q):
  """
  Sets up the camera and pan-tilt head and kicks off the image capture loop.
  """

  ### Start camera ###
  camera, roi = setup_camera()  
  raw_capture = PiYUVArray(camera, size=RESOLUTION)   # create buffer for camera data

  ### Main loop ###
  last_time = time.perf_counter()   # for tracking duration of loop
  for image in camera.capture_continuous(raw_capture, format='yuv', use_video_port=True):    # using video port true seems to cause exposure flicker but is way faster        
    frame = raw_capture.array
    q.put(raw_capture.array)
    q.put(roi)
    raw_capture.truncate(0)     # clear the frame array

def debug_show(frame):
  """
  Shows the given frame on the host display for debug purposes.
  """

  if DEBUG:
    cv2.imshow('debug', cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    if cv2.waitKey(1) == 27:
       return

def process_and_serve(q, aspect_ratio):
  """
  Kicks off the ambilight servers, then waits for frames to arrive from the 
  camera process. Processes each frame and sends it via the server.
  """

  server = AmbilightServer.AmbilightServer()
  server.run()

  last_time_ms = time.perf_counter() * 1000
  while True:
    # Get an image and roi from the camera process
    image = q.get()
    roi = q.get()
    curr_time_ms = time.perf_counter() * 1000

    if ((curr_time_ms - last_time_ms) > (2 / FPS) * 1000):
       print(f"Missed a frame! {curr_time_ms - last_time_ms} ms")
    last_time_ms = curr_time_ms

    # Capture in YUV to avoid flicker, then convert ourselves to RGB
    frame = cv2.cvtColor(image, cv2.COLOR_YUV2RGB)

    # Uncomment this for debug of individual frames
    # frame = np.empty((128, 160, 3), dtype=np.uint8)    
    # CAMERA.capture(frame, 'rgb')    # this takes 100ms!!

    # Do the perspective transform        
    dst = [[0, 0], [RESOLUTION[0], 0], [RESOLUTION[0], RESOLUTION[1]], [0, RESOLUTION[1]]] # define corners of rectangle (UL, UR, LR, LL)
    M = cv2.getPerspectiveTransform(np.float32(roi), np.float32(dst))     # 0.1ms
    crop = cv2.warpPerspective(frame, M, RESOLUTION)                      # 1.8ms
    
    if aspect_ratio == 'wide':
        crop_portion = int((1 - DEFAULT_ASPECT / WIDE_ASPECT)/2 * crop.shape[0])  # amount to crop from top/bottom
        crop = crop[crop_portion:crop.shape[0]-crop_portion,:]

    debug_show(crop)

    # Resize to the LED grid size
    led_array_resize = cv2.resize(crop,(NUM_COLS,NUM_ROWS))

    debug_show(led_array_resize)
    
    # Create the data array to write results to
    led_array = np.zeros((114, 3),dtype='uint8')
    
    # Average across 6 rows/cols into the frame
    led_array_resize[:,0] = np.mean(led_array_resize[:,:ZONE_SIZE],axis=1)   # left side
    led_array_resize[:,-1] = np.mean(led_array_resize[:,-ZONE_SIZE:],axis=1)   # right side
    led_array_resize[0,:] = np.mean(led_array_resize[:ZONE_SIZE,:],axis=0)   # top side
    led_array_resize[-1,:] = np.mean(led_array_resize[-ZONE_SIZE:,:],axis=0)   # bottom side

    debug_show(cv2.resize(led_array_resize, RESOLUTION))
    
    # Need to make this frame size agnostic
    led_array[0:17] = led_array_resize[-1,16::-1]          # bottom left (center to corner)
    led_array[17:39] = led_array_resize[::-1,0]             # left (bottom to top)
    led_array[39:75] = led_array_resize[0,:]                # top (left to right)
    led_array[75:97] = led_array_resize[:,-1]               # right (top to bottom)
    led_array[97:114] = led_array_resize[-1,35:18:-1]       # bottom right (corner to center)

    # Apply gamma luts
    led_array = apply_gamma(led_array)

    server.send(type=ambilight_pb2.MessageType.DATA, payload=led_array.tobytes())


def ambilight():
  """
  Runs the ambilight program by kicking off a child camera process that sends
  frames over a queue to the process_and_serve function, which processes each
  frame and sends the resulting color data to the AmbilightServer object.
  """

  q = Queue()
  camera_process = Process(target=camera_loop, args=(q,))
  camera_process.start()

  process_and_serve(q, "")

if __name__ == '__main__':
    ambilight()
    print('Exiting')
