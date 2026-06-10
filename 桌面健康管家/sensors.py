# -*- coding: utf-8 -*-
"""
桌面健康管家 - 传感器驱动模块
==============================

驱动列表 :
  实验24: DHT11 温湿度传感器
  实验18: 光敏传感器 + 实验11: PCF8591 AD转换
  实验15: 霍尔传感器
  实验7:  有源蜂鸣器
  实验1:  双色LED
  实验2:  RGB LED
  实验26: LCD1602 IIC 液晶显示

"""

import time  # 用于传感器时序、延时和提醒间隔计时
import threading  # 用于蜂鸣器定时关闭, 避免阻塞主循环
import RPi.GPIO as GPIO  # 树莓派GPIO控制库
import smbus  # I2C通信库, 用于PCF8591和LCD1602
from config import *  # 导入所有GPIO编号、阈值、LCD自定义字符等配置


# ==================== DHT11 温湿度传感器 ====================

class DHT11Sensor:
    """DHT11温湿度传感器驱动类。"""

    def __init__(self, pin=DHT11_PIN):
        self.pin = pin  # 保存DHT11数据引脚编号
        self.temperature = 0.0  # 保存最近一次成功读取的温度
        self.humidity = 0.0  # 保存最近一次成功读取的湿度
        self._last_read = 0  # 保存上一次读取时间, 控制DHT11读取间隔

    def read(self):
        """读取DHT11, 返回 (温度℃, 湿度%)"""
        # DHT11采样间隔需 ≥2秒
        now = time.time()  # 获取当前时间
        if now - self._last_read < 2.0:  # 如果距离上次读取不足2秒
            return self.temperature, self.humidity  # 返回缓存值, 避免DHT11读取过频
        self._last_read = now  # 更新本次读取时间

        # ---- 发送起始信号: 拉低18ms, 拉高40us ----
        GPIO.setup(self.pin, GPIO.OUT)  # 将数据脚临时设置为输出
        GPIO.output(self.pin, GPIO.LOW)  # 主机拉低总线, 发送开始信号
        time.sleep(0.018)  # 保持低电平18ms
        GPIO.output(self.pin, GPIO.HIGH)  # 拉高总线
        time.sleep(0.00004)  # 保持高电平约40us
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # 切换为输入, 等待DHT11响应

        # ---- 等待DHT11响应: 拉低80us, 拉高80us ----
        if self._wait_level(GPIO.LOW, 0.0001) == -1:
            return self.temperature, self.humidity
        if self._wait_level(GPIO.HIGH, 0.0001) == -1:
            return self.temperature, self.humidity

        # ---- 读取40位数据 ----
        bits = []  # 保存读取到的40位二进制数据
        for _ in range(40):  # DHT11一次返回40位数据
            if self._wait_level(GPIO.LOW, 0.0001) == -1:
                return self.temperature, self.humidity
            t0 = time.time()  # 记录高电平开始时间
            if self._wait_level(GPIO.HIGH, 0.0001) == -1:
                return self.temperature, self.humidity
            bits.append(1 if (time.time() - t0) > 0.00004 else 0)  # 高电平持续时间长表示1, 短表示0

        # ---- 位→字节 ----
        data = []  # 保存转换后的5个字节
        for i in range(5):  # 40位数据转换成5个字节
            byte = 0  # 当前字节初始值
            for j in range(8):  # 每8位组成1个字节
                byte = (byte << 1) | bits[i * 8 + j]  # 左移并加入当前位
            data.append(byte)  # 保存转换出的字节

        # ---- 校验和 ----
        if data[0] + data[1] + data[2] + data[3] == data[4]:
            self.humidity = data[0] + data[1] * 0.1  # 解析湿度整数和小数部分
            self.temperature = data[2] + data[3] * 0.1  # 解析温度整数和小数部分

        return self.temperature, self.humidity  # 返回温度和湿度

    def _wait_level(self, level, timeout):
        """等待引脚达到指定电平"""
        t0 = time.time()  # 记录等待开始时间
        while GPIO.input(self.pin) == level:  # 持续等待引脚离开指定电平
            if time.time() - t0 > timeout:  # 如果等待超时
                return -1  # 返回-1表示失败
        return 0  # 返回0表示成功等到电平变化


