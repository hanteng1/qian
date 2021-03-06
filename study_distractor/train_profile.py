#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import division
import sys
import collections
import serial
import time
import struct
from array import *
import binascii
import numpy as np
from math import *
from random import randint
from collections import deque
import threading

import os
os.environ['PYTHON_EGG_CACHE'] = '/tmp'

import matplotlib
matplotlib.use('TKAgg')
matplotlib.rcParams['toolbar'] = 'None'

from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.patches as mpatches
from matplotlib.collections import PatchCollection
from matplotlib.widgets import Button

from s_motor_train import motor
mMotor = motor()

from playsound import playsound

#study parameters
isRecording = False
total_profiles = 6
profile_repeat = 5
total_trials = 36 # 6 profile * 5 repeat
current_trial = 0
color_correct_trial = 0
color_accuracy = 0
pause = True
person = 0
block = 0
profile_index = 0
user_action_count = 0
trial_start_temp = 0
trial_end_temp = 0
trial_distraction_correct = 0
trial_isWaitingForAnswer = 0  #0-tesitng, 1-wait for profile, 2-wait for color, 3-check color answer
trial_answer_profile = 0
trial_answer_color = 0
trial_duration = 0
idx_p = -1
idxc_p = -1


def detect_peaks(x, mph=None, mpd=1, threshold=0, edge='rising',
                 kpsh=False, valley=False, show=False, ax=None):

    x = np.atleast_1d(x).astype('float64')
    if x.size < 3:
        return np.array([], dtype=int)
    if valley:
        x = -x
    # find indices of all peaks
    dx = x[1:] - x[:-1]
    # handle NaN's
    indnan = np.where(np.isnan(x))[0]
    if indnan.size:
        x[indnan] = np.inf
        dx[np.where(np.isnan(dx))[0]] = np.inf
    ine, ire, ife = np.array([[], [], []], dtype=int)
    if not edge:
        ine = np.where((np.hstack((dx, 0)) < 0) & (np.hstack((0, dx)) > 0))[0]
    else:
        if edge.lower() in ['rising', 'both']:
            ire = np.where((np.hstack((dx, 0)) <= 0) & (np.hstack((0, dx)) > 0))[0]
        if edge.lower() in ['falling', 'both']:
            ife = np.where((np.hstack((dx, 0)) < 0) & (np.hstack((0, dx)) >= 0))[0]
    ind = np.unique(np.hstack((ine, ire, ife)))
    # handle NaN's
    if ind.size and indnan.size:
        # NaN's and values close to NaN's cannot be peaks
        ind = ind[np.in1d(ind, np.unique(np.hstack((indnan, indnan-1, indnan+1))), invert=True)]
    # first and last values of x cannot be peaks
    if ind.size and ind[0] == 0:
        ind = ind[1:]
    if ind.size and ind[-1] == x.size-1:
        ind = ind[:-1]
    # remove peaks < minimum peak height
    if ind.size and mph is not None:
        ind = ind[x[ind] >= mph]
    # remove peaks - neighbors < threshold
    if ind.size and threshold > 0:
        dx = np.min(np.vstack([x[ind]-x[ind-1], x[ind]-x[ind+1]]), axis=0)
        ind = np.delete(ind, np.where(dx < threshold)[0])
    # detect small peaks closer than minimum peak distance
    if ind.size and mpd > 1:
        ind = ind[np.argsort(x[ind])][::-1]  # sort ind by peak height
        idel = np.zeros(ind.size, dtype=bool)
        for i in range(ind.size):
            if not idel[i]:
                # keep peaks with the same height if kpsh is True
                idel = idel | (ind >= ind[i] - mpd) & (ind <= ind[i] + mpd) \
                    & (x[ind[i]] > x[ind] if kpsh else True)
                idel[i] = 0  # Keep current peak
        # remove the small peaks and sort back the indices by their occurrence
        ind = np.sort(ind[~idel])

    if show:
        if indnan.size:
            x[indnan] = np.nan
        if valley:
            x = -x
        _plot(x, mph, mpd, threshold, edge, valley, ax, ind)

    return ind

