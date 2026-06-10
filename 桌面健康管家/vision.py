# -*- coding: utf-8 -*-  # 指定源码编码, 支持中文注释
"""
桌面健康管家 - 视觉模块 (坐姿检测)
====================================
坐姿判断逻辑:
  人脸在画面中的位置反映坐姿:
  - 人脸偏上 (Y占比小) → 抬头挺胸, 坐姿端正
  - 人脸偏下 (Y占比大) → 低头驼背, 坐姿不良
"""

import threading  # 用线程锁保护视觉识别结果, 避免主线程读取时冲突
import time       # 用于摄像头读取失败时延时和停止线程等待
import cv2        # OpenCV库, 用于摄像头读取、人脸检测和画面标注
import numpy as np  # 导入numpy, 保留给OpenCV图像数组处理使用
from config import *  # 导入摄像头参数、人脸检测阈值和坐姿判断阈值


# ==================== 摄像头初始化 ====================

def _init_camera():
    """打开摄像头: camera = cv2.VideoCapture(0) (参照PPT六 page 6)。"""
    cap = cv2.VideoCapture(CAMERA_INDEX)  # 根据配置中的摄像头编号打开USB摄像头
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)  # 设置摄像头画面宽度
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)  # 设置摄像头画面高度
    return cap  # 返回摄像头对象, 后续用它读取图像帧


# ==================== 坐姿视觉系统 ====================

