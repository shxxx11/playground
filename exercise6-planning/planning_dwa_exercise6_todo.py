#coding: utf-8

import sys
import os
import math
import signal
import time
import numpy as np
from cyber_py3 import cyber
from modules.planning.proto.planning_pb2 import PlanningInfo
from modules.planning.proto.planning_pb2 import Trajectory
from modules.planning.proto.planning_pb2 import Point
from modules.perception.proto.perception_obstacle_pb2 import PerceptionObstacles
from modules.perception.proto.perception_obstacle_pb2 import PerceptionObstacle
from modules.perception.proto.perception_obstacle_pb2 import BBox2D

from modules.localization.proto.localization_pb2 import localization
from modules.localization.proto.localization_pb2 import pos

from modules.control.proto.control_pb2 import Control_Reference

b_box = BBox2D()
point_xy = Point()
yawrate_old = 0
scale = 144.9


class Config(object):
    """
    用来仿真的参数，
    """
    def __init__(self):
        # car parameter
        self.max_speed = 0.8  # [m/s]  # 最大速度
        self.min_speed = 0  # [m/s]  # 最小速度，设置为不倒车
        self.max_yawrate = 90.0 * math.pi / 180.0  # [rad/s]  # 最大角速度s
        self.max_accel = 0.8  # [m/ss]  # 最大加速度
        self.max_dyawrate = 600.0 * math.pi / 180.0  # [rad/ss]  # 最大角加速度
        self.v_reso = 0.25  # [m/s]，速度分辨率
        self.yawrate_reso = 1.2 * math.pi / 180.0  # [rad/s]，角速度分辨率
        self.dt = 0.1  # [s]  # 采样周期
        self.predict_time = 3  # [s]  # 向前预估三秒
        self.to_goal_cost_gain = 6  # 目标代价增益
        self.speed_cost_gain = 10  # 速度代价增益
        self.obstacle_cost_gain = 20  # 障碍物代价增益
        self.yawrate_cost_gain = 10  # 角速度代价增益


def motion(x, u, dt):
    """
    :param x: 位置参数，在此叫做位置空间
    :param u: 速度和加速度，在此叫做速度空间
    :param dt: 采样时间
    :return:
    """
    x[0] += u[0] * math.cos(x[2]) * dt  # x方向位移
    x[1] += u[0] * math.sin(x[2]) * dt  # y
    x[2] += u[1] * dt  # 航向角
    x[3] = u[0]  # 速度v
    x[4] = u[1]  # 角速度w

    return x


def calc_dynamic_window(x, config):
    """
    位置空间集合
    :param x:当前位置空间
    :param config:
    :return:目前是两个速度的交集
    """

    # 车辆能够达到的最大最小速度
    vs = [
        config.min_speed, config.max_speed, -config.max_yawrate,
        config.max_yawrate
    ]

    # 一个采样周期能够变化的最大最小速度
    vd = [
        x[3] - config.max_accel * config.dt,
        x[3] + config.max_accel * config.dt,
        x[4] - config.max_dyawrate * config.dt,
        x[4] + config.max_dyawrate * config.dt
    ]

    # 求出两个速度集合的交集
    vr = [
        max(vs[0], vd[0]),
        min(vs[1], vd[1]),
        max(vs[2], vd[2]),
        min(vs[3], vd[3])
    ]

    return vr


def calc_trajectory(x_init, v, w, config):
    """
    预测3秒内的轨迹
    :param x_init:位置空间
    :param v:速度
    :param w:角速度
    :param config:
    :return: 每一次采样更新的轨迹，位置空间垂直堆叠
    """
    x = np.array(x_init)
    trajectory = np.array(x)
    time = 0
    while time <= config.predict_time:
        x = motion(x, [v, w], config.dt)
        trajectory = np.vstack((trajectory, x))  # 垂直堆叠，vertical
        time += config.dt

    return trajectory


def calc_to_goal_cost(trajectory, goal, config):
    """
    计算轨迹到目标点的代价
    :param trajectory:轨迹搜索空间
    :param goal:
    :param config:
    :return: 轨迹到目标点欧式距离
    """
    # calc to goal cost. It is 2D norm.

    ##TODO

    dx = goal[0] - trajectory[-1, 0]
    dy = goal[1] - trajectory[-1, 1]
    goal_dis = math.sqrt(dx**2 + dy**2)
    cost = config.to_goal_cost_gain * goal_dis

    return cost
    ##TODO


