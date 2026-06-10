# -*- coding: utf-8 -*-
"""
桌面健康管家 - 坐姿评估与健康提醒
==================================

融合传感器数据 + 视觉结果:
  霍尔传感器 → 设备是否打开 (工作/非工作)
  人脸检测   → 画面中是否有人 (有人/无人)
  人脸位置   → 坐姿是否端正 (抬头/低头)

提醒机制:
  1. 坐姿不良持续 → 蜂鸣短促提醒
  2. 连续久坐超45分钟 → 蜂鸣长鸣提醒
  3. RGB LED 随久坐时间渐变: 绿(0min) → 黄(60min) → 红(120min)
  4. LCD 实时显示温湿度、光照、状态
"""

import time  # 导入时间模块, 用于计算久坐时长和提醒间隔
from config import POSTURE_BAD_FRAMES, SITTING_ALERT_SEC, BEEP_INTERVAL  # 导入报警阈值配置


class PostureAlarm:
    """坐姿和久坐报警逻辑类, 只负责判断状态, 不直接操作硬件。"""

    def __init__(self):
        # 坐姿状态
        self.current_posture = 'none'   # 当前坐姿状态, good/warn/bad/none
        self.bad_frame_count = 0        # 连续检测到不良坐姿的次数

        # 久坐计时
        self.sitting_start_time = None  # 本轮开始坐下的时间戳
        self.sitting_seconds = 0        # 当前连续坐着的秒数
        self.is_sitting = False         # True表示正在工作/坐着

        # 提醒状态
        self.posture_beeped = False     # 防止同一轮不良坐姿重复报警
        self.sitting_alerted = False    # 防止同一轮久坐重复报警
        self.last_posture_text = 'none' # 记录上一次坐姿文字, 便于后续扩展显示

    def update(self, sensor_data, vision_data):
        """
        主更新函数 (每个主循环调用一次)

        参数:
          sensor_data:  {'device_open': bool, ...}
          vision_data:  {'posture': 'good'/'warn'/'bad'/'none', 'face_detected': bool}

        返回:
          {
            'working': bool,       # 系统是否处于工作状态
            'posture': str,        # 当前坐姿级别
            'posture_text': str,   # 中文坐姿描述
            'sitting_seconds': int,# 久坐秒数
            'need_beep': str,      # None / 'posture' / 'sitting'
            'face_count': int,     # 检测到的人脸数
          }
        """
        device_open = sensor_data.get('device_open', False)      # 从霍尔传感器结果中取设备开合状态
        face_detected = vision_data.get('face_detected', False)  # 从视觉结果中取是否检测到人脸
        posture = vision_data.get('posture', 'none')             # 从视觉结果中取坐姿等级

        # ---- 工作状态判定 ----
        # 设备打开 + 检测到人脸 = 工作模式
        working = device_open and face_detected  # 两个条件同时满足才认为用户正在使用设备

        # ---- 坐姿追踪 ----
        if working:  # 只有进入工作状态时才统计坐姿和久坐时间
            self.current_posture = posture  # 更新当前坐姿状态

            # 连续不良帧计数
            if posture in ('bad', 'warn'):  # warn或bad都认为是不良坐姿
                self.bad_frame_count += 1   # 连续不良次数加1
            else:
                self.bad_frame_count = max(0, self.bad_frame_count - 1)  # 坐姿恢复后逐步降低计数

            # 久坐计时
            if not self.is_sitting:  # 如果刚从非工作状态进入工作状态
                self.is_sitting = True  # 标记为正在坐着/工作中
                self.sitting_start_time = time.time()  # 记录本轮久坐开始时间
                self.sitting_alerted = False  # 新一轮久坐重新允许报警
            self.sitting_seconds = time.time() - self.sitting_start_time  # 计算当前连续久坐秒数

        else:
            # 非工作状态: 重置
            self.bad_frame_count = 0  # 未工作时不统计不良坐姿
            if self.is_sitting:  # 如果上一轮处于工作状态, 现在退出工作
                self.is_sitting = False  # 标记为未坐着/未工作
                self.sitting_start_time = None  # 清空久坐开始时间
                self.sitting_seconds = 0  # 久坐时间清零
                self.posture_beeped = False  # 坐姿报警状态复位

        # ---- 提醒判定 ----
        need_beep = None  # 默认本轮不需要蜂鸣器报警

        # 坐姿不良提醒 (连续不良帧数超过阈值)
        if self.bad_frame_count >= POSTURE_BAD_FRAMES and not self.posture_beeped:
            need_beep = 'posture'  # 标记需要坐姿短促提醒
            self.posture_beeped = True  # 本轮不良坐姿已经提醒过

        # 坐姿恢复, 重置提醒标记
        if self.bad_frame_count < POSTURE_BAD_FRAMES:
            self.posture_beeped = False  # 低于阈值后允许下次再次提醒

        # 久坐提醒 (超45分钟)
        if (self.sitting_seconds >= SITTING_ALERT_SEC
                and not self.sitting_alerted):
            need_beep = 'sitting'  # 标记需要久坐长鸣提醒
            self.sitting_alerted = True  # 本轮久坐已经提醒过

        # ---- 坐姿文本 ----
        posture_text_map = {       # 将程序内部状态转换成LCD/终端可读的中文
            'good': '坐姿端正',     # good表示坐姿正常
            'warn': '轻微低头',     # warn表示轻微异常
            'bad':  '严重驼背!',    # bad表示严重异常
            'none': '无人',         # none表示没有检测到人
        }
        posture_text = posture_text_map.get(self.current_posture, '--')  # 防止未知状态导致报错

        return {  # 返回给main.py, 由主程序决定怎么更新硬件
            'working': working,                         # 当前是否工作中
            'posture': self.current_posture,             # 当前坐姿状态
            'posture_text': posture_text,                # 当前坐姿中文描述
            'sitting_seconds': int(self.sitting_seconds),# 当前久坐秒数
            'need_beep': need_beep,                      # 蜂鸣器提醒类型
        }
