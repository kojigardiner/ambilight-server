#!/usr/bin/env python3

import argparse
import time
import pantilthat as pth
import numpy as np
# import cv2
import matplotlib.pyplot as plt
import json
from picamera2 import Picamera2, Preview
from libcamera import Transform

RESOLUTION = (160,128)          # actual resolution we will be processing
FPS = 90
FRAME_DUR_US = int(1/FPS * 1e6)

def select_roi(frame):   
    # need to flip color order for showing in matplotlib
    plt.imshow(frame)
    roi = np.around(plt.ginput(4)).astype(int)
    # print(points)

    # note ginput returns (X,Y) coords while cv2 frame is in (row,col) form
    # plt.imshow(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
    plt.close()
    plt.show()

    # dst = [[0,0],[RESOLUTION[0],0],[RESOLUTION[0],RESOLUTION[1]],[0,RESOLUTION[1]]] # define corners of rectangle (UL, UR, LR, LL)
    # M = cv2.getPerspectiveTransform(np.float32(roi),np.float32(dst))    # 0.1ms
    # crop = cv2.warpPerspective(frame,M,RESOLUTION)                      # 1.8ms

    return roi

def setup_camera():
    picam2 = Picamera2()
    picam2.preview_configuration.main.size = RESOLUTION
    picam2.preview_configuration.main.format = "BGR888"
    picam2.preview_configuration.queue = False
    picam2.preview_configuration.controls.FrameRate = FPS
    picam2.preview_configuration.controls.AeEnable = False
    picam2.preview_configuration.controls.ExposureTime = 10000
    picam2.preview_configuration.controls.AnalogueGain = 30.0
    picam2.preview_configuration.controls.ColourGains = (1.95, 1.25)
    picam2.preview_configuration.transform = Transform(vflip=1, hflip=1)
    picam2.preview_configuration.align()  # adjust resolution if needed
    if picam2.preview_configuration.main.size != RESOLUTION:
        print(f"picamera2 changed the configured resolution from {RESOLUTION} to {picam2.preview_configuration.main.size}!")

    picam2.start_preview(Preview.QT)  # use QT to enable X-forwarding

    # time.sleep(2.0)
    # camera.rotation = 180
    # camera.exposure_mode = 'off'
    # camera.shutter_speed = 10000
    # set_gains.set_gain(camera, set_gains.MMAL_PARAMETER_ANALOG_GAIN, 30.0)
    # camera.awb_mode = 'off'         #
    # camera.awb_gains = (1.95,1.25)  # empirically found to match "gray" on TV
    #camera.zoom = (0.1, 0.1, 0.8, 0.8)

    picam2.start()

    return picam2

def setup_pantilt():
    pt = pth.PanTilt()
    move_amount = 2

    print('''
    Type a key and hit enter to pan/tilt.
    Hit enter again to select the ROI.

    a = left
    d = right
    w = up
    s = down
    x = exit
    enter = select ROI''')

    while True:
        key = input()
        print('pressed ' + key + ' key')
        if key == 'a':
            pt.pan(move_amount + pt.get_pan())
        elif key == 'd':
            pt.pan(-1 * move_amount + pt.get_pan())
        elif key == 'w':
            pt.tilt(-1 * move_amount + pt.get_tilt())
        elif key =='s':
            pt.tilt(move_amount + pt.get_tilt())
        elif key =='':
            break
        print(f"pan: {pt.get_pan()}, tilt: {pt.get_tilt()}")
    return (pt.get_pan(), pt.get_tilt())

def setup_roi(picam2):
    array = picam2.capture_array("main")
    picam2.stop_preview()
    return select_roi(array)
    
def stop_camera(picam2):
    picam2.stop()

def main():
    parser = argparse.ArgumentParser(description="Setup the camera.")
    parser.add_argument("-n", "--no-pantilt", action='store_true', default=False, help="Disable pan-tilt control")
    
    args = parser.parse_args()
    
    picam2 = setup_camera()
    print('Set up your camera and LED region of interest (ROI). Hit enter to continue.')
    while True:
        key = input()
        if key == '':
            break

    if args.no_pantilt:
        pan = 0
        tilt = 0
    else:
        (pan, tilt) = setup_pantilt()
    roi = setup_roi(picam2)
    stop_camera(picam2)

    print('Settings:')
    print('Pan:' + str(pan))
    print('Tilt: ' + str(tilt))
    print('ROI: ' + str(roi))

    dict_to_write = {}
    dict_to_write['pan'] = pan
    dict_to_write['tilt'] = tilt
    dict_to_write['roi'] = roi.tolist()

    with open('setup.json','w') as outfile:
        json.dump(dict_to_write, outfile)

if __name__=="__main__":
    main()