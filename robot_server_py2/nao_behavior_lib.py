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
    def __init__(self, ip="172.20.10.4", port=9559):
        """初始化代理，直连物理机器人"""
        self.ip = ip
        self.port = port

        # NOTE: 在部分 Windows + Python2 控制台环境下，中文 print 可能触发 IOError: [Errno 0]
        # 这里统一使用 ASCII 日志，避免连接前就因编码问题崩溃。
        print("[INFO] connecting to robot: %s:%s ..." % (ip, port))
        try:
            self.tts = ALProxy("ALTextToSpeech", ip, port)
            self.motion = ALProxy("ALMotion", ip, port)
            self.posture = ALProxy("ALRobotPosture", ip, port)
            self.leds = ALProxy("ALLeds", ip, port)
            self.audio = ALProxy("ALAudioDevice", ip, port)

            # 基础设置：中文、唤醒、初始站姿
            self.tts.setLanguage("Chinese")
            # 强制提高音量，避免“命令成功但听不到声音”。
            try:
                self.audio.setOutputVolume(90)
            except Exception as e:
                print("[WARNING] setOutputVolume failed: %s" % str(e))

            try:
                # 语音参数兜底，确保音量/语速在可听范围。
                self.tts.setParameter("volume", 1.0)
                self.tts.setParameter("speed", 90.0)
            except Exception as e:
                print("[WARNING] set TTS params failed: %s" % str(e))

            self.motion.wakeUp()
            self.posture.goToPosture("StandInit", 0.5)  # 标准站姿，保证重心稳定
            print("[INFO] robot connected. ready for interview commands.")
        except Exception as e:
            print("[ERROR] failed to connect robot (check IP/network/SDK): %s" % str(e))
            raise

    def _fade_face_led_safe(self, r, g, b, duration):
        """兼容不同 NAOqi 版本的 ALLeds.fadeRGB 签名差异，避免因 LED 调用导致动作整体失败。"""
        try:
            # 常见签名之一：fadeRGB(name, r, g, b, duration)
            self.leds.fadeRGB("FaceLeds", float(r), float(g), float(b), float(duration))
            return True
        except Exception as e1:
            try:
                # 另一常见签名：fadeRGB(name, colorHex, duration)
                rr = max(0, min(255, int(round(float(r) * 255))))
                gg = max(0, min(255, int(round(float(g) * 255))))
                bb = max(0, min(255, int(round(float(b) * 255))))
                color = (rr << 16) | (gg << 8) | bb
                self.leds.fadeRGB("FaceLeds", color, float(duration))
                return True
            except Exception as e2:
                print("[WARNING] fadeRGB failed on both signatures: %s | %s" % (str(e1), str(e2)))
                return False

    # ==========================================
    # 基础交互模块
    # ==========================================
    def speak(self, text):
        """说话"""
        if text:
            print("[ACTION] 机器人正在说话: %s" % text)
            # 再次兜底设置音量，避免运行中被外部流程改小。
            try:
                self.audio.setOutputVolume(90)
            except Exception:
                pass
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

    def think_chin(self):
        """摸下巴思考动作（真实动作）：右手抬至下巴附近并短暂停留后回位"""
        print("[ACTION] 机器人执行摸下巴思考动作")
        names = [
            "HeadYaw", "HeadPitch",
            "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw"
        ]
        # 说明：NAO无“手触碰”传感闭环，采用稳定可见的关节插值近似“摸下巴”动作。
        # 阶段1：抬手靠近下巴；阶段2：短暂停留；阶段3：回到中位。
        # 关键可调参数含义：
        # - ShoulderPitch: 数值越小，手臂越向前上方抬起（更接近下巴）
        # - ShoulderRoll: 右臂建议在负小角度，避免手偏到身体外侧
        # - ElbowRoll: 数值越大，肘部弯曲越明显（手更容易贴近下巴）
        # - ElbowYaw/WristYaw: 控制前臂与手腕朝向，决定“摸下巴”的贴合感
        angles = [
            [0.0, 0.0, 0.0],
            [math.radians(8), math.radians(12), 0.0],
            # RShoulderPitch: 下垂位 -> 靠近下巴 -> 回位
            [math.radians(55), math.radians(18), math.radians(80)],
            # RShoulderRoll: 轻微外展，避免手偏太外
            [math.radians(-12), math.radians(0), 0.0],
            # RElbowYaw: 前臂旋转，帮助手心朝向下巴
            [math.radians(80), math.radians(100), 0.0],
            # RElbowRoll: 肘部充分弯曲，进一步靠近下巴
            [math.radians(78), math.radians(86), math.radians(5)],
            # RWristYaw: 手腕内旋，增强“摸下巴”贴合感
            [math.radians(45), math.radians(80), 0.0],
        ]
        times = [[0.7, 1.6, 2.6] for _ in names]
        self.motion.angleInterpolation(names, angles, times, True)
        return True

    def arms_crossed(self):
        """抱胸动作（优化版）：从自然下垂位直接抱胸，短停后直接回到自然下垂。"""
        print("[ACTION] 机器人执行抱胸动作")
        names = [
            "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll",
            "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll",
            "HeadPitch"
        ]
        # 目标：避免“先抬手再放下再抱胸”的违和路径。
        # 直接两段：
        #   t1 进入抱胸姿态
        #   t2 回到自然下垂位
        angles = [
            # Left arm
            [math.radians(28), math.radians(80)],
            [math.radians(24), math.radians(10)],
            [math.radians(-20), math.radians(-70)],
            [math.radians(-78), math.radians(-5)],
            # Right arm
            [math.radians(28), math.radians(80)],
            [math.radians(-24), math.radians(-10)],
            [math.radians(20), math.radians(70)],
            [math.radians(78), math.radians(5)],
            # Head
            [math.radians(6), 0.0],
        ]
        times = [[1.0, 2.2] for _ in names]
        self.motion.angleInterpolation(names, angles, times, True)
        return True

    def hands_on_hips(self):
        """叉腰动作（优化版）：从自然下垂位直接叉腰，短停后直接回位。"""
        print("[ACTION] 机器人执行叉腰动作")
        names = [
            "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll",
            "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll",
            "HeadPitch"
        ]
        # 目标：避免“先举臂再落下再叉腰”的中间轨迹。
        # 直接两段：
        #   t1 到达叉腰位
        #   t2 回到自然下垂
        # 关键可调参数含义：
        # - ShoulderPitch: 越小手臂越前抬，越大越靠下；叉腰通常在 40~55°
        # - ShoulderRoll: 控制手臂向身体侧面张开幅度（左右对称正负）
        # - ElbowYaw: 控制上臂内旋/外旋，影响“手是否贴到髋侧”
        # - ElbowRoll: 控制肘弯曲程度，过小像直臂，过大像抱胸
        # - times: 第一段为到位速度，第二段为回位时机（停留时长=第二段-第一段）
        angles = [
            # Left arm
            [math.radians(48), math.radians(80)],
            [math.radians(16), math.radians(12)],
            [math.radians(-32), math.radians(-70)],
            [math.radians(-36), math.radians(-5)],
            # Right arm
            [math.radians(48), math.radians(80)],
            [math.radians(-16), math.radians(-12)],
            [math.radians(32), math.radians(70)],
            [math.radians(36), math.radians(5)],
            # Head
            [math.radians(4), 0.0],
        ]
        times = [[0.9, 2.0] for _ in names]
        self.motion.angleInterpolation(names, angles, times, True)
        return True

    # ==========================================
    # 高压专属压迫模块 (视线与 LED)
    # ==========================================
    def stare_pressure(self):
        """压迫性死盯 (高压面试核心动作)"""
        print("[ACTION] 机器人开启压迫性死盯")
        # 1) 头部微微下压(更具攻击性)，死死盯住正前方
        try:
            self.motion.setAngles(["HeadYaw", "HeadPitch"], [0.0, math.radians(15)], 0.2)
        except Exception as e:
            print("[WARNING] stare setAngles failed: %s" % str(e))
        # 2) LED 变红（兼容不同 NAOqi 签名）
        self._fade_face_led_safe(1.0, 0.0, 0.0, 0.5)
        return True

    def avert_gaze(self):
        """回避视线 (高压表现：展现不耐烦或冷漠)"""
        print("[ACTION] 机器人回避视线 (不耐烦)")
        # 头部转向右侧且低垂
        yaw_angle = math.radians(-45)  # 向右转 45 度
        pitch_angle = math.radians(20)  # 低头 20 度
        try:
            self.motion.setAngles(["HeadYaw", "HeadPitch"], [yaw_angle, pitch_angle], 0.2)
        except Exception as e:
            print("[WARNING] avert_gaze setAngles failed: %s" % str(e))
        # 眼睛 LED 变暗蓝
        self._fade_face_led_safe(0.0, 0.0, 0.5, 0.5)
        return True

    def reset_gaze(self):
        """恢复正常视线与状态"""
        print("[ACTION] 机器人恢复正常视线")
        try:
            self.motion.setAngles(["HeadYaw", "HeadPitch"], [0.0, 0.0], 0.2)
        except Exception as e:
            print("[WARNING] reset_gaze setAngles failed: %s" % str(e))
        # 眼睛恢复默认白色
        self._fade_face_led_safe(1.0, 1.0, 1.0, 0.5)
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