class PostureVision:
    """
    坐姿视觉检测系统。
    该类在独立线程中运行, 持续分析摄像头中的人脸位置。
    """

    def __init__(self):
        # ---- 打开摄像头 ----
        self.cap = _init_camera()  # 初始化并打开摄像头
        if not self.cap.isOpened():  # 判断摄像头是否打开成功
            raise RuntimeError("摄像头打开失败!")  # 打不开摄像头时直接报错

        # ---- 步骤一: 载入人脸分类器 ----
        # face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
        self.face_cascade = cv2.CascadeClassifier(HAAR_PATH)  # 加载Haar人脸分类器模型文件
        if self.face_cascade.empty():  # 判断分类器是否加载成功
            print("[视觉] 警告: Haar分类器加载失败!")  # 加载失败时提示
            self.enabled = False  # 禁用人脸检测, 避免后续detectMultiScale报错
        else:
            print("[视觉] Haar人脸分类器就绪")  # 加载成功时提示
            self.enabled = True  # 启用人脸检测

        # 检测结果 (线程安全)
        self.lock = threading.Lock()  # 创建线程锁, 保护results字典读写
        self.results = {  # 保存最新视觉识别结果, 主线程会读取这个字典
            'face_detected': False,       # 是否检测到人脸
            'face_center_y': 0,           # 人脸中心点Y坐标
            'face_ratio': 0.0,            # 人脸Y位置占比, 0靠上, 1靠下
            'posture': 'none',            # 坐姿状态: good / warn / bad / none
            'display_frame': None,        # debug模式下显示的标注画面
        }
        self.running = False  # 视觉线程运行标志
        self.frame_count = 0  # 已读取的帧数, 用于间隔处理
        self.no_face_frames = 0  # 连续未检测到人脸的帧数

    def run(self):
        """视觉主循环, 由main.py启动为独立线程。"""
        self.running = True  # 标记视觉线程开始运行

        while self.running:  # running为True时持续处理摄像头画面
            # ---- 步骤二: 读取图片 ----
            # ret, img = cap.read()
            ret, frame = self.cap.read()  # 从摄像头读取一帧图像
            if not ret:  # 如果读取失败
                time.sleep(1)  # 等待1秒后重试, 避免疯狂循环
                continue  # 跳过本轮循环

            self.frame_count += 1  # 成功读取一帧后计数加1

            # 按间隔处理, 降低CPU负载
            skip = max(1, int(FRAME_INTERVAL * 30))  # 根据处理间隔估算跳帧数量
            if self.frame_count % skip != 0:  # 如果当前帧不是需要处理的帧
                continue  # 跳过识别, 降低树莓派CPU压力

            display = frame.copy()  # 复制一份画面, 用于画框和显示, 不破坏原始帧

            if self.enabled:  # 只有人脸分类器加载成功时才做人脸检测
                # ---- 步骤三: 灰度转换 ----
                # gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)  # 将彩色图像转为灰度图, 供Haar检测使用

                # ---- 步骤四: 识别人脸 ----
                # faces = face_cascade.detectMultiScale(gray, 1.3, 5)
                faces = self.face_cascade.detectMultiScale(
                    gray,                         # 输入灰度图像
                    scaleFactor=SCALE_FACTOR,     # 图像金字塔缩放比例
                    minNeighbors=MIN_NEIGHBORS,   # 候选框邻居数量, 越大误检越少
                    minSize=MIN_FACE_SIZE,        # 最小人脸尺寸, 过滤太小的误检
                    flags=cv2.CASCADE_SCALE_IMAGE # Haar检测标志
                )

                # ---- 步骤五: 画框 + 坐姿分析 ----
                if len(faces) > 0:  # 如果检测到至少一张人脸
                    # 取最大人脸 (最近的人)
                    (x, y, w, h) = max(faces, key=lambda r: r[2] * r[3])  # 面积最大的框认为是主要用户

                    # 画蓝色框标注人脸
                    # cv2.rectangle(img, (x,y), (x+w,y+h), (255,0,0), 2)
                    cv2.rectangle(display, (x, y), (x + w, y + h),
                                  (255, 0, 0), 2)  # 在显示画面中画出人脸框

                    # 计算人脸中心Y占比
                    face_center_y = y + h // 2  # 计算人脸框中心点的Y坐标
                    ratio = face_center_y / FRAME_H  # 转换为相对画面高度的比例

                    # 坐姿判定
                    if ratio < POSTURE_GOOD:  # 人脸位置较高, 判断坐姿较好
                        posture = 'good'  # 记录坐姿状态为正常
                        color = (0, 255, 0)      # 绿色=坐姿端正
                        text = "Good Posture"  # debug窗口显示文字
                    elif ratio < POSTURE_BAD:  # 人脸位置介于正常和严重阈值之间
                        posture = 'warn'  # 记录坐姿状态为轻微异常
                        color = (0, 255, 255)    # 黄色=轻微不良
                        text = "Slightly Slouch"  # debug窗口显示文字
                    else:  # 人脸位置过低, 判断为严重低头/驼背
                        posture = 'bad'  # 记录坐姿状态为严重异常
                        color = (0, 0, 255)      # 红色=严重低头
                        text = "Bad Posture!"  # debug窗口显示文字

                    # 显示坐姿状态文字
                    cv2.putText(display, text, (x, y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)  # 在人脸框上方写坐姿提示

                    self.no_face_frames = 0  # 检测到人脸后清零无人脸计数

                    with self.lock:  # 加锁后更新结果, 防止主线程同时读取
                        self.results.update({
                            'face_detected': True,          # 标记检测到人脸
                            'face_center_y': face_center_y, # 保存人脸中心Y坐标
                            'face_ratio': ratio,            # 保存人脸位置比例
                            'posture': posture,             # 保存坐姿状态
                            'display_frame': display,       # 保存标注后的画面
                        })
                else:  # 没有检测到人脸
                    self.no_face_frames += 1  # 连续无人脸帧数加1
                    # 超过阈值判定为无人
                    if self.no_face_frames > NO_FACE_TIMEOUT:  # 连续多帧无人脸才更新为none, 避免瞬时误判
                        with self.lock:  # 加锁后更新共享结果
                            self.results.update({
                                'face_detected': False,  # 标记没有检测到人脸
                                'face_center_y': 0,      # 人脸中心坐标清零
                                'face_ratio': 0.0,       # 人脸比例清零
                                'posture': 'none',       # 坐姿状态设为无人
                                'display_frame': display,# 保存当前画面
                            })
            else:  # 如果人脸分类器不可用
                # 人脸检测不可用时, 保持基本画面
                with self.lock:  # 加锁后只更新显示画面
                    self.results['display_frame'] = display  # debug窗口仍然可以看到摄像头画面

    # ---- 步骤六: 显示图像 (由main.py的debug模式处理) ----
    # cv2.imshow('img', img)

    def get_results(self):
        """获取最新检测结果, 返回字典副本, 保证线程安全。"""
        with self.lock:  # 加锁读取共享结果
            return dict(self.results)  # 返回副本, 防止外部直接修改内部字典

    def get_frame(self):
        """获取标注画面, 用于main.py的debug窗口。"""
        with self.lock:  # 加锁读取画面
            f = self.results.get('display_frame')  # 取出最新显示画面
            return f.copy() if f is not None else None  # 返回画面副本, 没有画面则返回None

    def stop(self):
        """停止视觉模块并释放摄像头。"""
        self.running = False  # 通知视觉循环退出
        time.sleep(0.3)  # 等待线程有时间退出循环
        if self.cap.isOpened():  # 如果摄像头仍处于打开状态
            self.cap.release()  # 释放摄像头资源
        print("[视觉] 摄像头已释放")  # 打印资源释放提示