peak_list = []
topanddown = 1
base_angle = 0
temp_angle = 0
offset_angle = 0
total_angle = 0
pre_total_angle = 0
firstTopOrBottom = True
goingup = True
reachingPeak = False
hard_peak = 680
hard_valley = 300
temp_peak = hard_peak
temp_valley = hard_valley
a_sensor_state = -1 #0-state, 1-state, 2-state, 3-state
state_cut_ratio = 0.001
state_cut_up = 0
state_cut_down = 0
b_sensor_dir = 1 #1-increase 2-decrease
#running and notrunning
running = False
prev_val = [] #5 frames
diff_prev_val = []
prev_val_ch1 = []
running_ch1 = False
r_count = 0
running_threshold = 7.0
#moving direction
running_clockwise = 1  #1->yes  -1->no 
direction_test_timer = 0
reading_direction = 1
predict_span = 200
buffer_interval = 1000;
running_mode = 1 # 1 -> reset  2-> no reset
mproxity_read = 0
profile_end_angle = 180
profile_start_angle = 20
profile_end_alert = False


def detectRunning(val_list):
    return np.std(val_list)


def detectMovingDirection(val_list):
    if running and len(val_list) > 2:
        vt = val_list[-1] - val_list[0]
        if vt > 0:
            return 1
        elif vt < 0:
            return -1
        else:
            return 0


def detectState(val, up, down):
    st = -1
    if up != 0 and down != 0:
        if val > up:
            st = 0
        elif val < down:
            st = 2
    return st