# ==================== PCF8591 + 光敏传感器 ====================

class LightSensor:
    """
    光敏传感器 (通过PCF8591 ADC读取模拟值)

    PCF8591: I2C地址0x48, 4通道8位ADC
    AIN0 接光敏传感器模块的模拟输出脚
    """

    def __init__(self, addr=PCF8591_ADDR, bus_num=I2C_BUS):
        self.addr = addr  # 保存PCF8591的I2C地址, 默认0x48
        self.bus = smbus.SMBus(bus_num)  # 打开I2C总线, 树莓派一般使用1号总线
        self.light_value = 0  # 保存光照值, 范围0-255 (8位ADC)

    def read(self):
        """读取光照值 (0-255, 越大越亮)"""
        try:
            # 写入控制字节: 选择AIN0通道, 启用模拟输出
            self.bus.write_byte(self.addr, 0x40)  # 写控制字, 选择AIN0通道
            time.sleep(0.001)  # 给PCF8591一点转换时间
            # 先读一次(前一通道值), 再读一次(当前通道值)
            self.bus.read_byte(self.addr)  # 第一次读到的通常是上一次转换结果
            self.light_value = self.bus.read_byte(self.addr)  # 第二次读取当前AIN0光照值
        except Exception:
            pass  # 偶发I2C读取失败时不刷屏, 保留上一次有效值
        return self.light_value  # 返回当前缓存的光照值

    def is_dim(self):
        """光线是否昏暗 (需开灯)"""
        return self.light_value < LIGHT_DIM  # 小于暗光阈值表示偏暗

    def is_bright(self):
        """光线是否过亮"""
        return self.light_value > LIGHT_BRIGHT  # 大于强光阈值表示偏亮


# ==================== 霍尔传感器 ====================

class HallSensor:
    """
    霍尔传感器 - 检测设备盖子是否打开 (实验15)

    原理: 霍尔元件检测磁场, 设备盖子合上时磁铁靠近 → 输出变化
    设备展开(打开)时磁铁远离 → 输出相反
    """

    def __init__(self, pin=HALL_SENSOR_PIN):
        self.pin = pin  # 保存霍尔传感器信号引脚
        self.is_open = False  # True表示设备已打开
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # 设置为输入并启用上拉

    def read(self):
        """
        读取设备开合状态
        返回: True=设备打开/展开, False=设备合上
        """
        self.is_open = (GPIO.input(self.pin) == HALL_OPEN_VALUE)  # 根据配置判断当前是否打开
        return self.is_open  # 返回设备开合状态


# ==================== 有源蜂鸣器 ====================

