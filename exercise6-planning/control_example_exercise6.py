# -*- coding: utf-8 -*-
import sys
import math
import time
import signal

import numpy as np

from cyber_py3 import cyber

from modules.control.proto.chassis_pb2 import Chassis
from modules.planning.proto.planning_pb2 import Point
from modules.control.proto.control_pb2 import Control_Command
from modules.control.proto.control_pb2 import Control_Reference
from modules.planning.proto.planning_pb2 import Trajectory


sys.path.append("../")


class Control(object):

    def __init__(self, node):
        self.node = node
        self.speed = 0
        self.target_speed = 0
        self.lateral_error = 0
        self.cmd = Control_Command()
        self.cmd.steer_angle = 0
        self.cmd.throttle = 0
        self.trajectory = Trajectory()
        self.node.create_reader("/chassis", Chassis, self.chassiscallback)
        self.node.create_reader("/control/reference",
                                Control_Reference, self.speedrefcallback)
        self.node.create_reader("/planning/dwa_trajectory",
                                Trajectory, self.trajectorycallback)
        self.writer = self.node.create_writer("/control", Control_Command)

        self.sum_error_longi = 0
        signal.signal(signal.SIGINT, self.sigint_handler)
        signal.signal(signal.SIGHUP, self.sigint_handler)
        signal.signal(signal.SIGTERM, self.sigint_handler)
        self.is_sigint_up = False
        while True:
            # try:
            time.sleep(0.05)
            self.lateral_controller(self.trajectory, self.lateral_error)
            self.longitude_controller(self.target_speed, self.speed)
            self.writer.write(self.cmd)
            if self.is_sigint_up:
                print("Exit")
                self.is_sigint_up = False
                return
            # except Exception:

         #   break

    def chassiscallback(self, data):
        self.speed = data.speed

    def sigint_handler(self, signum, frame):
            #global is_sigint_up
        self.is_sigint_up = True
        print("catched interrupt signal!")

    def speedrefcallback(self, data):
        self.target_speed = data.vehicle_speed
        print ("ref speed is : ")
        print(self.target_speed)

    def trajectorycallback(self, data):
        self.trajectory = data
        number = len(self.trajectory.point)
        if (number > 0):
            if (self.trajectory.point[0].x >= 0):
                flag = 1
            else:
                flag = -1
            self.lateral_error = math.sqrt(self.trajectory.point[0].x * self.trajectory.point[0].x +
                                           self.trajectory.point[0].y * self.trajectory.point[0].y) * flag

    def lateral_controller(self, trajectory, lateral_error):
        # TODO  you should calculate steerangle here
        if (len(trajectory.point)):
            preview_x = -1*trajectory.point[int(len(trajectory.point) / 2)].x
            preview_y = -1 * trajectory.point[int(len(trajectory.point) / 2)].y
            print(preview_x, preview_y)
            self.cmd.steer_angle = 57 * math.atan2(2 * preview_y * 0.313,
                                                    (preview_x * preview_x + preview_y * preview_y))
            if (abs(self.cmd.steer_angle) < 0.1):
                self.cmd.steer_angle = 0
            if self.cmd.steer_angle > 60:
                self.cmd.steer_angle = 60
            if self.cmd.steer_angle < -60:
                self.cmd.steer_angle = -60
        else:
            self.cmd.steer_angle = 0

        print(self.cmd.steer_angle)
        pass

    def longitude_controller(self, target_speed, speed_now):
        # + 6 + 8.0 * (target_speed - speed_now) + 5.0 * self.sum_error_longi
        self.sum_error_longi += 0.05 * (target_speed - speed_now)
        self.cmd.throttle = target_speed * 30 + (target_speed - speed_now) * 8 + 0.5 * self.sum_error_longi
        pass


if __name__ == '__main__':
    cyber.init()

    # TODO update node to your name
    exercise_node = cyber.Node("control_node")
    exercise = Control(exercise_node)
