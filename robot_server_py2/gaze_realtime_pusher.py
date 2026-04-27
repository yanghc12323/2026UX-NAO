# -*- coding: utf-8 -*-
"""NAO 实时视线追踪推送器（Python2.7 + NAOqi SDK）

功能：
1. 使用 NAO 的摄像头和人脸检测模块进行实时视线追踪
2. 计算用户注视机器人头部的时长
3. 将追踪结果通过 HTTP POST 推送到 Python3 客户端

依赖：
- Python 2.7
- NAOqi SDK (pynaoqi)
- 标准库：json, time, urllib2

使用方法：
    python gaze_realtime_pusher.py --robot-ip 192.168.93.152 --client-url http://127.0.0.1:8765/gaze

作者：NAO Interview Coach Team
日期：2026-04-25
"""

from __future__ import print_function

# -*- coding: utf-8 -*-
import sys
import __builtin__ as _builtin

# 【你需要补充的代码：终结中文乱码】
reload(sys)
sys.setdefaultencoding('utf-8')


def _to_unicode_text(value):
    """将任意对象稳健转换为 unicode（避免控制台编码异常）。"""
    if isinstance(value, unicode):
        return value
    if isinstance(value, str):
        try:
            return value.decode('utf-8')
        except Exception:
            try:
                return value.decode('gbk')
            except Exception:
                return value.decode('utf-8', 'replace')
    try:
        return unicode(value)
    except Exception:
        return unicode(str(value), errors='replace')


def print(*args, **kwargs):
    """覆盖模块内 print：在 PowerShell/cmd 下都尽量不因中文日志崩溃。"""
    sep = kwargs.get('sep', ' ')
    end = kwargs.get('end', '\n')
    stream = kwargs.get('file', sys.stdout) or sys.stdout

    text = _to_unicode_text(sep).join([_to_unicode_text(a) for a in args]) + _to_unicode_text(end)
    encoding = getattr(stream, 'encoding', None) or 'mbcs'
    try:
        stream.write(text.encode(encoding, 'replace'))
    except Exception:
        try:
            stream.write(text.encode('utf-8', 'replace'))
        except Exception:
            _builtin.print('[WARN] console_write_failed')

# 【你需要补充的代码：强制指向你的 32位 SDK 路径】
# 注意：请确保这个路径和你 command_server 里用的一模一样
sys.path.insert(0, r"C:\Python27\Lib\site-packages") 


import sys
import time
import json
import urllib2
import argparse
from naoqi import ALProxy, ALBroker, ALModule

# ============================================================================
# 全局变量（用于 NAOqi 回调机制）
# ============================================================================
GAZE_MODULE_NAME = "GazeRealtimePusher"
gaze_pusher_instance = None


