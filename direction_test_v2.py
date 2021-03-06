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

from matplotlib.widgets import Button

axis_span = 2000

#initilize the channle buffers
ch0_buf = deque(0 for _ in range(axis_span))
ch1_buf = deque(0 for _ in range(axis_span))
avg = 0


#communication with arduino
def write_serial(serial_port, val_string):
    serial_port.write(val_string)


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

hard_peak = 530
hard_valley = 450



temp_peak = hard_peak
temp_valley = hard_valley

a_sensor_state = -1 #0-state, 1-state, 2-state, 3-state
state_cut_ratio = 0.05
state_cut_up = 0
state_cut_down = 0
b_sensor_dir = 1 #1-increase 2-decrease

#running and notrunning
running = False
prev_val = [] #5 frames
prev_mid = 0
close_to_top = 0
diff_prev_val = []
r_count = 0
running_threshold = 15.0 #very sensitive
#moving direction
running_clockwise = 1  #1->yes  -1->no 
direction_test_timer = 0
reading_direction = 1

predict_span = 200

running_mode = 2 # 1 -> reset  2-> no reset

mproxity_read = 0


def detectRunning(val_list):
    return np.std(val_list)


itr_dif = 0
mup = 0
mdown = 0
mflat = 0

#this is bad
def detectMovingDirection(val_list):
    global itr_dif
    global mup
    global mdown
    global mflat

    length = len(val_list)
    if length > 2:

        """
        mup = 0
        mdown = 0
        mflat = 0
        
        for itrv in range(length-1):
            itr_dif = val_list[itrv+1] - val_list[itrv] 
            if itr_dif > 1:
                mup+=1
            elif itr_dif < -1:
                mdown +=1
            else:
                mflat += 1

        print("up %s, down %s, flat %s" %(mup, mdown, mflat))

        if mflat < 20:  
            if mup > mdown:
                return 1
            else:
                return -1
        else:
            #dangeours
            #should look at the other one
            print("too many flat")
            return 0

        """

        itr_dif  = val_list[-1] - val_list[0] 

        if itr_dif > 3:
            return 1
        elif itr_dif  < -3:
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

motion_count = 0
motion_stop_time = 0
motion_stop_wait = 1 #at least 1 sec


dir_span = 25

dir_using_channel = 0

dir_buff = deque(0 for _ in range(axis_span))

avg_val_0 = 0
prev_avg_val_0 = 0
smooth_dt = (1.0 / 800)
smooth_RC = 0.05
smooth_alpha = smooth_dt / (smooth_RC + smooth_dt)




