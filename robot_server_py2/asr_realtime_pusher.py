# -*- coding: utf-8 -*-
"""NAO 实时语音识别推送器（Python2.7 + NAOqi SDK）

功能：
1. 使用 NAO 的 ALSpeechRecognition 模块进行实时语音识别
2. 将识别结果通过 HTTP POST 推送到 Python3 客户端
3. 支持阶段标记，便于客户端匹配当前实验阶段

依赖：
- Python 2.7
- NAOqi SDK (pynaoqi)
- 标准库：json, time, urllib2

使用方法：
    python asr_realtime_pusher.py --robot-ip 192.168.93.152 --client-url http://127.0.0.1:8765/asr

作者：陶歌晴
日期：2026-04-25
"""

from __future__ import print_function

# -*- coding: utf-8 -*-
import sys
import __builtin__ as _builtin

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

import time
import json
import urllib2
import argparse
from naoqi import ALProxy, ALBroker, ALModule

# ============================================================================
# 全局变量（用于 NAOqi 回调机制）
# ============================================================================
ASR_MODULE_NAME = "ASRRealtimePusher"
asr_pusher_instance = None


# ============================================================================
# NAOqi 回调模块
# ============================================================================
class ASRRealtimePusher(ALModule):
    """NAOqi 语音识别回调模块

    设计说明：
    - NAOqi 的事件机制要求回调类继承 ALModule
    - 当识别到语音时，onWordRecognized 方法会被自动调用
    - 我们在回调中将结果推送到 Python3 客户端
    """

    def __init__(self, name, robot_ip, robot_port, client_url, current_stage):
        """初始化 ASR 推送器

        Args:
            name: 模块名称（必须全局唯一）
            robot_ip: NAO 机器人 IP
            robot_port: NAO 机器人端口
            client_url: Python3 客户端接收 URL（如 http://127.0.0.1:8765/asr）
            current_stage: 当前实验阶段（如 warmup, formal_interview）
        """
        ALModule.__init__(self, name)

        self.robot_ip = robot_ip
        self.robot_port = robot_port
        self.client_url = client_url
        self.current_stage = current_stage

        # 连接到 NAO 的语音识别服务
        try:
            self.asr_proxy = ALProxy("ALSpeechRecognition", robot_ip, robot_port)
            self.memory_proxy = ALProxy("ALMemory", robot_ip, robot_port)
            print("[INFO] 成功连接到 NAO 语音识别服务")
        except Exception as e:
            print("[ERROR] 连接 NAO 失败: %s" % str(e))
            sys.exit(1)

        # 配置语音识别
        self._setup_speech_recognition()

        # 订阅语音识别事件
        self.memory_proxy.subscribeToEvent(
            "WordRecognized",
            ASR_MODULE_NAME,
            "onWordRecognized"
        )
        print("[INFO] 已订阅 WordRecognized 事件")

        # 统计信息
        self.recognition_count = 0
        self.push_success_count = 0
        self.push_fail_count = 0
        self.last_recognition_time = 0

    def _setup_speech_recognition(self):
        """配置语音识别参数

        说明：
        - 设置语言为中文
        - 配置识别词汇表（可根据实验需求调整）
        - 设置识别灵敏度
        """
        try:
            # 设置语言为中文
            self.asr_proxy.setLanguage("Chinese")

            # 设置词汇表（开放式识别，不限定特定词汇）
            # 注意：NAO 的中文识别可能需要预定义词汇表
            # 如果需要开放式识别，可能需要使用 ALSoundExtractor
            vocabulary = [
                u"是的", u"不是", u"好的", u"明白", u"继续",
                u"项目", u"开发", u"团队", u"负责", u"完成",
                u"学习", u"经验", u"能力", u"挑战", u"解决"
            ]
            self.asr_proxy.setVocabulary(vocabulary, False)

            # 设置识别参数
            # AudioExpression: 0.0-1.0，越高越敏感
            self.asr_proxy.setAudioExpression(0.6)

            print("[INFO] 语音识别配置完成")
            print("[INFO] 词汇表大小: %d" % len(vocabulary))

        except Exception as e:
            print("[WARN] 语音识别配置失败: %s" % str(e))

    def onWordRecognized(self, key, value, message):
        """语音识别回调函数（NAOqi 自动调用）

        Args:
            key: 事件键名（固定为 "WordRecognized"）
            value: 识别结果 [word, confidence]
            message: 附加消息

        说明：
        - value 是一个列表，格式为 [识别文本, 置信度]
        - 置信度范围 0.0-1.0，越高表示越确定
        - 我们只处理置信度 > 0.3 的结果
        """
        try:
            # 解析识别结果
            if not value or len(value) < 2:
                return

            recognized_text = value[0]
            confidence = value[1]

            # 过滤低置信度结果
            if confidence < 0.3:
                print("[DEBUG] 置信度过低，忽略: text=%s confidence=%.2f" % (
                    recognized_text, confidence
                ))
                return

            # 计算语音时长（估算）
            current_time = time.time()
            if self.last_recognition_time > 0:
                speech_duration_s = current_time - self.last_recognition_time
            else:
                # 首次识别，根据文本长度估算
                speech_duration_s = max(1.0, len(recognized_text) * 0.3)

            self.last_recognition_time = current_time

            # 构造推送数据
            payload = {
                "text": recognized_text,
                "speech_duration_s": speech_duration_s,
                "confidence": confidence,
                "stage": self.current_stage,
                "timestamp_ms": int(current_time * 1000)
            }

            # 推送到 Python3 客户端
            success = self._push_to_client(payload)

            # 更新统计
            self.recognition_count += 1
            if success:
                self.push_success_count += 1
                print("[SUCCESS] 推送成功 #%d: text=%s confidence=%.2f stage=%s" % (
                    self.recognition_count, recognized_text, confidence, self.current_stage
                ))
            else:
                self.push_fail_count += 1
                print("[ERROR] 推送失败 #%d: text=%s" % (
                    self.recognition_count, recognized_text
                ))

        except Exception as e:
            print("[ERROR] 回调处理异常: %s" % str(e))

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
        """
        old_stage = self.current_stage
        self.current_stage = stage
        print("[INFO] 阶段切换: %s -> %s" % (old_stage, stage))

    def start_recognition(self):
        """启动语音识别"""
        try:
            self.asr_proxy.subscribe(ASR_MODULE_NAME)
            print("[INFO] 语音识别已启动")
        except Exception as e:
            print("[ERROR] 启动识别失败: %s" % str(e))

    def stop_recognition(self):
        """停止语音识别"""
        try:
            self.asr_proxy.unsubscribe(ASR_MODULE_NAME)
            print("[INFO] 语音识别已停止")
        except Exception as e:
            print("[ERROR] 停止识别失败: %s" % str(e))

    def print_statistics(self):
        """打印统计信息"""
        print("\n" + "=" * 60)
        print("ASR 推送器统计信息")
        print("=" * 60)
        print("识别次数: %d" % self.recognition_count)
        print("推送成功: %d" % self.push_success_count)
        print("推送失败: %d" % self.push_fail_count)
        if self.recognition_count > 0:
            success_rate = float(self.push_success_count) / self.recognition_count * 100
            print("成功率: %.1f%%" % success_rate)
        print("=" * 60 + "\n")


# ============================================================================
# 主程序
# ============================================================================
def main():
    """主函数"""
    global asr_pusher_instance

    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="NAO 实时语音识别推送器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 基本用法
  python asr_realtime_pusher.py --robot-ip 192.168.93.152

  # 指定客户端 URL
  python asr_realtime_pusher.py --robot-ip 192.168.93.152 --client-url http://127.0.0.1:8765/asr

  # 指定初始阶段
  python asr_realtime_pusher.py --robot-ip 192.168.93.152 --stage formal_interview
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
        default="http://127.0.0.1:8765/asr",
        help="Python3 客户端接收 URL（默认: http://127.0.0.1:8765/asr）"
    )

    parser.add_argument(
        "--stage",
        type=str,
        default="warmup",
        help="初始实验阶段（默认: warmup）"
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
    print("NAO 实时语音识别推送器")
    print("=" * 60)
    print("NAO 机器人: %s:%d" % (args.robot_ip, args.robot_port))
    print("客户端 URL: %s" % args.client_url)
    print("初始阶段: %s" % args.stage)
    print("=" * 60 + "\n")

    # 创建本地 Broker（NAOqi 要求）
    try:
        broker = ALBroker(
            "ASRPusherBroker",
            args.broker_ip,
            args.broker_port,
            args.robot_ip,
            args.robot_port
        )
        print("[INFO] 本地 Broker 已创建")
    except Exception as e:
        print("[ERROR] 创建 Broker 失败: %s" % str(e))
        sys.exit(1)

    # 创建 ASR 推送器实例
    try:
        asr_pusher_instance = ASRRealtimePusher(
            ASR_MODULE_NAME,
            args.robot_ip,
            args.robot_port,
            args.client_url,
            args.stage
        )
        print("[INFO] ASR 推送器已创建")
    except Exception as e:
        print("[ERROR] 创建推送器失败: %s" % str(e))
        broker.shutdown()
        sys.exit(1)

    # 启动语音识别
    asr_pusher_instance.start_recognition()

    # 主循环
    print("\n[INFO] 推送器运行中... 按 Ctrl+C 停止\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] 收到停止信号")

    # 清理资源
    print("[INFO] 正在清理资源...")
    asr_pusher_instance.stop_recognition()
    asr_pusher_instance.print_statistics()
    broker.shutdown()
    print("[INFO] 推送器已停止")


if __name__ == "__main__":
    main()