def calc_obstacle_cost(traj, ob, config):
    """
    计算预测轨迹和障碍物的最小距离，dist(v,w)
    :param traj:
    :param ob:
    :param config:
    :return:
    """
    # calc obstacle cost inf: collision, 0:free

    ##TODO

    if len(ob) < 1:
        return 0

    skip_n = 2  # 省时

    minr = float("inf")  # 距离初始化为无穷大

    for ii in range(0, len(traj[:, 1]), skip_n):
        for i in range(len(ob[:, 0])):
            ox = ob[i, 0]
            oy = ob[i, 1]
            obr = ob[i, 2]

            dx = traj[ii, 0] - ox
            dy = traj[ii, 1] - oy

            r = math.sqrt(dx**2 + dy**2)
            if r <= obr:
                return float("Inf")  # collision

            if minr >= r:
                minr = r

    return 1.0 / minr  # 越小越好

    ##TODO


def calc_speed_cost(traj, config):
    """
    计算预测速度与最大速度差距
    :param traj:
    :param config:
    :return:
    """
    ##TODO

    speed_cost = config.max_speed - traj[-1, 3]

    return speed_cost

    ##TODO


def calc_final_input(x, u, vr, config, goal, ob):
    """
    计算采样空间的评价函数，选择最合适的那一个作为最终输入
    :param x:位置空间
    :param u:速度空间
    :param vr:速度空间交集
    :param config:
    :param goal:目标位置
    :param ob:障碍物
    :return:
    """
    global yawrate_old

    x_init = x[:]
    min_cost = 10000.0
    min_u = u

    best_trajectory = np.array([x])

    # v,生成一系列速度，w，生成一系列角速度
    for v in np.arange(vr[0], vr[1], config.v_reso):
        for w in np.arange(vr[2], vr[3], config.yawrate_reso):

            trajectory = calc_trajectory(x_init, v, w, config)

            # calc cost
            to_goal_cost = config.to_goal_cost_gain * calc_to_goal_cost(
                trajectory, goal, config)
            speed_cost = config.speed_cost_gain * calc_speed_cost(
                trajectory, config)
            ob_cost = config.obstacle_cost_gain * calc_obstacle_cost(
                trajectory, ob, config)

            #用于稳定规划路径，减少跳动
            yawrate_cost = config.yawrate_cost_gain * abs(w - yawrate_old)

            # 评价函数多种多样，看自己选择
            # 代价越小越好
            final_cost = to_goal_cost + speed_cost + ob_cost + yawrate_cost

            # search minimum trajectory
            if min_cost >= final_cost:
                min_cost = final_cost
                min_u = [v, w]
                best_trajectory = trajectory

    #限制小车的最小速度
    if min_u[0] < 0.5:
        min_u[0] = 0.5

    yawrate_old = min_u[1]

    return min_u, best_trajectory


def dwa_control(x, u, config, goal, ob):
    """
    调用前面的几个函数，生成最合适的速度空间和轨迹搜索空间
    :param x:
    :param u:
    :param config:
    :param goal:
    :param ob:
    :return:
    """

    vr = calc_dynamic_window(x, config)

    u, trajectory = calc_final_input(x, u, vr, config, goal, ob)

    return u, trajectory