class Buzzer:
    """
    有源蜂鸣器
    有源蜂鸣器只需要控制开/关, 坐姿/久坐提醒
    """

    def __init__(self, pin=BUZZER_PIN):
        self.pin = pin  # 保存蜂鸣器控制引脚
        self.is_on = False  # 保存蜂鸣器当前是否正在响
        GPIO.setup(self.pin, GPIO.OUT)  # 设置蜂鸣器引脚为输出
        self.stop()  # 初始化时先确保蜂鸣器关闭

    def _on_level(self):
        return GPIO.LOW if BUZZER_ACTIVE_LOW else GPIO.HIGH  # 根据模块触发方式返回响铃电平

    def _off_level(self):
        return GPIO.HIGH if BUZZER_ACTIVE_LOW else GPIO.LOW  # 根据模块触发方式返回关闭电平

    def beep(self, freq=800, duty=50, duration=0.3):
        """短促蜂鸣提醒"""
        GPIO.output(self.pin, self._on_level())  # 输出有效电平, 让蜂鸣器响
        self.is_on = True  # 更新蜂鸣器状态
        if duration > 0:  # 如果设置了持续时间
            threading.Timer(duration, self.stop).start()  # 定时关闭蜂鸣器, 不阻塞主循环

    def double_beep(self):
        """两声短促提醒 (坐姿不良)"""
        self.beep(800, 50, 0.15)  # 第一声短响
        time.sleep(0.15)  # 两声之间间隔0.15秒
        self.beep(800, 50, 0.15)  # 第二声短响

    def long_beep(self):
        """长鸣提醒 (久坐超时)"""
        self.beep(1000, 60, 1.0)  # 长响1秒, 用于久坐提醒

    def stop(self):
        """停止蜂鸣"""
        GPIO.output(self.pin, self._off_level())  # 输出关闭电平
        self.is_on = False  # 更新蜂鸣器状态为关闭

    def cleanup(self):
        self.stop()  # 清理时确保蜂鸣器关闭


# ==================== 双色LED ====================

class DualLED:
    """
    双色LED (实验1)
    红色: 非工作模式 (设备未打开/未检测到人脸)
    绿色: 正常工作模式
    """

    def __init__(self, red_pin=DUAL_LED_R, green_pin=DUAL_LED_G):
        self.red_pin = red_pin  # 保存红灯引脚
        self.green_pin = green_pin  # 保存绿灯引脚
        GPIO.setup(self.red_pin, GPIO.OUT)  # 红灯引脚设置为输出
        GPIO.setup(self.green_pin, GPIO.OUT)  # 绿灯引脚设置为输出
        self.off()  # 初始化时先关闭双色LED

    def set_green(self):
        """绿色=工作模式"""
        GPIO.output(self.red_pin, GPIO.LOW)  # 关闭红灯
        GPIO.output(self.green_pin, GPIO.HIGH)  # 打开绿灯

    def set_red(self):
        """红色=非工作模式"""
        GPIO.output(self.green_pin, GPIO.LOW)  # 关闭绿灯
        GPIO.output(self.red_pin, GPIO.HIGH)  # 打开红灯

    def off(self):
        """熄灭"""
        GPIO.output(self.red_pin, GPIO.LOW)  # 关闭红灯
        GPIO.output(self.green_pin, GPIO.LOW)  # 关闭绿灯


# ==================== RGB LED ====================

class RGBLED:
    """
    RGB LED (实验2)
    根据久坐时间渐变: 绿色(0h) → 黄色 → 红色(2h+)
    使用PWM控制三路颜色通道
    """

    def __init__(self, r_pin=RGB_R, g_pin=RGB_G, b_pin=RGB_B):
        self.pins = {'R': r_pin, 'G': g_pin, 'B': b_pin}  # 保存RGB三路颜色对应的GPIO引脚
        self.pwm = {}  # 保存每一路颜色的PWM对象
        for name, pin in self.pins.items():  # 逐个初始化R/G/B三路引脚
            GPIO.setup(pin, GPIO.OUT)  # 设置当前颜色引脚为输出
            GPIO.output(pin, GPIO.LOW)  # 初始化为低电平
            p = GPIO.PWM(pin, 100)  # 创建100Hz PWM对象
            p.start(0)  # 初始占空比为0, LED不亮
            self.pwm[name] = p  # 保存PWM对象, 后续调节颜色

    def set_color(self, r, g, b):
        """
        设置RGB颜色
        r/g/b: 0.0 ~ 1.0 (PWM占空比)
        """
        self.pwm['R'].ChangeDutyCycle(r * 100)  # 设置红色通道占空比
        self.pwm['G'].ChangeDutyCycle(g * 100)  # 设置绿色通道占空比
        self.pwm['B'].ChangeDutyCycle(b * 100)  # 设置蓝色通道占空比

    def set_by_elapsed(self, elapsed_seconds):
        """
        根据久坐时间设置颜色
        0分钟→纯绿, 线性过渡, 120分钟→纯红
        """
        ratio = min(elapsed_seconds / RGB_FULL_RED_SEC, 1.0)  # 久坐比例, 最大不超过1
        r = ratio              # 红色随久坐时间从0增加到1
        g = 1.0 - ratio        # 绿色随久坐时间从1降低到0
        b = 0.0                # 蓝色不用, 保持0
        self.set_color(r, g, b)  # 应用计算后的颜色

    def off(self):
        self.set_color(0, 0, 0)  # 三路占空比都为0, RGB熄灭

    def cleanup(self):
        for p in self.pwm.values():  # 遍历三路PWM对象
            p.stop()  # 停止PWM输出
        self.off()  # 清理后确保RGB灯熄灭


