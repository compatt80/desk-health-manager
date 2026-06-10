# -*- coding: utf-8 -*-
"""
桌面健康管家 - 配置文件
======================

传感器使用 (≥5个, 摄像头除外):
  1. DHT11         - 温湿度采集 (实验24)
  2. 光敏传感器     - 环境光照采集, PCF8591 ADC读取 (实验18+实验11)
  3. 霍尔传感器     - 设备盖子开合检测 (实验15)
  4. 有源蜂鸣器     - 坐姿/久坐提醒 (实验7)
  5. 双色LED       - 绿色=工作中 / 红色=非工作 (实验1)
  6. RGB LED       - 久坐时间渐变色环 (实验2)
  7. LCD1602 IIC   - 水滴/温度计/太阳图标 + 数值 (实验26)
  8. 摄像头        - 人脸检测 → 坐姿分析 (PPT四)

"""

# ==================== GPIO引脚 (BCM编码) ====================

DHT11_PIN = 17                  # 温湿度传感器
HALL_SENSOR_PIN = 27            # 霍尔传感器 (设备开合)
BUZZER_PIN = 18                 # 有源蜂鸣器 (PWM)
BUZZER_ACTIVE_LOW = True        # True=低电平响, False=高电平响
DUAL_LED_R = 22                 # 双色LED 红灯
DUAL_LED_G = 23                 # 双色LED 绿灯
RGB_R = 5                       # RGB LED 红
RGB_G = 6                       # RGB LED 绿
RGB_B = 13                      # RGB LED 蓝

LCD_I2C_ADDR = 0x27             # LCD1602 PCF8574 I2C地址
PCF8591_ADDR = 0x48             # PCF8591 AD/DA转换器 I2C地址
I2C_BUS = 1                     # I2C-1总线

# ==================== 传感器阈值 ====================

TEMP_HIGH = 32.0                # 高温提醒 (℃)
HUMIDITY_LOW = 30.0             # 干燥提醒 (%)
LIGHT_DIM = 80                  # 光线昏暗阈值 (PCF8591: 0-255)
LIGHT_BRIGHT = 200              # 光线过亮阈值
HALL_OPEN_VALUE = 1             # 设备打开时的GPIO值: 磁铁离开时为打开

# ==================== 人脸检测参数 (PPT四 page 9-11) ====================

# 步骤一: face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
HAAR_PATH = "/usr/local/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"

# detectMultiScale() 参数
# scaleFactor=1.1: 每次缩小图像的比例
# minNeighbors=5:  匹配所需周围矩形框数目 (默认3, 提高减少误检)
# minSize:         人脸最小尺寸
SCALE_FACTOR = 1.1
MIN_NEIGHBORS = 5
MIN_FACE_SIZE = (40, 40)
NO_FACE_TIMEOUT = 10             # 连续10帧未检测到人脸后判定为无人

# 人脸位置 → 坐姿判定
# 人脸中心Y坐标 / 画面高度 → 越小=越靠上=抬头, 越大=越靠下=低头
POSTURE_GOOD = 0.45             # < 0.45: 坐姿端正
POSTURE_BAD = 0.60              # > 0.60: 严重低头

# ==================== 提醒时间配置 ====================

POSTURE_BAD_FRAMES = 15          # 连续不良帧数阈值
SITTING_ALERT_SEC = 45 * 60      # 久坐提醒: 45分钟
RGB_FULL_RED_SEC = 60            # RGB全红: 连续坐1分钟, 便于课堂演示
BEEP_INTERVAL = 15               # 蜂鸣间隔 (秒), 避免频繁打扰

# ==================== 摄像头配置 ====================

CAMERA_TYPE = "opencv"           # picamera2 或 opencv
CAMERA_INDEX = 0
FRAME_W = 640
FRAME_H = 480
FRAME_INTERVAL = 0.2             # 帧处理间隔 (秒)

# ==================== 系统参数 ====================

LOOP_INTERVAL = 0.5
LCD_INTERVAL = 1.0

# ==================== LCD1602 自定义字符 (CGRAM 5x8点阵) ====================

# 水滴 (CGRAM 地址 0x00)
WATER_DROP = [
    0b00100,
    0b00100,
    0b01110,
    0b01110,
    0b11111,
    0b11111,
    0b11111,
    0b01110,
]

# 温度计 (CGRAM 地址 0x01)
THERMOMETER = [
    0b01110,
    0b01010,
    0b01110,
    0b01110,
    0b01110,
    0b11111,
    0b11111,
    0b01110,
]

# 太阳 (CGRAM 地址 0x02)
SUN = [
    0b10101,
    0b01110,
    0b11111,
    0b11111,
    0b11111,
    0b01110,
    0b10101,
    0b00000,
]

# 上箭头: 光照偏亮 (CGRAM 地址 0x03)
ARROW_UP = [
    0b00100,
    0b01110,
    0b10101,
    0b00100,
    0b00100,
    0b00100,
    0b00100,
    0b00000,
]

# 下箭头: 光照偏暗 (CGRAM 地址 0x04)
ARROW_DOWN = [
    0b00100,
    0b00100,
    0b00100,
    0b00100,
    0b10101,
    0b01110,
    0b00100,
    0b00000,
]

# 勾: 光照合适 (CGRAM 地址 0x05)
CHECK_MARK = [
    0b00000,
    0b00001,
    0b00011,
    0b10110,
    0b11100,
    0b01000,
    0b00000,
    0b00000,
]