def AddValue(serial_port, val):

    global hard_valley
    global hard_peak

    if val > hard_peak:
        val = hard_peak
    if val < hard_valley:
        val = hard_valley

    global avg
    global topanddown
    global base_angle
    global temp_angle
    global firstTopOrBottom
    global temp_peak
    global temp_valley
    global total_angle
    global pre_total_angle
    global offset_angle
    global goingup
    global reachingPeak
    global state_cut_up
    global state_cut_down
    global a_sensor_state
    global prev_val
    global prev_val_ch1
    global diff_prev_val
    global running
    global running_clockwise
    global reading_direction
    global direction_test_timer
    global running_ch1
    global predict_span
    global r_count
    global running_threshold
    global profile_end_angle
    global profile_start_angle
    global profile_end_alert
    global mproxity_read

    #study parameters
    global current_trial
    global block
    global profile_index
    global user_action_count
    
    peak_list.append(val)

    if len(peak_list) > 1000:
        peak_list.pop(0)

    prev_val.append(val)
    if len(prev_val) > predict_span:

        prev_val.pop(0)
        std_value = detectRunning(prev_val)
        
        if std_value > running_threshold or running_ch1 == True:  # predict as running, a sensor or b sensor
            #print("running")
            if running == False:
                running = True
                direction_test_timer = 0

                #a start
                if isRecording:
                    user_action_count+=1

            #wait for span/2 frames
            #reading_direction must be 1
            if direction_test_timer < predict_span / 2: #10
                direction_test_timer += 1
                if direction_test_timer == predict_span / 2:

                    if a_sensor_state == -1:
                        running_clockwise = 1

                    elif a_sensor_state == 0:
                        #see sensor 2
                        dir_ch1 = detectMovingDirection(prev_val_ch1)

                        if dir_ch1 == 1:
                            running_clockwise = -1
                        elif dir_ch1 == -1:
                            running_clockwise = 1

                    elif a_sensor_state == 1:
                        a_sensor_state = 1
                        #see sensor 1
                        dir_ch0 = detectMovingDirection(prev_val)

                        if dir_ch0 == 1:
                            running_clockwise = -1
                            #topanddown = 1
                        elif dir_ch0 == -1:
                            running_clockwise = 1


                    elif a_sensor_state == 2:
                        #see sensor 2
                        dir_ch1 = detectMovingDirection(prev_val_ch1)

                        if dir_ch1 == 1:
                            running_clockwise = 1
                        elif dir_ch1 == -1:
                            running_clockwise = -1

                    elif a_sensor_state == 3:
                        a_sensor_state = 3
                        #see sensor 1
                        dir_ch0 = detectMovingDirection(prev_val)

                        if dir_ch0 == 1:
                            running_clockwise = 1
                        elif dir_ch0 == -1:
                            running_clockwise = -1
                            #topanddown = -1

                    reading_direction = 0  #got direction info
                    running_clockwise = 1  #make sure there is no direction
        else:
            if running_ch1 == False:
                if running == True:
                    running = False
                    reading_direction = 1 #waiting for diretion info

                    if running_mode == 1 and total_angle > profile_end_angle:
                        base_angle = 0
                        temp_angle = 0
                        total_angle = 0

                    mMotor.set_action_stop(total_angle)

                    

    if topanddown == 1:
        if val==hard_peak:
            temp_peak = hard_peak
            
            del peak_list[:]
            topanddown = 2

            #angle cal
            if firstTopOrBottom:
                base_angle = 0
                temp_angle = 0
                firstTopOrBottom = False
                reachingPeak = True
                a_sensor_state = 0

            else:
                base_angle += (20*running_clockwise)
                temp_angle = 0
                reachingPeak = True
                state_cut_up = temp_peak - (temp_peak - temp_valley) * state_cut_ratio

            if reading_direction == 0:
                a_sensor_state = 0

    elif topanddown == 2:  #detect the second top
        filter_peaks = detect_peaks(peak_list, mph=hard_peak-1, mpd=20, threshold=0, edge='falling',
                 kpsh=False, valley=False, show=False, ax=None)
    
        if len(filter_peaks)>0:  #found a peak
            del peak_list[:]
            topanddown = -1

            goingup = False
            reachingPeak = False

            if reading_direction == 0:
                if running_clockwise == 1:
                    a_sensor_state = 1
                elif running_clockwise == -1:
                    a_sensor_state = 3

    elif topanddown == -1:
        if val == hard_valley:
            temp_valley = hard_valley
            
            del peak_list[:]
            topanddown = -2

            if firstTopOrBottom:
                base_angle = 0
                temp_angle = 0
                firstTopOrBottom = False
                reachingPeak = True
                a_sensor_state = 2

            else:
                base_angle += (20*running_clockwise)
                temp_angle = 0
                reachingPeak = True
                state_cut_down = temp_valley + (temp_peak - temp_valley) * state_cut_ratio

            if reading_direction == 0:
                a_sensor_state = 2


    elif topanddown == -2:
        filter_valleys = detect_peaks(peak_list, mph=-hard_valley-1, mpd=20, threshold=0, edge='falling',
                 kpsh=False, valley=True, show=False, ax=None)

        if len(filter_valleys)>0:  #found a valley
            del peak_list[:]
            topanddown = 1
            goingup = True
            reachingPeak = False

            if reading_direction == 0:
                if running_clockwise == 1:
                    a_sensor_state = 3
                elif running_clockwise == -1:
                    a_sensor_state = 1

    
    if reachingPeak ==  False:
        if temp_peak*temp_valley != 0:
            if goingup:
                temp_angle = abs(val - temp_valley) * 20 / abs(temp_peak - temp_valley)
            else:
                temp_angle = abs(val - temp_peak) * 20 / abs(temp_peak - temp_valley)

            if running == False:
                    offset_angle = temp_angle

    

    if running_mode == 1: #auto reset
        total_angle = base_angle + temp_angle * running_clockwise - offset_angle
        if total_angle < 0:
            total_angle = 0

        if profile_end_alert == False:
            if total_angle > profile_start_angle and total_angle < (profile_start_angle + 2.0):
                profile_end_alert = True
        else:
            if total_angle > (profile_end_angle - 2):
                playsound("ding2.wav")
                profile_end_alert = False

        if total_angle < pre_total_angle:
            mMotor.get_angle(pre_total_angle, mproxity_read)  
        else:
            mMotor.get_angle(total_angle, mproxity_read)

        pre_total_angle = total_angle 

        # print(mproxity_read)

    if running_mode == 2 and firstTopOrBottom == False:  #no reset
        total_angle = base_angle + temp_angle * running_clockwise

        if total_angle > 360:
            total_angle = 0
            base_angle = 0
            temp_angle = 0

        if total_angle < 0:
            total_angle = 360
            base_angle = 360
            temp_angle = 0

        mMotor.get_angle(total_angle)

def AddValue_Ch1(val):
    global prev_val_ch1
    global running_ch1
    global predict_span
    global running_threshold

    prev_val_ch1.append(val)
    if len(prev_val_ch1) > predict_span:
        prev_val_ch1.pop(0)

        std_value_ch1 = detectRunning(prev_val_ch1)

        if std_value_ch1 > running_threshold:  #running
            if running_ch1 == False:
                running_ch1 = True
        else:
            if running_ch1 == True:
                running_ch1 = False

