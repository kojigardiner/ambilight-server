#!/usr/bin/env python3

## Imports ###
import set_gains
from picamera2 import Picamera2, Preview
from libcamera import Transform
import pantilthat as pth
import time
import cv2
import numpy as np
import json
import os
import pid_utils
import sys
import AmbilightServer
from proto import ambilight_pb2
from multiprocessing import Process, Queue
import queue   # for the Empty exception
from matplotlib import pyplot as plt
import TV
from enum import Enum

### Defines ###
DEBUG = False               # set to True to display each frame

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

TV_STATUS_INTERVAL_S = 5   # how often to check the TV status
FADE_TIME_S = 1.5   # how quickly to fade in after tv turns on

class QMsgCamera:
    def __init__(self, frame, roi):
        self.frame = frame
        self.roi = roi

class QMsgTV:
    class TVStatus(Enum):
        ON = 0
        OFF = 1

    def __init__(self, status):
        self.status = status

def read_setup_json():
    """
    Reads the calibration values stored in the setup.json file and returns a
    3-element tuple with (pan, tilt, roi).
    """
    ### Read JSON settings file ###
    setup_filename = CAMERA_SETUP_PATH   # this file defines the camera setup (pan/tilt and roi)
    try:
        open(setup_filename)
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
    camera = Picamera2()
    time.sleep(2.0) # sleep just after setting up camera to ensure the following param sets work properly

    camera.preview_configuration.main.size = RESOLUTION
    camera.preview_configuration.main.format = "BGR888"
    camera.preview_configuration.queue = False
    camera.preview_configuration.controls.FrameRate = FPS
    camera.preview_configuration.controls.AeEnable = False
    camera.preview_configuration.controls.ExposureTime = 10000
    camera.preview_configuration.controls.AnalogueGain = 6.0          # 6x gain + 10ms exposure empirically seems ok
    camera.preview_configuration.controls.ColourGains = (1.95, 1.25)  # empirically found to match "gray" on TV
    camera.preview_configuration.transform = Transform(vflip=1, hflip=1)
    camera.preview_configuration.align()  # adjust resolution if needed
    if camera.preview_configuration.main.size != RESOLUTION:
        print(f"picamera2 changed the configured resolution from {RESOLUTION} to {camera.preview_configuration.main.size}!")

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

def camera_loop(q_camera, q_tv):
    """
    Sets up the camera and pan-tilt head and kicks off the image capture loop.
    """

    ### Start camera ###
    camera, roi = setup_camera() 
    camera.start()

    ### Main loop ###
    last_time = time.perf_counter()   # for tracking duration of loop
    should_capture = False

    while True:
        # Check if there is a new status message from the TV queue
        try:
            qmsg = q_tv.get(block=False)  # non-blocking
            
            if qmsg == QMsgTV.TVStatus.ON:
                should_capture = True
            else:
                should_capture = False
        except queue.Empty:
            pass
        
        # Only capture and push a frame if the TV is on
        if should_capture:
            frame = camera.capture_array()
            q_camera.put(QMsgCamera(frame, roi))

def tv_status_loop(q_tv):
    """
    Checks the status of the TV and provides it to the camera process.
    """

    tv = TV.TV()
    while True:
        if tv.is_on():
            q_tv.put(QMsgTV.TVStatus.ON)
            print("TV is ON!")
        else:
            q_tv.put(QMsgTV.TVStatus.OFF)
            print("TV is OFF!")
        time.sleep(TV_STATUS_INTERVAL_S)
    

def debug_show(frame):
    """
    Shows the given frame on the host display for debug purposes.
    """

    if DEBUG:
        plt.imshow(frame)
        plt.show()
    
def process_and_serve(q_camera, aspect_ratio):
    """
    Kicks off the ambilight servers, then waits for frames to arrive from the 
    camera process. Processes each frame and sends it via the server.
    """

    server = AmbilightServer.AmbilightServer()
    server.run()

    # Create the data array to write results to
    led_array = np.zeros((114, 3),dtype='uint8')

    last_time_ms = time.perf_counter() * 1000
    
    gain = 0
    while True:
        # Get an image and roi from the camera process
        try:
            msg = q_camera.get(block=True, timeout=TV_STATUS_INTERVAL_S)
            gain += (FADE_TIME_S / FPS) # fade in from zero
        except queue.Empty:
            # Send a blank frame if we time out, to prevent stuck lighting
            gain = 0
            continue

        gain = np.clip(gain, 0, 1)
        frame = msg.frame * gain
        roi = msg.roi

        curr_time_ms = time.perf_counter() * 1000

        if ((curr_time_ms - last_time_ms) > (2 / FPS) * 1000):
            print(f"Missed a frame! {curr_time_ms - last_time_ms} ms")
        last_time_ms = curr_time_ms

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
        
        # Average across 6 rows/cols into the frame
        led_array_resize2 = np.zeros(led_array_resize.shape, dtype='uint8')
        led_array_resize2[:,0] = np.mean(led_array_resize[:,:ZONE_SIZE],axis=1)   # left side
        led_array_resize2[:,-1] = np.mean(led_array_resize[:,-ZONE_SIZE:],axis=1)   # right side
        led_array_resize2[0,1:-1] = np.mean(led_array_resize[:ZONE_SIZE,1:-1],axis=0)   # top side
        led_array_resize2[-1,1:-1] = np.mean(led_array_resize[-ZONE_SIZE:,1:-1],axis=0)   # bottom side
        
        debug_show(led_array_resize2)
        
        # Need to make this frame size agnostic
        led_array[0:17] = led_array_resize2[-1,16::-1]          # bottom left (center to corner)
        led_array[17:39] = led_array_resize2[::-1,0]             # left (bottom to top)
        led_array[39:75] = led_array_resize2[0,:]                # top (left to right)
        led_array[75:97] = led_array_resize2[:,-1]               # right (top to bottom)
        led_array[97:114] = led_array_resize2[-1,35:18:-1]       # bottom right (corner to center)

        # Apply gamma luts
        led_array = apply_gamma(led_array)

        server.send(type=ambilight_pb2.MessageType.DATA, payload=led_array.tobytes())


def ambilight():
    """
    Runs the ambilight program by kicking off a child camera process that sends
    frames over a queue to the process_and_serve function, which processes each
    frame and sends the resulting color data to the AmbilightServer object.
    """

    q_camera = Queue()
    q_tv = Queue()
    camera_process = Process(target=camera_loop, args=(q_camera, q_tv))
    camera_process.start()

    tv_status_process = Process(target=tv_status_loop, args=(q_tv,))
    tv_status_process.start()

    process_and_serve(q_camera, "")

if __name__ == '__main__':
    ambilight()
    print('Exiting')
