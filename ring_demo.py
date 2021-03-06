#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import division
import sys
import collections
import serial
import time
import struct
#import msvcrt
from array import *
import binascii
import numpy as np
from math import *

import os
os.environ['PYTHON_EGG_CACHE'] = '/tmp'

import matplotlib
matplotlib.use('TKAgg')

from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.patches as mpatches
from matplotlib.collections import PatchCollection
from collections import deque
#threading
import threading

from motor import motor
from matplotlib.widgets import Button

mMotor = motor()


#from proximity import proximity
#mProximity = proximity()

axis_span = 1000

#initilize the channle buffers
ch0_buf = deque(0 for _ in range(axis_span))
ch1_buf = deque(0 for _ in range(axis_span))
avg = 0


#communication with arduino
def write_serial(serial_port, val_string):
    serial_port.write(val_string)


"""
tick_event = 0
def tick_tick(serial_port):
    global total_angle
    global tick_event

    if total_angle >= 15 and tick_event == 0:
        write_serial(serial_port, "e")
        tick_event = 1
        print("event 1 called")
        
"""


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
peak_x = []
peak_y = []
valley_x = []
valley_y = []
topanddown = 1

stop_x = []
stop_y = []

base_angle = 0
temp_angle = 0
offset_angle = 0
total_angle = 0
pre_total_angle = 0

firstTopOrBottom = True
goingup = True
reachingPeak = False

hard_peak = 650
hard_valley = 390

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
r_count = 0
running_threshold = 7.0
#moving direction
running_clockwise = 1  #1->yes  -1->no 
direction_test_timer = 0
reading_direction = 1


predict_span = 200

running_mode = 1 # 1 -> reset  2-> no reset