# ==================== IIC LCD1602 ====================

class LCD1602:
    """
    IIC LCD1602 液晶显示屏 (实验26)
    PCF8574 I2C转接板, 4位模式驱动HD44780

    显示格式 (16x2):
      Line1: [水滴]45% [温度计]26C
      Line2: [太阳]Light:[状态图标] Work/Idle
    """

    LCD_CLEAR = 0x01  # LCD清屏指令
    LCD_HOME = 0x02  # 光标回到原点指令
    LCD_DISPLAY_ON = 0x0C  # 打开显示且不显示光标
    LCD_FUNC_4BIT_2LINE = 0x28  # 设置4位模式、2行显示
    LCD_SET_DDRAM = 0x80  # 设置显示内存地址的指令基值
    LCD_SET_CGRAM = 0x40  # 设置自定义字符内存地址的指令基值

    BACKLIGHT = 0x08  # 背光控制位
    ENABLE = 0x04  # LCD使能位
    RS = 0x01  # 数据/命令选择位, 1表示数据, 0表示命令

    def __init__(self, addr=LCD_I2C_ADDR, bus_num=I2C_BUS):
        self.addr = addr  # 保存LCD的I2C地址, 常见为0x27
        self.bus = smbus.SMBus(bus_num)  # 打开I2C总线
        self._init_lcd()  # 初始化LCD显示模式
        self._load_custom_chars()  # 写入水滴、温度计、太阳、箭头、勾等自定义字符
        self.clear()  # 初始化完成后清屏

    def _write(self, data):
        """I2C写一个字节"""
        self.bus.write_byte(self.addr, data)  # 通过I2C向LCD背包写1个字节
        time.sleep(0.0001)  # 短暂延时, 保证LCD有时间处理

    def _pulse_enable(self, data):
        """带使能脉冲的写入"""
        self._write(data | self.BACKLIGHT | self.ENABLE)  # 拉高使能位, 准备写入
        time.sleep(0.000001)  # 保持极短时间
        self._write(data | self.BACKLIGHT)  # 拉低使能位, 完成一次脉冲
        time.sleep(0.00005)  # 等待LCD执行

    def _send_nibble(self, nibble, rs=0):
        """发送4位半字节 (LCD 4位模式)"""
        data = nibble & 0xF0  # 只保留高4位数据
        if rs:  # 如果发送的是显示数据而不是命令
            data |= self.RS  # 设置RS位为1
        self._pulse_enable(data)  # 发送使能脉冲写入半字节

    def _send_byte(self, byte, rs=0):
        """发送一个字节 (先高4位, 后低4位)"""
        self._send_nibble(byte & 0xF0, rs)  # 先发送高4位
        self._send_nibble((byte << 4) & 0xF0, rs)  # 再发送低4位

    def _init_lcd(self):
        """初始化LCD为4位2行模式"""
        time.sleep(0.05)  # LCD上电后需要等待稳定
        for _ in range(3):  # 按HD44780初始化流程发送3次0x30
            self._send_nibble(0x30)  # 发送初始化半字节
            time.sleep(0.005)  # 每次初始化命令后等待
        self._send_nibble(0x20)  # 切换到4位数据模式
        time.sleep(0.001)  # 等待模式切换完成
        self._send_byte(self.LCD_FUNC_4BIT_2LINE)  # 设置4位、2行显示
        self._send_byte(self.LCD_DISPLAY_ON)  # 打开显示
        self._send_byte(self.LCD_CLEAR)  # 清屏
        time.sleep(0.002)  # 清屏指令需要更长时间
        self._send_byte(0x06)  # 设置写入后光标右移

    def _load_custom_chars(self):
        """
        将自定义字符写入CGRAM
        CGRAM共64字节, 每个字符占8字节, 最多存8个字符
        水滴→地址0, 温度计→地址1, 太阳→地址2
        上箭头→地址3, 下箭头→地址4, 勾→地址5
        """
        chars = [  # 每个元组表示(自定义字符编号, 5x8点阵数据)
            (0x00, WATER_DROP),   # 0号字符: 水滴
            (0x01, THERMOMETER),  # 1号字符: 温度计
            (0x02, SUN),          # 2号字符: 太阳
            (0x03, ARROW_UP),     # 3号字符: 上箭头
            (0x04, ARROW_DOWN),   # 4号字符: 下箭头
            (0x05, CHECK_MARK),   # 5号字符: 勾
        ]
        for cg_addr, bitmap in chars:  # 逐个写入自定义字符
            self._send_byte(self.LCD_SET_CGRAM | (cg_addr * 8))  # 设置CGRAM写入地址
            for row in bitmap:  # 写入该字符的8行点阵
                self._send_byte(row, rs=1)  # rs=1表示写入字符数据

    def clear(self):
        self._send_byte(self.LCD_CLEAR)  # 发送清屏命令
        time.sleep(0.002)  # 清屏需要等待LCD执行

    def set_cursor(self, row, col):
        addr = col + (0x40 if row == 1 else 0x00)  # 第0行起始0x00, 第1行起始0x40
        self._send_byte(self.LCD_SET_DDRAM | addr)  # 设置LCD光标位置

    def write(self, text, row=0, col=0):
        """在指定位置写字符串"""
        self.set_cursor(row, col)  # 先把光标移动到指定位置
        width = max(0, 16 - col)  # 计算本行剩余可显示宽度
        for ch in text[:width].ljust(width):  # 截断到16字符并补空格覆盖旧内容
            self._send_byte(ord(ch), rs=1)  # 逐字符写入LCD

    def show_status(self, humidity, temperature, light,
                    posture_text, working):
        """
        显示完整状态
        参数:
          humidity:     湿度值 (如 45.0)
          temperature:  温度值 (如 26.0)
          light:        光照值 (0-255)
          posture_text: 坐姿状态文字
          working:      是否工作中 (True=双色绿灯)
        """
        # Line 1: [水滴]XX% [温度计]XXC
        line1 = "\x00{:3.0f}% \x01{:3.0f}C".format(humidity, temperature)  # 第一行显示湿度和温度
        # Line 2: [太阳]Light:[上箭头/下箭头/勾] Work/Idle
        if light > LIGHT_BRIGHT:  # 光照值高于上限
            light_icon = "\x03"   # 偏亮: 上箭头
        elif light < LIGHT_DIM:  # 光照值低于下限
            light_icon = "\x04"   # 偏暗: 下箭头
        else:
            light_icon = "\x05"   # 合适: 勾
        status = "Work" if working else "Idle"  # 工作状态用英文显示, 避免LCD中文乱码
        line2 = "\x02Light:{} {}".format(light_icon, status)  # 第二行显示光照图标和工作状态

        self.write(line1, 0, 0)  # 写入LCD第一行
        self.write(line2, 1, 0)  # 写入LCD第二行