def serial_read():
    global buffer_interval
    t = threading.currentThread()
    serial_port = serial.Serial(port='/dev/tty.usbmodem1411', baudrate=115200)

    try:
        while getattr(t, "do_run", True):   
            read_val = serial_port.readline()
            read_val_list = [x.strip() for x in read_val.split(',')]

            if buffer_interval > 0:
                buffer_interval -= 1
            else:
                if len(read_val_list) == 2:
                    AddValue(serial_port, int(read_val_list[0])) 
                    AddValue_Ch1(int(read_val_list[1]))         

    except ValueError:
        pass

    while serial_port.inWaiting():
        read_val = serial_port.read(serial_port.inWaiting())
        print("Read:%s" % (binascii.hexlify(read_val)))

    serial_port.close()
    print('hall sensor serial existing...')


def SetIRValue(val):
    global mproxity_read
    mproxity_read = val

def ir_read():
    ir = threading.currentThread()
    serial_port = serial.Serial(port='/dev/tty.usbmodem14211', baudrate=115200)
    try:
        while getattr(ir, "do_run", True):
            read_val = serial_port.readline()
            SetIRValue(int(read_val))
    except ValueError:
        pass

    while serial_port.inWaiting():
        read_val = serial_port.read(serial_port.inWaiting())
        print("ir Read:%s" % (binascii.hexlify(read_val)))

    serial_port.close()
    print('ir sensor serial existing...')
#############################################################################################
next_trial = 0


def main():
    global total_angle
    global temp_angle
    global base_angle
    global current_trial
    global color_correct_trial
    global color_accuracy
    global pause
    global isRecording
    global block
    global person
    global profile_index
    global user_action_count
    global trial_start_temp
    global trial_end_temp
    global trial_distraction_correct
    global trial_isWaitingForAnswer
    global trial_answer_profile
    global trial_answer_color
    global next_trial

    #take user input

    

    while True:
        try:
            next_trial = int(raw_input('enter a trial number: '))  #in total 4 blocks, 2 moving conditions by 2 distractor conditions
            
            if next_trial > 6 or next_trial < 1:
                print("not a valid trial")
                continue

            print("next trial: ", next_trial)
            break
        except ValueError:
            print("not a valid number")

    ir = threading.Thread(target=ir_read)
    ir.start()
            
    t = threading.Thread(target=serial_read)
    t.start()

    mMotor.start()

    def close_event():
        global persons
        global isRecording

        isRecording = False

        mMotor.close()
        mMotor.join()
        
        t.do_run = False
        t.join()

        ir.do_run = False
        ir.join()

        exit()


    def handle_close(event):
        close_event()

    def press(event):
        global current_trial
        global next_trial
        global profile_index
        global base_angle
        global temp_angle
        global total_angle
        global pause

        #mMotor.write_serial(event.key)
        if event.key == ' ':
            pause^=True
            if not pause:
                print("trial start")
                playsound("ding.wav") #indicate start
                profile_index = next_trial
                base_angle = 0
                temp_angle = 0
                total_angle = 0
                mMotor.set_profile(profile_index)

            if pause:
                print("trial end")
                while True:
                    try:
                        next_trial = int(raw_input('enter a trial number: '))  #in total 4 blocks, 2 moving conditions by 2 distractor conditions
                        
                        if next_trial > 6 or next_trial < 1:
                            print("not a valid trial")
                            continue

                        print("next trial: ", next_trial)
                        break
                    except ValueError:
                        print("not a valid number")

        elif event.key == 'q':
            #close
            plt.close(fig)

        elif event.key == 'e' or event.key == 'c' or event.key == 's':
            mMotor.write_serial(event.key)


    fig, p1 = plt.subplots()
    p1.axis("off")
    fig.canvas.set_window_title('Study Train Profile')

    fig.canvas.mpl_connect('close_event', handle_close)
    fig.canvas.mpl_connect('key_press_event', press)


    im_profile_axes = plt.axes([0.0, 0.7, 1.0, 0.2], frameon=True)  # Change the numbers in this array to position your image [left, bottom, width, height])
    im_profile = plt.imread('profile.png')
    im_profile_axes.axis("off")
    im_profile_axes.imshow(im_profile)


    plt.show()

if __name__ == "__main__":
    main()