mproxity_read = 0


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
    global mproxity_read
    
    ch0_buf.append(val)
    ch0_buf.popleft()
    
    """
    avg = avg + 0.1*(val-avg)
    ch1_buf.append(avg)
    ch1_buf.popleft()
    """

    peak_list.append(val)

    if len(peak_list) > 1000:
        peak_list.pop(0)

    prev_val.append(val)
    if len(prev_val) > predict_span:

        prev_val.pop(0)

        std_value = detectRunning(prev_val)

        #print(std_value)
        
        if std_value > running_threshold or running_ch1 == True:  # predict as running, a sensor or b sensor
            #print("running")
            if running == False:
                running = True
                direction_test_timer = 0

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

                        #print("ch1 dir: %s"%dir_ch1)

                        if dir_ch1 == 1:
                            running_clockwise = -1
                            #a_sensor_state = 3
                        elif dir_ch1 == -1:
                            running_clockwise = 1
                            #a_sensor_state = 1

                    elif a_sensor_state == 1:
                        a_sensor_state = 1
                        #see sensor 1
                        dir_ch0 = detectMovingDirection(prev_val)

                        #print("ch0 dir: %s"%dir_ch0)

                        if dir_ch0 == 1:
                            running_clockwise = -1
                            #topanddown = 1
                        elif dir_ch0 == -1:
                            running_clockwise = 1


                    elif a_sensor_state == 2:
                        #see sensor 2
                        dir_ch1 = detectMovingDirection(prev_val_ch1)
                        #print("ch1 dir: %s"%dir_ch1)

                        if dir_ch1 == 1:
                            running_clockwise = 1
                            #a_sensor_state = 3
                        elif dir_ch1 == -1:
                            running_clockwise = -1
                            #a_sensor_state = 1

                    elif a_sensor_state == 3:
                        a_sensor_state = 3
                        #see sensor 1
                        dir_ch0 = detectMovingDirection(prev_val)

                        #print("ch0 dir: %s"%dir_ch0)

                        if dir_ch0 == 1:
                            running_clockwise = 1
                        elif dir_ch0 == -1:
                            running_clockwise = -1
                            #topanddown = -1

                    reading_direction = 0  #got direction info

                    running_clockwise = 1
                    #print(running_clockwise)



                
                
                

        else:
            #r_count = r_count + 1
            #print(r_count)  #predict as not running
            if running_ch1 == False:
                if running == True:
                    running = False
                    reading_direction = 1 #waiting for diretion info

                    #print("             %s"%a_sensor_state)

                    """
                    temp_st = detectState(val, state_cut_up, state_cut_down)
                    if temp_st != -1:
                        a_sensor_state = temp_st

                    #del prev_val_ch1[:]
                    """

                    # if running_mode == 1 and total_angle > 300:
                    if running_mode == 1 and total_angle > 180:
                        base_angle = 0
                        temp_angle = 0
                        total_angle = 0

                    mMotor.set_action_stop(total_angle)

                    #record stop points
                    stop_x.append(axis_span)
                    stop_y.append(val)

        
       
        
    #running or not
    #print(running)
    #print("             %s"%(val))


    if topanddown == 1:
        
        """
        filter_peaks = detect_peaks(peak_list, mph=920, mpd=20, threshold=0, edge='rising',
                 kpsh=False, valley=False, show=False, ax=None)
    
        if len(filter_peaks)>0:  #found a peak
            peak_x.append(axis_span)
            peak_y.append(peak_list[filter_peaks[-1]])
            temp_peak = peak_list[filter_peaks[-1]]
            goingup = False
            del peak_list[:]
            topanddown = 2

            #angle cal
            if firstTopOrBottom:
                base_angle = 0
                temp_angle = 0
                firstTopOrBottom = False
                #initial closewise, see sensor 2
                dir_ch1 = detectMovingDirection(prev_val_ch1)
                if dir_ch1 == 1:
                    running_clockwise = 1 #-1
                elif dir_ch1 == -1:
                    running_clockwise = 1

            else:
                base_angle += (20*running_clockwise)

                temp_angle = 0
                reachingPeak = True
                state_cut_up = temp_peak - (temp_peak - temp_valley) * state_cut_ratio

            a_sensor_state = 0

            """

        if val==hard_peak:
            peak_x.append(axis_span)
            peak_y.append(hard_peak)
            temp_peak = hard_peak
            
            del peak_list[:]
            topanddown = 2

            #print(topanddown)

            #angle cal
            if firstTopOrBottom:

                #print("first top")
                base_angle = 0
                temp_angle = 0
                firstTopOrBottom = False
                reachingPeak = True
                a_sensor_state = 0
                #initial closewise, see sensor 2
                """
                dir_ch1 = detectMovingDirection(prev_val_ch1)
                if dir_ch1 == 1:
                    running_clockwise = -1
                elif dir_ch1 == -1:
                    running_clockwise = 1
                """

            else:

                base_angle += (20*running_clockwise)

                temp_angle = 0
                reachingPeak = True
                state_cut_up = temp_peak - (temp_peak - temp_valley) * state_cut_ratio

            if reading_direction == 0:
                a_sensor_state = 0

            #print("sensor_state: %s" % a_sensor_state)


    elif topanddown == 2:  #detect the second top
        filter_peaks = detect_peaks(peak_list, mph=hard_peak-1, mpd=20, threshold=0, edge='falling',
                 kpsh=False, valley=False, show=False, ax=None)
    
        if len(filter_peaks)>0:  #found a peak
            peak_x.append(axis_span)
            peak_y.append(peak_list[filter_peaks[-1]])
            del peak_list[:]
            topanddown = -1

            #print(topanddown)

            goingup = False
            reachingPeak = False

            if reading_direction == 0:
                if running_clockwise == 1:
                    a_sensor_state = 1
                elif running_clockwise == -1:
                    a_sensor_state = 3

    elif topanddown == -1:

        """
        filter_valleys = detect_peaks(peak_list, mph=-50, mpd=20, threshold=0, edge='rising',
                 kpsh=False, valley=True, show=False, ax=None)

        if len(filter_valleys)>0:  #found a valley
            valley_x.append(axis_span)
            valley_y.append(peak_list[filter_valleys[-1]])
            temp_valley = peak_list[filter_valleys[-1]]
            goingup = True
            del peak_list[:]
            topanddown = -2

            if firstTopOrBottom:
                base_angle = 0
                temp_angle = 0
                firstTopOrBottom = False
                #initial closewise, see sensor 2
                dir_ch1 = detectMovingDirection(prev_val_ch1)
                if dir_ch1 == 1:
                    running_clockwise = 1
                elif dir_ch1 == -1:
                    running_clockwise = 1 #-1

            else:
                base_angle += (20*running_clockwise)
                temp_angle = 0
                reachingPeak = True
                state_cut_down = temp_valley + (temp_peak - temp_valley) * state_cut_ratio

            a_sensor_state = 2
        """

        if val == hard_valley:

            valley_x.append(axis_span)
            valley_y.append(hard_valley)
            temp_valley = hard_valley
            
            del peak_list[:]
            topanddown = -2

            #print(topanddown)

            if firstTopOrBottom:
                base_angle = 0
                temp_angle = 0
                firstTopOrBottom = False
                reachingPeak = True
                a_sensor_state = 2
                #initial closewise, see sensor 2

                """
                dir_ch1 = detectMovingDirection(prev_val_ch1)
                if dir_ch1 == 1:
                    running_clockwise = 1
                elif dir_ch1 == -1:
                    running_clockwise = 1 #-1
                """

            else:
                base_angle += (20*running_clockwise)
                temp_angle = 0
                reachingPeak = True
                state_cut_down = temp_valley + (temp_peak - temp_valley) * state_cut_ratio

            if reading_direction == 0:
                a_sensor_state = 2

            #print("sensor_state: %s" % a_sensor_state)


    elif topanddown == -2:
        filter_valleys = detect_peaks(peak_list, mph=-hard_valley-1, mpd=20, threshold=0, edge='falling',
                 kpsh=False, valley=True, show=False, ax=None)

        if len(filter_valleys)>0:  #found a valley
            valley_x.append(axis_span)
            valley_y.append(peak_list[filter_valleys[-1]])
            del peak_list[:]
            topanddown = 1
            goingup = True
            reachingPeak = False

            if reading_direction == 0:
                if running_clockwise == 1:
                    a_sensor_state = 3
                elif running_clockwise == -1:
                    a_sensor_state = 1

            #print(topanddown)

    #print(topanddown)

    
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

        #mproxity_read = mProximity.read_value_thread()
        #mproxity_read = mProximity.prox_read


        if total_angle < pre_total_angle:
            #total_angle = pre_total_angle
            
            mMotor.get_angle(pre_total_angle, mproxity_read)  
        else:
            mMotor.get_angle(total_angle, mproxity_read)  
        

        pre_total_angle = total_angle 
        #print(mproxity_read)

    if running_mode == 2 and firstTopOrBottom == False:  #no reset
        #print("base%s, temp%s"%(base_angle, temp_angle))
        total_angle = base_angle + temp_angle * running_clockwise

        if total_angle > 360:
            total_angle = 0
            base_angle = 0
            temp_angle = 0

        if total_angle < 0:
            total_angle = 360
            base_angle = 360
            temp_angle = 0


        #if mMotor.trigger_state > 0:
        # mMotor.get_angle(total_angle)

    if len(peak_x)>0:
        for itrx in range(len(peak_x)):
            peak_x[itrx] = peak_x[itrx] - 1

            #print(peak_x[itrx])

    if len(valley_x) > 0:
        for itrx in range(len(valley_x)):
            valley_x[itrx] = valley_x[itrx] - 1

    if len(stop_x) > 0:
        for itrx in range(len(stop_x)):
            stop_x[itrx] = stop_x[itrx] - 1

    #print(peak_x)

    





