# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.

import numpy as np
import threading
import requests
from cv2 import cv2 as cv
import time
import datetime
import json
import utility
import os
import logging

from queue import Queue

from driver_age_gender import AgeGenderClass
from driver_behavior import BehaviorClass
from driver_emotion import EmotionClass
from driver_face_detection import FaceDetectionClass
from driver_identification import IdentificationClass

class DriverClass():
    def __init__(self, name):
        self.max_frame_count = int(os.getenv('MAX_FRAME_COUNT', 0))  # default = 0: no frame skipped
        self.frame_count = self.max_frame_count
        self.info = []

        self.image_w = 640
        self.image_h = 360
        self.crop_l = 160   # left
        self.crop_r = 160   # right
        self.crop_t = 180   # top
        self.crop_b = 0     # buttom

        self.driver_pos_x = int((720 - self.crop_l) * 4 / 3)
        self.driver_pos_y = int((250 - self.crop_t) * 4 / 3)
        
        self.padding_ratio = 0.15

        self.obj_age_gender = AgeGenderClass()
        self.obj_behavior = BehaviorClass()
        self.obj_emotion = EmotionClass()
        self.obj_face = FaceDetectionClass()
        self.obj_identification = IdentificationClass()

        self.t_start = None
        self.t_end = None

        self.output_img = np.zeros((360, 640, 3))
        self.color_list = {'safe': (0, 255, 0), 'warning': (0, 112, 255), 'danger': (0, 0, 255)}

        self.vote_num = 15
        self.drowsiness_vote = Queue(self.vote_num)
        self.drowsiness_sum = 0
        self.yawn_vote = Queue(self.vote_num)
        self.yawn_sum = 0
        for i in range(0, self.vote_num):
            self.drowsiness_vote.put(False)
            self.yawn_vote.put(False)
        self.driving = False
        self.driver_name = name
        self.driver_vote = 0

        if utility.is_recording:
            utility.start_record(self.image_w, self.image_h)
        

    def get_img(self):
        return self.output_img

    def detect_models(self, image):
        

        # get faces in image
        t = time.time()
        driver_face = self.obj_face.get_driver_dlib(image)
        duration_face = time.time() - t
        # logging.info(f'Face Detection Time = {duration_face} sec')

        if driver_face is None:
            # logging.info("!!! No face found !!!")
            self.info = ""
            return

        gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)  # gray image
        img = image.copy()

        # for rect in faces:
        x1, x2, y1, y2 = driver_face.left(), driver_face.right(), driver_face.top(), driver_face.bottom()
        padding_w = int((x2 - x1) * self.padding_ratio)
        padding_h = int((y2 - y1) * self.padding_ratio)
        face = img[max(0, y1 - padding_h):min(y2 + padding_h, self.image_h - 1), 
                    max(0, x1 - padding_w):min(x2 + padding_w, self.image_w - 1)]
        face_gray = gray[max(0, y1 - padding_h):min(y2 + padding_h, self.image_h - 1), 
                            max(0, x1 - padding_w):min(x2 + padding_w, self.image_w - 1)]  

        # Get age
        t = time.time()
        age = 'teenager'#self.obj_age_gender.get_age(face)
        duration_age = time.time() - t
        #print('Age and Gender Detection Time = {:8.6f} sec' .format(duration_age))

        # Get gender
        t = time.time()
        gender = 'male'#self.obj_age_gender.get_gender(face)
        duration_gender = time.time() - t
        #print('Age and Gender Detection Time = {:8.6f} sec' .format(duration_gender))

        # Get name
        t = time.time()
        name = self.obj_identification.get_name(face)
        duration_name = time.time() - t
        #print('Driver Identification Time = {:8.6f} sec' .format(duration_name))
            
        # Get emotion
        t = time.time()
        emotion, confidence, color = self.obj_emotion.get_emotion(face_gray)
        duration_emotion = time.time() - t
        #print('Emotion Detection Time = {:8.6f} sec' .format(duration_emotion))

        # Check drowsiness and yawn
        t = time.time()
        drowsiness, yawn, gaze, head_pose = self.obj_behavior.check_drowsiness_yawn(img, driver_face)
        duration_yawn = time.time() - t
        #print('Drowsiness and Yawn Detection Time = {:8.6f} sec' .format(duration_yawn))


        self.info = [age, gender, name, emotion, drowsiness, yawn, gaze, confidence, color, 
                    x1, y1, x2, y2, 
                    duration_face, duration_age, duration_gender, 
                    duration_emotion, duration_name, duration_yawn, head_pose]

    def detect_image(self, image: np.ndarray):
        # Crop image
        image = cv.resize(image, (640, 360))
        self.image_h, self.image_w = image.shape[:2]

        if self.frame_count >= self.max_frame_count:
            self.detect_models(image)
            self.frame_count = 0
        else:
            self.frame_count += 1


        if not self.info:
            self.output_img = utility.output_result(image, 0)
            cv.putText(image, "Driver Missing", (200, 30), cv.FONT_HERSHEY_DUPLEX, 
                    1, (0,255,255), 1, cv.LINE_AA)
            return 

        age, gender, name, emotion, drowsiness, yawn, gaze, confidence, color, \
        x1, y1, x2, y2, duration_face, duration_age, duration_gender, \
        duration_emotion, duration_name, duration_yawn, head_pose = self.info
        
        duration = duration_face + duration_age + duration_gender + duration_emotion + duration_name + duration_yawn 

        # Display bboxes and information
        label = name + ", " + emotion
        y = y1 - utility.rect_h * 2
        if y < 0:
            if (y1 - utility.rect_h) < 0:                        
                y = y2 + utility.rect_h
            else:
                y = y2
        cv.rectangle(image, (x1, y), (x1 + utility.rect_w, y + utility.rect_h), color, -1)
        cv.putText(image, label, (x1 + 4, y + utility.rect_h - 4), cv.FONT_HERSHEY_SIMPLEX, 
                    utility.textsize_label, (255 - color[0], 255 - color[1], 255 - color[2]), 1, cv.LINE_AA)
        cv.line(image, head_pose[0], head_pose[1], (255,0,0), 2)
            
        message = { "Name": name, "Emotion": emotion, "Gender": gender, "Age": age,
                    "Confidence": "{:6.4f}".format(confidence),
                    "Position": [int(x1), int(y1), int(x2), int(y2)],
                    "TimeStamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    }
        label = gender + ", " + age
        utility.draw_object(image, color, label, confidence, x1, y1, x2, y2, message)

        # Ouput detail items
        utility.output_detail(image, 0, "Face Detection", duration_face)
        utility.output_detail(image, 1, "Age", duration_age)
        utility.output_detail(image, 2, "Gender", duration_gender)
        utility.output_detail(image, 3, "Emotion", duration_emotion)
        utility.output_detail(image, 4, "Driver identification", duration_name)
        utility.output_detail(image, 5, "Driver behavior", duration_yawn)

        # Send alert messages
        if True or (x1 >= self.driver_pos_x) and (y1 >= self.driver_pos_y):  # Only send alert for driver
            if (name == "Unknown"):
                cv.putText(image, "?", (int((x1 + x2) / 2) - 40, y1), cv.FONT_HERSHEY_DUPLEX, utility.textsize_label * 3, (128, 0, 128), 1, cv.LINE_AA)

            alert = None
            if drowsiness:
                alert = "DROWSINESS"

            if yawn:
                if alert is None:
                    alert = "YAWN"
                else:
                    alert = alert + " + YAWN"

            if alert is not None:
                print('alert:', alert)
                cv.putText(image, "!!! " + alert + " !!!", (x1 + 10, int(y1 + utility.rect_h * 1.3)), 
                            cv.FONT_HERSHEY_DUPLEX, utility.textsize_label * 1.2, (0, 0, 255), 1, cv.LINE_AA)
            
            # show driver status
            self.drowsiness_sum += drowsiness
            self.drowsiness_sum -= self.drowsiness_vote.get()
            self.drowsiness_vote.put(drowsiness)
            self.yawn_sum += yawn
            self.yawn_sum -= self.yawn_vote.get()
            self.yawn_vote.put(yawn)
            # print('vote:', self.yawn_sum+self.drowsiness_sum*2)
            if int(self.yawn_sum*1.1)+self.drowsiness_sum*2 > self.vote_num:
                sleepy_status = 'danger'
                print("Danger!!!\a")
            elif int(self.yawn_sum*1.1)+self.drowsiness_sum*2 > self.vote_num//2:
                sleepy_status = 'warning'
            else:
                sleepy_status = 'safe'
            col = self.color_list[sleepy_status]
            cv.putText(image, sleepy_status, (500, 30), cv.FONT_HERSHEY_DUPLEX, 
                        1, col, 1, cv.LINE_AA)

        # show driving status // this is garbage
        if 'name' in locals():
            if name == self.driver_name and self.driver_vote < 20:
                self.driver_vote += 1
            elif self.driver_vote > 0:
                self.driver_vote -= 1

            if not self.driving:
                driving_status = "Vehicle Locked"
                col = (255,255,0)
                if self.driver_vote >= 15:
                    self.driving = True
                    logging.info(f'Welcome back {self.driver_name}')
            else:
                driving_status = "Driving Normally"
                col = (255,0,0)
                if self.driver_vote < 5:
                    driving_status = "Wrong Driver! Speed Limit: 20\a"
                    print("Wrong Driver!!!\a")
                    col = (0,0,255)
        if not driving_status == 'Wrong Driver! Speed Limit: 20':
            cv.putText(image, driving_status, (200, 60), cv.FONT_HERSHEY_DUPLEX, 
                        1, col, 1, cv.LINE_AA)
        else:
            cv.putText(image, driving_status, (80, 60), cv.FONT_HERSHEY_DUPLEX, 
                        1, col, 1, cv.LINE_AA)
                    
        # Ouput detection result
        #image = cv.resize(image, (self.image_w, self.image_h))   # restore to the original image size to display
        
        self.output_img = utility.output_result(image, duration)