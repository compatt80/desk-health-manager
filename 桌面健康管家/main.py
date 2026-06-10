# -*- coding: utf-8 -*-  # 指定源码文件编码为UTF-8, 方便写中文注释
"""
桌面健康管家 - 主程序
=====================
运行方式:
  python main.py           正常模式
  python main.py --debug   调试模式 (显示摄像头画面)
"""

import sys        # 用于读取命令行参数, 判断是否包含--debug
import time       # 用于延时、计时和控制循环频率
import signal     # 用于捕获Ctrl+C退出信号
import threading  # 用于启动摄像头视觉识别子线程
import cv2        # OpenCV库, 用于显示debug摄像头窗口

from config import LOOP_INTERVAL, LCD_INTERVAL, FRAME_H  # 导入主循环间隔、LCD刷新间隔和画面高度
from sensors import SensorManager       # 导入传感器和输出设备统一管理类
from vision import PostureVision        # 导入摄像头人脸检测和坐姿识别类
from posture_alarm import PostureAlarm  # 导入工作状态、坐姿报警和久坐报警判断类


class DeskHealthManager:
    """桌面健康管家主控类, 负责把传感器、视觉识别和报警逻辑串起来。"""

    def __init__(self, debug=False):
        self.debug = debug  # 保存是否开启debug窗口的标志
        print("=" * 50)  # 打印启动分隔线
        print("  桌面健康管家 启动中...")  # 提示系统正在启动
        print("=" * 50)  # 打印启动分隔线

        # 初始化子系统
        self.sensors = SensorManager()  # 初始化DHT11、光敏、霍尔、LED、蜂鸣器、LCD等硬件
        self.vision = PostureVision()   # 初始化摄像头和Haar人脸分类器
        self.alarm = PostureAlarm()     # 初始化坐姿判断、工作状态判断和久坐提醒逻辑

        # 状态变量
        self.running = False      # 主循环运行标志, True表示程序正在监控
        self.last_lcd_update = 0  # 记录上一次刷新LCD的时间

        print("[系统] 传感器: DHT11 + 光敏 + 霍尔 + 蜂鸣器 + 双色LED + RGB LED + LCD1602")  # 输出硬件列表
        print("[系统] 视觉: Haar Cascade 人脸检测 (PPT四)")  # 输出视觉检测方法
        print("[系统] 初始化完成, 开始监控...\n")  # 提示初始化完成

    def start(self):
        """启动系统。"""
        self.running = True  # 将主循环标志设为运行

        # 启动视觉线程
        vision_thread = threading.Thread(
            target=self.vision.run,  # 子线程执行vision.py中的run方法
            name="VisionThread",    # 给线程命名, 报错时更容易定位
            daemon=True             # 设置为守护线程, 主程序退出时自动结束
        )
        vision_thread.start()  # 正式启动摄像头视觉识别线程
        time.sleep(1.5)  # 等待摄像头和识别线程准备完成

        # Ctrl+C 处理
        signal.signal(signal.SIGINT, self._on_signal)  # 捕获Ctrl+C并调用_on_signal安全退出

        # 主循环
        self._loop()  # 进入主控循环

    def _loop(self):
        """主控循环, 周期性读取数据、判断状态、更新输出。"""
        while self.running:  # running为True时一直循环
            t0 = time.time()  # 记录本轮循环开始时间

            # 1. 读取传感器
            sensor_data = self.sensors.read_all()  # 读取温湿度、光照和霍尔开合状态

            # 2. 获取视觉结果
            vision_data = self.vision.get_results()  # 从视觉线程获取人脸检测和坐姿结果

            # 3. 坐姿评估
            result = self.alarm.update(sensor_data, vision_data)  # 综合传感器和视觉数据得到工作/报警状态

            # 4. 更新双色LED (工作/非工作)
            self.sensors.update_dual_led(result['working'])  # 工作状态亮绿灯, 非工作状态亮红灯

            # 5. 更新RGB LED (久坐渐变色)
            self.sensors.update_rgb_led(result['sitting_seconds'])  # 根据久坐秒数设置RGB颜色

            # 6. 更新LCD
            now = time.time()  # 获取当前时间
            if now - self.last_lcd_update >= LCD_INTERVAL:  # 达到LCD刷新周期才更新屏幕
                self.sensors.update_lcd(
                    sensor_data,             # 传入温湿度、光照、设备开合等数据
                    result['posture_text'],  # 传入当前坐姿中文描述
                    result['working'],       # 传入当前工作状态
                )
                self.last_lcd_update = now  # 记录本次LCD刷新时间

            # 7. 提醒
            if result['need_beep'] == 'posture':  # 如果坐姿异常达到阈值
                self.sensors.beep_posture_warn()  # 蜂鸣器短促提醒
                print(f"  [!] 坐姿提醒: {result['posture_text']}")  # 在终端打印提醒信息
            elif result['need_beep'] == 'sitting':  # 如果久坐时间达到阈值
                self.sensors.beep_sitting_alert()  # 蜂鸣器长鸣提醒
                mins = result['sitting_seconds'] // 60  # 将久坐秒数换算成分钟
                print(f"  [!] 久坐提醒: 已连续坐{mins}分钟, 请起身活动!")  # 在终端打印久坐提醒

            # 8. 调试窗口 (步骤六: cv2.imshow('img', img))
            if self.debug:  # 如果启动时带了--debug参数
                self._show_debug(result, sensor_data, vision_data)  # 显示摄像头画面和状态文字

            # 9. 控制循环频率
            elapsed = time.time() - t0  # 计算本轮循环已经消耗的时间
            time.sleep(max(0, LOOP_INTERVAL - elapsed))  # 补足循环间隔, 避免CPU占用过高

    def _show_debug(self, result, sensor_data, vision_data):
        """显示OpenCV调试画面, 用于观察摄像头识别和传感器状态。"""

        frame = self.vision.get_frame()  # 获取视觉线程生成的带人脸框画面
        if frame is not None:  # 如果画面不为空才进行显示
            # 叠加状态信息
            posture = result['posture']  # 获取当前坐姿状态: good/warn/bad/none
            color_map = {                # 定义不同坐姿状态对应的文字颜色
                'good': (0, 255, 0),     # good用绿色
                'warn': (0, 255, 255),   # warn用黄色
                'bad':  (0, 0, 255),     # bad用红色
                'none': (128, 128, 128), # none用灰色
            }
            posture_text_map = {  # debug窗口使用英文, 避免OpenCV中文显示为问号
                'good': 'Good',   # 坐姿正常
                'warn': 'Warn',   # 轻微低头
                'bad': 'Bad',     # 严重低头/驼背
                'none': 'None',   # 未检测到人脸
            }
            debug_posture_text = posture_text_map.get(posture, '--')  # 未知状态显示--
            cv2.putText(frame, f"Posture: {debug_posture_text}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, color_map.get(posture, (255,255,255)), 2)  # 在左上角显示坐姿状态

            mins = result['sitting_seconds'] // 60  # 久坐秒数换算成分钟
            secs = result['sitting_seconds'] % 60   # 久坐秒数换算成剩余秒
            cv2.putText(frame, f"Sitting: {mins:02d}:{secs:02d}",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (255, 255, 255), 1)  # 在画面上显示久坐计时

            temp = sensor_data.get('temperature', 0)  # 取温度值, 取不到时默认为0
            hum = sensor_data.get('humidity', 0)      # 取湿度值, 取不到时默认为0
            light = sensor_data.get('light', 0)       # 取光照值, 取不到时默认为0
            cv2.putText(frame, f"T:{temp:.1f}C H:{hum:.0f}% L:{light}",
                        (10, FRAME_H - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (200, 200, 200), 1)  # 在画面底部显示温湿度和光照

            # 步骤六: cv2.imshow('img', img)
            cv2.imshow("Desk Health Manager", frame)  # 弹出窗口显示摄像头画面
            cv2.waitKey(1)  # 等待1毫秒, 保证窗口能刷新

    def _on_signal(self, signum, frame):
        print("\n[系统] 收到退出信号...")  # 提示收到Ctrl+C
        self.shutdown()  # 调用统一关闭函数

    def shutdown(self):
        self.running = False  # 停止主循环
        self.vision.stop()  # 停止视觉线程并释放摄像头
        self.sensors.cleanup()  # 关闭LED、蜂鸣器、LCD并清理GPIO
        if self.debug:  # 如果打开了debug窗口
            cv2.destroyAllWindows()  # 关闭所有OpenCV窗口
        print("[系统] 桌面健康管家已关闭, 再见!")  # 打印关闭提示


# ==================== 入口 ====================

def main():
    debug = "--debug" in sys.argv  # 判断命令行是否带--debug参数
    app = DeskHealthManager(debug=debug)  # 创建系统主控对象
    try:
        app.start()  # 启动桌面健康管家
    except KeyboardInterrupt:
        pass  # Ctrl+C退出时不打印额外异常
    except Exception as e:
        print(f"[错误] {e}")  # 打印错误信息
        import traceback  # 导入traceback用于显示完整报错位置
        traceback.print_exc()  # 打印完整异常堆栈
    finally:
        app.shutdown()  # 无论正常退出还是异常退出, 都清理硬件资源


if __name__ == "__main__":
    main()  # 直接运行main.py时执行主函数