#variables for b sensor
prev_val_ch1 = []
running_ch1 = False

def AddValue_Ch1(val):

    #print("       %s"%(val))
    global prev_val_ch1
    global running_ch1
    global predict_span
    global running_threshold
    
    ch1_buf.append(val)
    ch1_buf.popleft()

    prev_val_ch1.append(val)
    if len(prev_val_ch1) > predict_span:
        prev_val_ch1.pop(0)

        std_value_ch1 = detectRunning(prev_val_ch1)

        #print("            %s" %(std_value_ch1))

        if std_value_ch1 > running_threshold:  #running
            if running_ch1 == False:
                running_ch1 = True
        else:
            if running_ch1 == True:
                running_ch1 = False

buffer_interval = 1000;

def serial_read():
    global buffer_interval
    t = threading.currentThread()
    serial_port = serial.Serial(port='/dev/tty.usbmodem14121', baudrate=115200)
    # serial_port = serial.Serial(port='/dev/tty.usbmodem1411', baudrate=115200)
    
    sx = 0
    try:
        while getattr(t, "do_run", True):  
            read_val = serial_port.readline()
            #split and reading
            read_val_list = [x.strip() for x in read_val.split(',')]
            #print("read:%s"%(read_val))


            if buffer_interval > 0:
                buffer_interval -= 1
            else:
                


                if len(read_val_list) == 2:
                    AddValue(serial_port, int(read_val_list[0])) 
                    AddValue_Ch1(int(read_val_list[1]))         

            #time.sleep(0.1)  # ~200Hz
    except ValueError:
        pass

    
    
    while serial_port.inWaiting():
        read_val = serial_port.read(serial_port.inWaiting())
        print("Hall Read:%s" % (binascii.hexlify(read_val)))
    
    serial_port.close()
    print('existing...')
    exit()



