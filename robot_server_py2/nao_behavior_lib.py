# -*- coding: utf-8 -*-
"""
NAO 实体机器人行为控制核心库 (Python 2.7)
专为高压模拟面试场景设计，包含微表情、视线压迫、LED反馈等。
无 Mock 模式，直连真实机器人运行。
"""

from naoqi import ALProxy
import math
import time


class NaoBehaviorController(object):
    def __init__(self, ip="192.168.93.152", port=9559):
        """初始化代理，直连物理机器人"""
        self.ip = ip
        self.port = port

        print("[INFO] 正在连接实体机器人: %s:%s ..." % (ip, port))
        try:
            self.tts = ALProxy("ALTextToSpeech", ip, port)
            self.motion = ALProxy("ALMotion", ip, port)
            self.posture = ALProxy("ALRobotPosture", ip, port)
            self.leds = ALProxy("ALLeds", ip, port)

            # 基础设置：中文、唤醒、初始站姿
            self.tts.setLanguage("Chinese")
            self.motion.wakeUp()
            self.posture.goToPosture("StandInit", 0.5)  # 标准站姿，保证重心稳定
            print("[INFO] 机器人连接成功！准备执行高压面试指令。")
        except Exception as e:
            print("[ERROR] 无法连接到机器人，请检查 IP 和网络！错误详情: %s" % str(e))
            raise

    # ==========================================
    # 基础交互模块
    # ==========================================
    def speak(self, text):
        """说话"""
        if text:
            print("[ACTION] 机器人正在说话: %s" % text)
            self.tts.say(str(text))
        return True

    def rest(self):
        """进入静息状态（释放电机锁定，防止过热）"""
        print("[ACTION] 机器人进入静息态")
        self.posture.goToPosture("Crouch", 0.5)  # 先安全蹲下
        self.motion.rest()
        return True

    # ==========================================
    # 面试动作与微表情模块 (基于物理参数限制)
    # ==========================================
    def nod(self):
        """点头 (肯定/倾听)"""
        print("[ACTION] 机器人点头")
        # HeadPitch: 负数抬头，正数低头。说明书中极值 -39 到 39 度
        angle_down = math.radians(20)  # 低头 20 度
        angle_up = math.radians(-10)  # 抬头 10 度

        # 动作序列：低头 -> 抬头 -> 回正
        self.motion.angleInterpolation(
            ["HeadPitch"],
            [[angle_down, angle_up, 0.0]],
            [[0.3, 0.6, 0.9]],  # 时间轴(秒)
            True
        )
        return True

    def shake_head(self):
        """摇头 (否定/高压表现)"""
        print("[ACTION] 机器人摇头")
        # HeadYaw: 左正右负
        angle_left = math.radians(30)
        angle_right = math.radians(-30)

        self.motion.angleInterpolation(
            ["HeadYaw"],
            [[angle_left, angle_right, 0.0]],
            [[0.4, 0.8, 1.2]],
            True
        )
        return True

    # ==========================================
    # 高压专属压迫模块 (视线与 LED)
    # ==========================================
    def stare_pressure(self):
        """压迫性死盯 (高压面试核心动作)"""
        print("[ACTION] 机器人开启压迫性死盯")
        # 1. 头部微微下压(更具攻击性)，死死盯住正前方
        self.motion.setAngles(["HeadYaw", "HeadPitch"], [0.0, math.radians(15)], 0.2)
        # 2. 眼睛 LED 变红 (参数: 模块, R, G, B, 渐变时间)
        self.leds.fadeRGB("FaceLeds", 1.0, 0.0, 0.0, 0.5)
        return True

    def avert_gaze(self):
        """回避视线 (高压表现：展现不耐烦或冷漠)"""
        print("[ACTION] 机器人回避视线 (不耐烦)")
        # 头部转向右侧且低垂
        yaw_angle = math.radians(-45)  # 向右转 45 度
        pitch_angle = math.radians(20)  # 低头 20 度
        self.motion.setAngles(["HeadYaw", "HeadPitch"], [yaw_angle, pitch_angle], 0.2)
        # 眼睛 LED 变暗蓝
        self.leds.fadeRGB("FaceLeds", 0.0, 0.0, 0.5, 0.5)
        return True

    def reset_gaze(self):
        """恢复正常视线与状态"""
        print("[ACTION] 机器人恢复正常视线")
        self.motion.setAngles(["HeadYaw", "HeadPitch"], [0.0, 0.0], 0.2)
        # 眼睛恢复默认白色
        self.leds.fadeRGB("FaceLeds", 1.0, 1.0, 1.0, 0.5)
        return True


# 简单测试代码（如果直接运行此文件）
if __name__ == '__main__':
    # 注意：如果没连上机器人，这里会报错并退出，这是正常的！
    controller = NaoBehaviorController(ip="192.168.93.152")
    controller.stare_pressure()
    time.sleep(2)
    controller.shake_head()
    controller.speak("你的回答没有逻辑")
    controller.reset_gaze()
    controller.rest()