def AddValue(serial_port, val):

    global hard_valley
    global hard_peak
    global avg_val_0
    global prev_avg_val_0

    
    #avg_val_0 = avg_val_0 + 0.1*(val-avg_val_0)
    avg_val_0 = (smooth_alpha * val) + (1.0 - smooth_alpha) * prev_avg_val_0

    prev_avg_val_0 = avg_val_0

    val = avg_val_0  #do the absolute peak and valley

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
    global prev_mid
    global close_to_top
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

    global motion_count
    global motion_stop_time

    global dir_using_channel
    

    ch0_buf.append(val)
    ch0_buf.popleft()

    dir_buff.append(0)
    dir_buff.popleft()

    peak_list.append(val)

    if len(peak_list) > 1000:
        peak_list.pop(0)

    #for motion state detection
    prev_val.append(avg_val_0)

    if len(prev_val) > predict_span: #200

        prev_val.pop(0)

        std_value = detectRunning(prev_val)

        #print(std_value)
        
        if std_value > running_threshold :  # predict as running, a sensor or b sensor, either one works
            #print("running")
            if running == False and time.time() - motion_stop_time > motion_stop_wait:
                running = True

                #screenshot
                dir_xxxx = -dir_span
                dir_yyyy = 0
                for trippp in prev_val[-dir_span:]:
                	dir_buff[-dir_span + dir_yyyy] = trippp
                	dir_yyyy += 1

                direction_test_timer = 0
                motion_count += 1
                print("start %s" % motion_count)

                #read the direction
                if reading_direction == 1:
                    if a_sensor_state == -1:
                        running_clockwise = 1


                    elif a_sensor_state == 1:

                        #see sensor 1
                        dir_ch0 = detectMovingDirection(prev_val[-dir_span:])
                        dir_ch1 = detectMovingDirection(prev_val_ch1[-dir_span:])


                        #prev_mid = (prev_val[-dir_span]  + prev_val[-1])/2 

                        if prev_mid < state_cut_down:
                            dir_using_channel = 1
                            close_to_top = -1
                        elif prev_mid > state_cut_up:
                            dir_using_channel = 1
                            close_to_top = 1
                        else:
                            dir_using_channel = 0

                        #print("state: %s, ch0 dir: %s"%(a_sensor_state, dir_ch0))
                        #print(prev_val[-dir_span:])
                        #print(prev_val)if 

                        if dir_using_channel == 0:

                            if dir_ch0 == 1:
                                running_clockwise = -1
                            elif dir_ch0 == -1:
                                running_clockwise = 1

                            print("state: %s, ch0 dir: %s"%(a_sensor_state, dir_ch0))

                        else:

                            #pay special attention
                            if close_to_top == 1:
                                if dir_ch1 == 1:
                                    running_clockwise = 1
                                elif dir_ch1 == -1:
                                    running_clockwise = -1
                            elif close_to_top == -1:
                                if dir_ch1 == 1:
                                    running_clockwise = -1
                                elif dir_ch1 == -1:
                                    running_clockwise = 1

                            print("state: %s, ch1 dir: %s"%(a_sensor_state, dir_ch1))
                        


                    elif a_sensor_state == 2:
                        #see sensor 2
                        dir_ch0 = detectMovingDirection(prev_val[-dir_span:])
                        dir_ch1 = detectMovingDirection(prev_val_ch1[-dir_span:])

                        #prev_mid = (prev_val[-dir_span]  + prev_val[-1])/2 

                        if prev_mid < state_cut_down:
                            dir_using_channel = 1
                            close_to_top = -1
                        elif prev_mid > state_cut_up:
                            dir_using_channel = 1
                            close_to_top = 1
                        else:
                            dir_using_channel = 0
                        
                        #print("state: %s, ch1 dir: %s"%(a_sensor_state, dir_ch1))
                        #print(prev_val_ch1[-dir_span:])
                        #print(prev_val_ch1)

                        if dir_using_channel == 0:
                            if dir_ch0 == 1:
                                running_clockwise = 1
                                    #a_sensor_state = 3
                            elif dir_ch0 == -1:
                                running_clockwise = -1
                                    #a_sensor_state = 1

                            print("state: %s, ch0 dir: %s"%(a_sensor_state, dir_ch0))
                        else:  
                            #pay special attention here
                            if close_to_top == 1:
                                if dir_ch1 == 1:
                                    running_clockwise = 1
                                        #a_sensor_state = 3
                                elif dir_ch1 == -1:
                                    running_clockwise = -1
                                        #a_sensor_state = 1
                            elif close_to_top == -1:
                                if dir_ch1 == 1:
                                    running_clockwise = -1
                                        #a_sensor_state = 3
                                elif dir_ch1 == -1:
                                    running_clockwise = 1
                                        #a_sensor_state = 1

                            print("state: %s, ch1 dir: %s"%(a_sensor_state, dir_ch1))

                    #running_clockwise = 1
                    print("dir %s" % running_clockwise)

                    reading_direction = 0
                        
            

        else:
            #r_count = r_count + 1
            #print(r_count)  #predict as not running
            #if running_ch1 == False:
            if running == True:

                print("stop")
                print("")
                motion_stop_time = time.time()

                running = False
                reading_direction = 1 #waiting for diretion info

                #record stop points
                stop_x.append(axis_span)
                stop_y.append(val)

                #if val > hard_valley and val < hard_peak:
                #    dir_using_channel = 0
                #else:
                #    dir_using_channel = 1

                #plt.savefig('%s.png'%(time.time()))

                prev_mid = val

                #os.system('screencapture %s.png'%(time.time()))


            else:

                #regular check
                if std_value < 0.1:
                    #print("check valid")
                    prev_mid = val
                
    #running or not
    #print(running)
    #print("             %s"%(val))


    if topanddown == 1:

        #use another method
        filter_peaks = detect_peaks(peak_list, mph=hard_peak, mpd=20, threshold=0, edge='falling',
                 kpsh=False, valley=False, show=False, ax=None)

        if len(filter_peaks)>0:
            peak_x.append(axis_span)
            peak_y.append(peak_list[filter_peaks[-1]])
            temp_peak = peak_list[filter_peaks[-1]]
            
            del peak_list[:]
            topanddown = -1

            #angle cal
            if firstTopOrBottom:

                #print("first top")
                base_angle = 0
                temp_angle = 0
                firstTopOrBottom = False
                reachingPeak = True
                a_sensor_state = 1
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

            goingup = False

            #if reading_direction == 0:
            if running_clockwise == 1:
                a_sensor_state = 1
            else:
                a_sensor_state = 2

            #print("sensor_state: %s" % a_sensor_state)


    elif topanddown == -1:
        filter_valleys = detect_peaks(peak_list, mph=-hard_valley-1, mpd=20, threshold=0, edge='falling',
                 kpsh=False, valley=True, show=False, ax=None)
        if len(filter_valleys)>0:

            valley_x.append(axis_span)
            valley_y.append(peak_list[filter_valleys[-1]])
            temp_valley = peak_list[filter_valleys[-1]]
            
            del peak_list[:]
            topanddown = 1

            if firstTopOrBottom:
                base_angle = 0
                temp_angle = 0
                firstTopOrBottom = False
                reachingPeak = True
                a_sensor_state = 2
                #initial closewise, see sensor 2

            else:
                base_angle += (20*running_clockwise)
                temp_angle = 0
                reachingPeak = True
                state_cut_down = temp_valley + (temp_peak - temp_valley) * state_cut_ratio

            goingup = True

            #if reading_direction == 0:
            if running_clockwise == 1:
                a_sensor_state = 2
            else:
                a_sensor_state = 1

            #print("sensor_state: %s" % a_sensor_state)



    
    
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

        pre_total_angle = total_angle 

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


    if len(peak_x)>0:
        for itrx in range(len(peak_x)):
            peak_x[itrx] = peak_x[itrx] - 1

    if len(valley_x) > 0:
        for itrx in range(len(valley_x)):
            valley_x[itrx] = valley_x[itrx] - 1

    if len(stop_x) > 0:
        for itrx in range(len(stop_x)):
           	stop_x[itrx] = stop_x[itrx] - 1



