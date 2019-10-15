#!/usr/bin/env python3

import logging
import threading
import sys
import os
from cv2 import cv2 as cv
from queue import Queue
from typing import Union

import numpy as np

from driver import DriverClass

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

video_file = 'data/videos/IMG_6782.mp4'
#video_file = 'data/videos/incar_rgb_201908016-2.mp4'

source_type = os.environ['INPUT_SRC'] if 'INPUT_SRC' in os.environ else 'video'
avail_source_type = ['video', 'camera']
name = ""

def detect_image(model_class: str, frame_q: Queue):
    while True:
        frame = frame_q.get()
        if frame is None: break
        model_class.detect_image(frame)

def capture_frames(source: Union[str, int], frame_q: Queue, model_class):
    try:
        cap = cv.VideoCapture(source)
        while cap.isOpened():
            # Capture frame-by-frame
            retval, frame = cap.read()
            if retval:
                frame_q.put(cv.flip(frame, 1))
            img = model_class.get_img()
            cv.imshow('output', img)
            cv.waitKey(1)
    finally:
        cap.release()

if __name__ == '__main__':
    frame_q = Queue(1)
    
    if source_type not in avail_source_type:
        logging.error(f'Source type {source_type} not supported')

    # list all users
    path = './data/photos'
    names = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    print('=' * 15, 'Driver List', '=' * 15)
    for n in names:
        if n.split('.')[-1] == 'jpg':
            print(n.split('.')[0])
    print('=' * 43, end='\n\n')

    # Init Model class
    name = input("Enter Driver's ID: ")
    model_class = DriverClass(name)

    logging.info(f'Start to detect object with model DriverClass')
    threading.Thread(target=detect_image, args=(model_class, frame_q), daemon=True).start()
    
    logging.info(f'Start to load from source input {source_type}')
    logging.info(f'Use source type {source_type}')
    
    if source_type == 'video':
        capture_frames(video_file, frame_q, model_class)
    elif source_type == 'camera':
        capture_frames(0, frame_q, model_class)