def SetIRValue(val):
    global mproxity_read

    mproxity_read = val


def ir_read():
    ir = threading.currentThread()
    serial_port = serial.Serial(port='/dev/tty.usbmodem14121', baudrate=115200)
    # serial_port = serial.Serial(port='/dev/tty.usbmodem14241', baudrate=115200)

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
#############################################################################################



def main():

    global total_angle
    global temp_angle
    global base_angle


    ir = threading.Thread(target=ir_read)
    ir.start()


    t = threading.Thread(target=serial_read)
    t.start()

    mMotor.start()


    def handle_close(evt):
        mMotor.close()
        mMotor.join()

        
        t.do_run = False
        t.join()

        ir.do_run = False
        ir.join()




    def press(event):
        #if event.key == 'r':  #reset motor
        mMotor.write_serial(event.key)

    def reset(event):
        base_angle = 0
        temp_angle = 0
        total_angle = 0

    fig, (p1, p2) = plt.subplots(2, 1, dpi = 80)

    fig.canvas.mpl_connect('close_event', handle_close)
    fig.canvas.mpl_connect('key_press_event', press)

    # axwall = plt.axes([0.4, 0.01, 0.05, 0.05])
    # axtuk = plt.axes([0.35, 0.01, 0.05, 0.05])
    
    
    # axknob = plt.axes([0.2, 0.01, 0.05, 0.05])
    # axtune_up = plt.axes([0.1, 0.01, 0.05, 0.05])
    # axtune_down = plt.axes([0.15, 0.01, 0.05, 0.05])
    axnoforce = plt.axes([0.2 - 0.1, 0.01, 0.1, 0.05])
    axforce = plt.axes([0.3- 0.1, 0.01, 0.1, 0.05])
    axstop = plt.axes([0.4- 0.1, 0.01, 0.1, 0.05])
    axspring = plt.axes([0.5- 0.1, 0.01, 0.1, 0.05])
    axantispring = plt.axes([0.6- 0.1, 0.01, 0.15, 0.05])
    axtick_bump = plt.axes([0.75- 0.1, 0.01, 0.12, 0.05])
    # axtick_fast = plt.axes([0.87- 0.1, 0.01, 0.12, 0.05])

    def click_noforce(event):
        global base_angle
        global temp_angle
        global total_angle
        base_angle = 0
        temp_angle = 0
        total_angle = 0
        mMotor.noforce(event)

        print("noforce clicked")  

    def click_force(event):
        global base_angle
        global temp_angle
        global total_angle
        base_angle = 0
        temp_angle = 0
        total_angle = 0
        mMotor.force(event)

        print("force clicked")

    def click_stop(event):
        global base_angle
        global temp_angle
        global total_angle
        base_angle = 0
        temp_angle = 0
        total_angle = 0
        mMotor.stop(event)

        print("stop clicked")


    def click_spring(event):
        global base_angle
        global temp_angle
        global total_angle
        base_angle = 0
        temp_angle = 0
        total_angle = 0
        mMotor.spring(event)

        print("spring clicked")  

    def click_antispring(event):
        global base_angle
        global temp_angle
        global total_angle
        base_angle = 0
        temp_angle = 0
        total_angle = 0
        mMotor.antispring(event)

        print("antispring clicked")

    def click_tick_bump(event):
        global base_angle
        global temp_angle
        global total_angle
        base_angle = 0
        temp_angle = 0
        total_angle = 0
        mMotor.tick_bump(event)

        print("tick_bump clicked")




    bnoforce = Button(axnoforce, 'No Force')   # When use on_clicked function, it has to have a para.
    bnoforce.on_clicked(click_noforce)

    bforce = Button(axforce, 'Force')
    bforce.on_clicked(click_force)

    bstop = Button(axstop, 'Stop')
    bstop.on_clicked(click_stop)

    bspring = Button(axspring, 'Spring')
    #bspring.on_clicked(mMotor.spring)
    bspring.on_clicked(click_spring)

    bantispring = Button(axantispring, 'Anti-Spring')
    bantispring.on_clicked(click_antispring)

    btick_bump = Button(axtick_bump, 'Tick_bump')
    btick_bump.on_clicked(click_tick_bump)

    # btick_fast = Button(axtick_fast, 'Tick_fast')
    # btick_fast.on_clicked(mMotor.tick_fast)

    # bwall = Button(axwall, 'Wall')
    # bwall.on_clicked(mMotor.wall)

    # btuk = Button(axtuk, 'Tuk')
    # btuk.on_clicked(mMotor.tuk)

    
 
    # bknob = Button(axknob, 'Knob')
    # bknob.on_clicked(mMotor.knob)

    # btune_up = Button(axtune_up, '+1')
    # btune_up.on_clicked(mMotor.tune_up)
    # btune_down = Button(axtune_down, '-1')
    # btune_down.on_clicked(mMotor.tune_down)


    range_max = 1100
    range_min = -10

    plot_data, = p1.plot(ch0_buf, animated=True)
    plot_data_ch1, = p1.plot(ch1_buf, color="green", animated=True)
    
    wedge = mpatches.Wedge((0.5, 0.5), 0.2, 0, 0)
    p2.add_patch(wedge)
    #p2.axis('equal')
    #p2.axis("off")
    txt_angle = p2.text(0.7, 0.9, '', transform=p2.transAxes, animated=True)
    
    plot_peak, = p1.plot(peak_x, peak_y, 'ro')
    plot_valley, = p1.plot(valley_x, valley_y, 'ro')
    plot_stop, = p1.plot(stop_x, stop_y, 'o', color='yellow')


    p1.set_ylim(range_min, range_max)
    #p2.set_ylim(range_min, range_max)
    
    def animate(i):
        plot_data.set_ydata(ch0_buf)
        plot_data.set_xdata(range(len(ch0_buf)))
        
        plot_data_ch1.set_ydata(ch1_buf)
        plot_data_ch1.set_xdata(range(len(ch1_buf)))
        #wedge.theta1 += 0.1
        #wedge._recompute_path()
        wedge.theta2 = total_angle
        wedge._recompute_path()

        txt_angle.set_text('angle = %1.2f' % (total_angle))

        plot_peak.set_ydata(peak_y)
        plot_peak.set_xdata(peak_x)

        plot_valley.set_ydata(valley_y)
        plot_valley.set_xdata(valley_x)

        plot_stop.set_ydata(stop_y)
        plot_stop.set_xdata(stop_x)

        return [plot_data, plot_data_ch1, wedge, txt_angle, plot_peak, plot_valley, plot_stop]
    
    ani = animation.FuncAnimation(fig, animate, range(axis_span), 
                                  interval=20, blit=True)  #20 delay, frames refresh 50 times per sec
    plt.show()

if __name__ == "__main__":
    main()