#variables for b sensor
prev_val_ch1 = []
running_ch1 = False
avg_val_1 = 0
prev_avg_val_1 = 0

std_value_ch1 = 0

def AddValue_Ch1(val):

    #print("       %s"%(val))
    global prev_val_ch1
    global running_ch1
    global predict_span
    global running_threshold
    global avg_val_1
    global prev_avg_val_1

    global std_value_ch1
    
    #avg_val_1 = avg_val_1 + 0.1 * (val - avg_val_1)
    avg_val_1 = (smooth_alpha * val) + (1.0 - smooth_alpha) * prev_avg_val_1


    prev_avg_val_1 = avg_val_1

    ch1_buf.append(avg_val_1)
    ch1_buf.popleft()

    prev_val_ch1.append(avg_val_1)
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

    serial_port = serial.Serial(port='/dev/tty.usbmodem14141', baudrate=115200)
    
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

#############################################################################################



def main():

    global total_angle
    global temp_angle
    global base_angle

    t = threading.Thread(target=serial_read)
    t.start()

    def handle_close(evt):        
        t.do_run = False
        t.join()

        exit()

    fig, (p1, p2) = plt.subplots(2, 1, dpi = 80)
    range_max = 650
    range_min = 300

    fig.canvas.mpl_connect('close_event', handle_close)


    plot_data, = p1.plot(ch0_buf, animated=True)
    plot_data_ch1, = p1.plot(ch1_buf, color="green", animated=True)

    plot_dir, = p1.plot(dir_buff, color="red", animated=True)
    
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

        plot_dir.set_ydata(dir_buff)
        plot_dir.set_xdata(range(len(dir_buff)))

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

        return [plot_data, plot_data_ch1, plot_dir, wedge, txt_angle, plot_peak, plot_valley, plot_stop]
    
    ani = animation.FuncAnimation(fig, animate, range(axis_span), 
                                  interval=20, blit=True)  #20 delay, frames refresh 50 times per sec
    plt.show()

if __name__ == "__main__":
    main()