# ==================== 传感器管理器 ====================

class SensorManager:
    """统一管理所有传感器和输出模块, 给main.py提供简单接口。"""

    def __init__(self):
        GPIO.setmode(GPIO.BCM)  # 使用BCM编号方式, 与config.py中的G17/G18等一致
        GPIO.setwarnings(False)  # 关闭重复初始化GPIO时的警告

        self.dht11 = DHT11Sensor()  # 创建DHT11温湿度传感器对象
        self.light = LightSensor()  # 创建PCF8591光敏传感器对象
        self.hall = HallSensor()  # 创建霍尔传感器对象
        self.buzzer = Buzzer()  # 创建蜂鸣器对象
        self.dual_led = DualLED()  # 创建双色LED对象
        self.rgb_led = RGBLED()  # 创建RGB LED对象
        self.lcd = LCD1602()  # 创建LCD1602显示屏对象

        # 蜂鸣控制
        self.last_beep_time = 0  # 记录上一次蜂鸣时间, 用于限制提醒频率

        # 启动显示
        self.lcd.clear()  # LCD清屏
        self.lcd.write("Desk Health", 0, 0)  # 第一行显示项目名称
        self.lcd.write("Starting...", 1, 0)  # 第二行显示启动中
        time.sleep(1)  # 保持启动画面1秒

    def read_all(self):
        """读取所有传感器"""
        temp, hum = self.dht11.read()  # 读取温度和湿度
        light = self.light.read()  # 读取光照值
        device_open = self.hall.read()  # 读取设备是否打开

        return {  # 将所有传感器结果打包成字典返回给主程序
            'temperature': temp,  # 温度
            'humidity': hum,  # 湿度
            'light': light,  # 光照值
            'device_open': device_open,  # 设备开合状态
            'light_dim': self.light.is_dim(),  # 是否偏暗
            'light_bright': self.light.is_bright(),  # 是否偏亮
        }

    def update_dual_led(self, working):
        """工作模式指示灯"""
        if working:  # 如果系统处于工作状态
            self.dual_led.set_green()  # 双色LED显示绿色
        else:
            self.dual_led.set_red()  # 非工作状态显示红色

    def update_rgb_led(self, sitting_seconds):
        """久坐时间渐变色"""
        self.rgb_led.set_by_elapsed(sitting_seconds)  # 按久坐时间设置RGB渐变色

    def update_lcd(self, data, posture_text, working):
        """刷新LCD显示"""
        self.lcd.show_status(  # 调用LCD对象显示完整状态
            humidity=data['humidity'],  # 传入湿度
            temperature=data['temperature'],  # 传入温度
            light=data['light'],  # 传入光照
            posture_text=posture_text,  # 传入坐姿文字, 目前LCD主要显示工作状态
            working=working,  # 传入工作状态
        )

    def beep_posture_warn(self):
        """坐姿提醒: 避免频繁响"""
        now = time.time()  # 获取当前时间
        if now - self.last_beep_time > BEEP_INTERVAL:  # 距离上次蜂鸣超过间隔才允许提醒
            self.buzzer.double_beep()  # 蜂鸣器响两声
            self.last_beep_time = now  # 更新蜂鸣时间

    def beep_sitting_alert(self):
        """久坐提醒: 长鸣"""
        self.buzzer.long_beep()  # 蜂鸣器长响
        self.last_beep_time = time.time()  # 更新蜂鸣时间

    def cleanup(self):
        self.buzzer.cleanup()  # 关闭蜂鸣器
        self.rgb_led.cleanup()  # 停止RGB PWM并熄灭
        self.dual_led.off()  # 关闭双色LED
        self.lcd.clear()  # LCD清屏
        self.lcd.write("System", 0, 0)  # 显示系统提示
        self.lcd.write("Shutdown...", 1, 0)  # 显示关机提示
        GPIO.cleanup()  # 释放所有GPIO资源