class planning(object):
    def __init__(self, node):
        self.node = node
        self.goal_x = 0
        self.goal_y = 0
        self.pathList = []
        self.obstacleList = []
        self.speed = 0
        self.goal = []

        global_str = ''

        self.node.create_reader("/planning/global_trajectory", Trajectory,
                                self.globalcallback)
        self.node.create_reader("/perception/obstacles", PerceptionObstacles,
                                self.obstaclecallback)
        self.node.create_reader("/geek/uwb/localization", pos, self.callback)
        self.writer = self.node.create_writer("/planning/dwa_trajectory",
                                              Trajectory)
        self.vwriter = self.node.create_writer("/control/reference",
                                               Control_Reference)

        signal.signal(signal.SIGINT, self.sigint_handler)
        signal.signal(signal.SIGHUP, self.sigint_handler)
        signal.signal(signal.SIGTERM, self.sigint_handler)
        self.is_sigint_up = False
        while True:
            time.sleep(0.05)
            if self.is_sigint_up:
                print("Exit!")
                self.is_sigint_up = False
                sys.exit()

    def sigint_handler(self, signum, frame):
        self.is_sigint_up = True
        print("catch interrupt signal!")

    def globalcallback(self, global_trajectory):

        pathList = []

        for point in global_trajectory.point:
            pathList.append([point.x, point.y])

        self.pathList = []

        self.pathList = pathList

        print("global trajectory updated.")

    def obstaclecallback(self, data):

        obstacle_info = []

        for obstacle in data.perception_obstacle:

            min_x = obstacle.bbox2d.zmin
            max_x = obstacle.bbox2d.zmax
            min_y = -obstacle.bbox2d.xmin
            max_y = -obstacle.bbox2d.xmax

            #obstacle_r = (((max_x - min_x)/2)**2 + ((max_y - min_y)/2)**2)**0.5
            obstacle_x = (max_x - min_x) / 2 + min_x
            obstacle_y = (max_y - min_y) / 2 + min_y
            obstacle_r = 0.2

            obstacle_info.append([obstacle_x, obstacle_y, obstacle_r])

        self.obstacleList = obstacle_info

        print("obstacles updated.")

    def callback(self, pos):
        global obslist, planning_path, best_trajectory

        start_x = int(pos.x * scale)
        start_y = int(pos.y * scale)

        obslist = []
        num_point = 0
        minr = float("inf")

        for i, point in enumerate(self.pathList):
            r = math.sqrt((point[0] - start_x)**2 + (point[1] - start_y)**2)
            if minr >= r:
                minr = r
                num_point = i

        if (num_point - 8) <= 0:
            num_point = 8

        #规划预瞄点
        f_point = self.pathList[num_point - 8]

        self.goal = f_point

        print("goal:", self.goal)

        #将预瞄点坐标从地图坐标系转换到车身坐标系
        f_point = [(f_point[0] - start_x) / scale,
                   -((f_point[1] - start_y) / scale)]

        yaw = math.pi - pos.yaw

        x_f = f_point[0] * math.cos(yaw) + f_point[1] * math.sin(yaw)
        y_f = f_point[1] * math.cos(yaw) - f_point[0] * math.sin(yaw)

        print("trans-goal:", [x_f, y_f])
        
	#将预设障碍物坐标从地图坐标系转换到车身坐标系
        ob_point = [643, 353]

        ob_point = [(ob_point[0] - start_x) / scale, -((ob_point[1] - start_y) / scale)]
        x_ob = ob_point[0] * math.cos(yaw) + ob_point[1] * math.sin(yaw)
        y_ob = ob_point[1] * math.cos(yaw) - ob_point[0] * math.sin(yaw)

        print("ob:", [x_ob, y_ob])

        print(" planning start!")

        # initial state [x(m), y(m), yaw(rad), v(m/s), omega(rad/s)]
        x = np.array([0.0, 0.0, 0, 0.3, 0.0])
        # goal position [x(m), y(m)]
        goal = np.array([x_f, y_f])

        ob = np.matrix(self.obstacleList)
        ob = np.array([[x_ob, y_ob, 0.24/scale]])

        # input [forward speed, yawrate]
        u = np.array([0.3, 0.0])
        config = Config()

        best_trajectory = np.array(x)

        u, best_trajectory = dwa_control(x, u, config, goal, ob)

        x = motion(x, u, config.dt)

        #接近终点减速
        dist_car_goal = ((((start_x - self.pathList[0][0])**2 +
                   (start_y - self.pathList[0][1])**2)**0.5) / scale)

        if dist_car_goal <= 0.2:
            u[0] = 0

        self.planning_path = Trajectory()
        self.speed = Control_Reference()
        self.speed.vehicle_speed = u[0]

        if not best_trajectory.any():
            print("Failed to find a path")
        else:
            for path_point in best_trajectory:
                point_xy.x = path_point[0]
                point_xy.y = path_point[1]

                self.planning_path.point.append(point_xy)

        point_xy.x = self.goal[0]
        point_xy.y = self.goal[1]

        self.planning_path.point.append(point_xy)

        if not cyber.is_shutdown() and self.planning_path:
            self.writer.write(self.planning_path)
            self.vwriter.write(self.speed)

        print("planning done")


if __name__ == '__main__':
    cyber.init()
    cyber_node = cyber.Node("planning_dwa")
    exercise = planning(cyber_node)

    cyber_node.spin()
    cyber.shutdown()