# ============================================================================
# NAOqi 回调模块
# ============================================================================
class GazeRealtimePusher(ALModule):
    """NAOqi 视线追踪回调模块

    设计说明：
    - 使用 NAO 的 ALFaceDetection 模块检测人脸
    - 通过人脸位置和大小估算用户是否在注视机器人
    - 定期统计注视时长并推送到 Python3 客户端

    注视判定逻辑：
    - 检测到人脸 + 人脸在中心区域 + 人脸大小适中 = 注视
    - 中心区域：图像中心 ±30% 范围
    - 人脸大小：宽度占图像 15%-60% 范围
    """

    def __init__(self, name, robot_ip, robot_port, client_url, current_stage):
        """初始化 Gaze 推送器

        Args:
            name: 模块名称（必须全局唯一）
            robot_ip: NAO 机器人 IP
            robot_port: NAO 机器人端口
            client_url: Python3 客户端接收 URL（如 http://127.0.0.1:8765/gaze）
            current_stage: 当前实验阶段
        """
        ALModule.__init__(self, name)

        self.robot_ip = robot_ip
        self.robot_port = robot_port
        self.client_url = client_url
        self.current_stage = current_stage

        # 连接到 NAO 的服务
        try:
            self.face_detection = ALProxy("ALFaceDetection", robot_ip, robot_port)
            self.memory_proxy = ALProxy("ALMemory", robot_ip, robot_port)
            print("[INFO] 成功连接到 NAO 人脸检测服务")
        except Exception as e:
            print("[ERROR] 连接 NAO 失败: %s" % str(e))
            sys.exit(1)

        # 配置人脸检测
        self._setup_face_detection()

        # 订阅人脸检测事件
        self.memory_proxy.subscribeToEvent(
            "FaceDetected",
            GAZE_MODULE_NAME,
            "onFaceDetected"
        )
        print("[INFO] 已订阅 FaceDetected 事件")

        # 注视追踪状态
        self.is_gazing = False
        self.gaze_start_time = 0
        self.total_gaze_time_s = 0.0
        self.last_face_time = 0
        self.face_timeout_s = 1.0  # 超过1秒未检测到人脸则认为不再注视

        # 推送控制
        self.push_interval_s = 2.0  # 每2秒推送一次
        self.last_push_time = 0

        # 统计信息
        self.detection_count = 0
        self.gaze_count = 0
        self.push_success_count = 0
        self.push_fail_count = 0

    def _setup_face_detection(self):
        """配置人脸检测参数"""
        try:
            # 设置检测周期（毫秒）
            self.face_detection.setParameter("Period", 200)  # 每200ms检测一次

            # 启用人脸追踪
            self.face_detection.setTrackingEnabled(True)

            print("[INFO] 人脸检测配置完成")

        except Exception as e:
            print("[WARN] 人脸检测配置失败: %s" % str(e))

    def onFaceDetected(self, key, value, message):
        """人脸检测回调函数（NAOqi 自动调用）

        Args:
            key: 事件键名（固定为 "FaceDetected"）
            value: 检测结果，包含人脸信息
            message: 附加消息

        value 结构示例：
        [
            [TimeStamp, [FaceInfo1, FaceInfo2, ...], CameraPose_InTorsoFrame, CameraPose_InRobotFrame, CurrentCameraName],
            ...
        ]

        FaceInfo 结构：
        [ShapeInfo, ExtraInfo]
        ShapeInfo: [0, alpha, beta, sizeX, sizeY]
            - alpha: 人脸中心相对图像中心的水平角度（弧度）
            - beta: 人脸中心相对图像中心的垂直角度（弧度）
            - sizeX: 人脸宽度（归一化，0-1）
            - sizeY: 人脸高度（归一化，0-1）
        """
        try:
            current_time = time.time()
            self.detection_count += 1

            # 解析检测结果
            if not value or len(value) == 0:
                self._update_gaze_state(False, current_time)
                return

            # 获取最新的检测结果
            latest_detection = value[0]
            if len(latest_detection) < 2:
                self._update_gaze_state(False, current_time)
                return

            face_info_list = latest_detection[1]
            if not face_info_list or len(face_info_list) == 0:
                self._update_gaze_state(False, current_time)
                return

            # 取第一个检测到的人脸（假设只有一个被试）
            face_info = face_info_list[0]
            if len(face_info) < 1:
                self._update_gaze_state(False, current_time)
                return

            shape_info = face_info[0]
            if len(shape_info) < 5:
                self._update_gaze_state(False, current_time)
                return

            # 提取人脸参数
            alpha = shape_info[1]  # 水平角度（弧度）
            beta = shape_info[2]  # 垂直角度（弧度）
            size_x = shape_info[3]  # 宽度（归一化）
            size_y = shape_info[4]  # 高度（归一化）

            # 判断是否为注视状态
            is_gazing = self._is_gazing(alpha, beta, size_x, size_y)
            self._update_gaze_state(is_gazing, current_time)

            if is_gazing:
                self.gaze_count += 1
                if self.gaze_count % 10 == 0:  # 每10次打印一次
                    print("[DEBUG] 注视中: alpha=%.2f beta=%.2f size_x=%.2f" % (
                        alpha, beta, size_x
                    ))

        except Exception as e:
            print("[ERROR] 回调处理异常: %s" % str(e))

    def _is_gazing(self, alpha, beta, size_x, size_y):
        """判断是否为注视状态

        Args:
            alpha: 水平角度（弧度）
            beta: 垂直角度（弧度）
            size_x: 人脸宽度（归一化）
            size_y: 人脸高度（归一化）

        Returns:
            bool: 是否为注视状态
        """
        # 角度阈值（弧度）
        # ±0.5 弧度 ≈ ±28.6 度
        alpha_threshold = 0.5
        beta_threshold = 0.5

        # 人脸大小阈值（归一化）
        # 太小：距离太远或不是正面
        # 太大：距离太近
        min_size_x = 0.15
        max_size_x = 0.60

        # 判断人脸是否在中心区域
        in_center = (abs(alpha) < alpha_threshold and
                     abs(beta) < beta_threshold)

        # 判断人脸大小是否合适
        size_ok = (min_size_x < size_x < max_size_x)

        return in_center and size_ok

    def _update_gaze_state(self, is_gazing, current_time):
        """更新注视状态并累计时长

        Args:
            is_gazing: 当前是否为注视状态
            current_time: 当前时间戳
        """
        # 检查是否超时（未检测到人脸）
        if not is_gazing:
            if self.is_gazing and (current_time - self.last_face_time) > self.face_timeout_s:
                # 结束注视
                if self.gaze_start_time > 0:
                    duration = self.last_face_time - self.gaze_start_time
                    self.total_gaze_time_s += duration
                self.is_gazing = False
                self.gaze_start_time = 0
            return

        # 更新最后检测到人脸的时间
        self.last_face_time = current_time

        # 开始新的注视
        if not self.is_gazing:
            self.is_gazing = True
            self.gaze_start_time = current_time

    def update_and_push(self):
        """更新注视时长并推送到客户端

        说明：
        - 由主循环定期调用
        - 计算当前累计的注视时长
        - 推送到 Python3 客户端
        """
        current_time = time.time()

        # 检查是否需要推送
        if (current_time - self.last_push_time) < self.push_interval_s:
            return

        # 计算总注视时长
        total_gaze_s = self.total_gaze_time_s
        if self.is_gazing and self.gaze_start_time > 0:
            # 加上当前正在进行的注视时长
            current_gaze_duration = current_time - self.gaze_start_time
            total_gaze_s += current_gaze_duration

        # 构造推送数据
        payload = {
            "gaze_contact_s": total_gaze_s,
            "stage": self.current_stage,
            "timestamp_ms": int(current_time * 1000)
        }

        # 推送到 Python3 客户端
        success = self._push_to_client(payload)

        # 更新推送时间
        self.last_push_time = current_time

        # 更新统计
        if success:
            self.push_success_count += 1
            print("[SUCCESS] 推送成功: gaze_contact_s=%.2f stage=%s" % (
                total_gaze_s, self.current_stage
            ))
        else:
            self.push_fail_count += 1
            print("[ERROR] 推送失败")

    def _push_to_client(self, payload):
        """推送数据到 Python3 客户端

        Args:
            payload: 要推送的数据字典

        Returns:
            bool: 推送是否成功
        """
        try:
            # 序列化为 JSON
            json_data = json.dumps(payload, ensure_ascii=False).encode('utf-8')

            # 构造 HTTP 请求
            request = urllib2.Request(
                self.client_url,
                data=json_data,
                headers={
                    'Content-Type': 'application/json; charset=utf-8',
                    'Content-Length': str(len(json_data))
                }
            )

            # 发送请求（超时 2 秒）
            response = urllib2.urlopen(request, timeout=2.0)
            response_body = response.read()

            # 检查响应
            response_data = json.loads(response_body)
            if response_data.get("ok"):
                return True
            else:
                print("[WARN] 客户端返回错误: %s" % response_body)
                return False

        except urllib2.URLError as e:
            print("[ERROR] HTTP 请求失败: %s" % str(e))
            return False
        except Exception as e:
            print("[ERROR] 推送异常: %s" % str(e))
            return False

    def set_stage(self, stage):
        """更新当前实验阶段

        Args:
            stage: 新的阶段名称

        说明：
        - 切换阶段时重置注视时长统计
        """
        old_stage = self.current_stage
        self.current_stage = stage

        # 重置注视统计
        self.total_gaze_time_s = 0.0
        self.is_gazing = False
        self.gaze_start_time = 0

        print("[INFO] 阶段切换: %s -> %s (注视统计已重置)" % (old_stage, stage))

    def start_detection(self):
        """启动人脸检测"""
        try:
            self.face_detection.subscribe(GAZE_MODULE_NAME)
            print("[INFO] 人脸检测已启动")
        except Exception as e:
            print("[ERROR] 启动检测失败: %s" % str(e))

    def stop_detection(self):
        """停止人脸检测"""
        try:
            self.face_detection.unsubscribe(GAZE_MODULE_NAME)
            print("[INFO] 人脸检测已停止")
        except Exception as e:
            print("[ERROR] 停止检测失败: %s" % str(e))

    def print_statistics(self):
        """打印统计信息"""
        print("\n" + "=" * 60)
        print("Gaze 推送器统计信息")
        print("=" * 60)
        print("人脸检测次数: %d" % self.detection_count)
        print("注视检测次数: %d" % self.gaze_count)
        print("推送成功: %d" % self.push_success_count)
        print("推送失败: %d" % self.push_fail_count)
        print("总注视时长: %.2f 秒" % self.total_gaze_time_s)
        if self.push_success_count + self.push_fail_count > 0:
            success_rate = float(self.push_success_count) / (self.push_success_count + self.push_fail_count) * 100
            print("推送成功率: %.1f%%" % success_rate)
        print("=" * 60 + "\n")


# ============================================================================
# 主程序
# ============================================================================
def main():
    """主函数"""
    global gaze_pusher_instance

    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="NAO 实时视线追踪推送器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 基本用法
  python gaze_realtime_pusher.py --robot-ip 192.168.93.152

  # 指定客户端 URL
  python gaze_realtime_pusher.py --robot-ip 192.168.93.152 --client-url http://127.0.0.1:8765/gaze

  # 指定初始阶段
  python gaze_realtime_pusher.py --robot-ip 192.168.93.152 --stage formal_interview

  # 调整推送频率
  python gaze_realtime_pusher.py --robot-ip 192.168.93.152 --push-interval 1.0
        """
    )

    parser.add_argument(
        "--robot-ip",
        type=str,
        required=True,
        help="NAO 机器人 IP 地址"
    )

    parser.add_argument(
        "--robot-port",
        type=int,
        default=9559,
        help="NAO 机器人端口（默认: 9559）"
    )

    parser.add_argument(
        "--client-url",
        type=str,
        default="http://127.0.0.1:8765/gaze",
        help="Python3 客户端接收 URL（默认: http://127.0.0.1:8765/gaze）"
    )

    parser.add_argument(
        "--stage",
        type=str,
        default="warmup",
        help="初始实验阶段（默认: warmup）"
    )

    parser.add_argument(
        "--push-interval",
        type=float,
        default=2.0,
        help="推送间隔（秒，默认: 2.0）"
    )

    parser.add_argument(
        "--broker-ip",
        type=str,
        default="0.0.0.0",
        help="本地 Broker IP（默认: 0.0.0.0）"
    )

    parser.add_argument(
        "--broker-port",
        type=int,
        default=0,
        help="本地 Broker 端口（默认: 0 表示自动分配）"
    )

    args = parser.parse_args()

    # 打印配置信息
    print("\n" + "=" * 60)
    print("NAO 实时视线追踪推送器")
    print("=" * 60)
    print("NAO 机器人: %s:%d" % (args.robot_ip, args.robot_port))
    print("客户端 URL: %s" % args.client_url)
    print("初始阶段: %s" % args.stage)
    print("推送间隔: %.1f 秒" % args.push_interval)
    print("=" * 60 + "\n")

    # 创建本地 Broker（NAOqi 要求）
    try:
        broker = ALBroker(
            "GazePusherBroker",
            args.broker_ip,
            args.broker_port,
            args.robot_ip,
            args.robot_port
        )
        print("[INFO] 本地 Broker 已创建")
    except Exception as e:
        print("[ERROR] 创建 Broker 失败: %s" % str(e))
        sys.exit(1)

    # 创建 Gaze 推送器实例
    try:
        gaze_pusher_instance = GazeRealtimePusher(
            GAZE_MODULE_NAME,
            args.robot_ip,
            args.robot_port,
            args.client_url,
            args.stage
        )
        gaze_pusher_instance.push_interval_s = args.push_interval
        print("[INFO] Gaze 推送器已创建")
    except Exception as e:
        print("[ERROR] 创建推送器失败: %s" % str(e))
        broker.shutdown()
        sys.exit(1)

    # 启动人脸检测
    gaze_pusher_instance.start_detection()

    # 主循环
    print("\n[INFO] 推送器运行中... 按 Ctrl+C 停止\n")
    try:
        while True:
            time.sleep(0.5)  # 每0.5秒检查一次
            gaze_pusher_instance.update_and_push()
    except KeyboardInterrupt:
        print("\n[INFO] 收到停止信号")

    # 清理资源
    print("[INFO] 正在清理资源...")
    gaze_pusher_instance.stop_detection()
    gaze_pusher_instance.print_statistics()
    broker.shutdown()
    print("[INFO] 推送器已停止")


if __name__ == "__main__":
    main()
