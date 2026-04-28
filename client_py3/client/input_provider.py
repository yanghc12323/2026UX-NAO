"""输入采集抽象层。

本模块负责“用户语音 -> 文本”的统一抽象，目标是：
1. 将会话流程与具体 ASR SDK 解耦；
2. 保留可运行的 mock 回退；
3. 提供一个低耦合的数据桥接实现（JSONL），便于和外部进程集成。
"""

from dataclasses import dataclass
from typing import Optional, Protocol
import json
import os
import time

from .realtime_bridge import RealtimeStreamBridge


@dataclass
class UserInputSample:
    """一次用户输入样本。"""

    text: str
    speech_duration_s: float
    gaze_contact_s: float
    source: str = "mock"
    timestamp_ms: int = 0


class ASRProvider(Protocol):
    """ASR 提供器接口（真实接入时实现该接口）。

    约定：
    - 返回 ``None`` 表示当前时刻无可用转写结果；
    - 返回 ``UserInputSample`` 表示成功采集到一次用户回答。
    """

    def transcribe_once(self, stage: str, prompt: str) -> Optional[UserInputSample]:
        ...


class SessionInputProvider(Protocol):
    """会话输入接口。"""

    def collect_answer(self, stage: str, prompt: str) -> UserInputSample:
        ...


class MockInputProvider(object):
    """默认 mock 输入，保证流程可运行。"""

    def collect_answer(self, stage: str, prompt: str) -> UserInputSample:
        if stage == "warmup":
            text = "大家好，我叫小王，目前是计算机专业大三学生。"
        elif stage == "formal_interview":
            text = "我在校园项目中负责后端开发，推进了接口重构并提升了稳定性，然后和团队完成上线。"
        else:
            text = "好的，我明白了。"

        duration_s = max(2.0, len(text) * 0.18)
        gaze_s = min(duration_s, duration_s * 0.62)
        return UserInputSample(
            text=text,
            speech_duration_s=duration_s,
            gaze_contact_s=gaze_s,
            source="mock",
            timestamp_ms=int(time.time() * 1000),
        )


class ASRFirstInputProvider(object):
    """优先调用 ASR，失败时回退 mock。"""

    def __init__(self, asr: Optional[ASRProvider] = None, fallback: Optional[SessionInputProvider] = None):
        self.asr = asr
        self.fallback = fallback or MockInputProvider()

    def collect_answer(self, stage: str, prompt: str) -> UserInputSample:
        if self.asr is not None:
            try:
                sample = self.asr.transcribe_once(stage=stage, prompt=prompt)
                if sample is not None and sample.text.strip():
                    if sample.timestamp_ms <= 0:
                        sample.timestamp_ms = int(time.time() * 1000)
                    return sample
            except Exception as exc:  # noqa: BLE001
                print("[WARN] asr_collect_failed stage=%s reason=%s" % (stage, exc))

        return self.fallback.collect_answer(stage=stage, prompt=prompt)


class JsonlASRProvider(object):
    """基于 JSONL 文件的 ASR 适配器。

    典型使用方式：
    - 外部 ASR 进程持续写入 JSONL；
    - 本适配器按顺序消费未读记录并映射为 ``UserInputSample``；
    - 若当前无新记录则返回 ``None``，由上层回退到 mock。

    JSONL 每行示例：
    {
      "text": "我在上一个项目中负责后端重构",
      "speech_duration_s": 8.3,
      "timestamp_ms": 1714012345678,
      "stage": "formal_interview"
    }
    """

    def __init__(self, jsonl_path: str, poll_timeout_s: float = 0.0, poll_interval_s: float = 0.1):
        self.jsonl_path = jsonl_path
        self._line_cursor = 0
        self.poll_timeout_s = max(0.0, float(poll_timeout_s))
        self.poll_interval_s = max(0.01, float(poll_interval_s))

    def transcribe_once(self, stage: str, prompt: str) -> Optional[UserInputSample]:
        del prompt  # 当前 JSONL 方案不依赖 prompt，预留给未来策略。

        deadline = time.time() + self.poll_timeout_s
        while True:
            sample = self._consume_one_matching_record(stage=stage)
            if sample is not None:
                return sample

            if self.poll_timeout_s <= 0:
                return None
            if time.time() >= deadline:
                return None

            time.sleep(self.poll_interval_s)

    def _consume_one_matching_record(self, stage: str) -> Optional[UserInputSample]:
        if not self.jsonl_path or not os.path.isfile(self.jsonl_path):
            return None

        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 从当前位置开始，找到首条“可用且 stage 匹配”的记录
        while self._line_cursor < len(lines):
            raw = lines[self._line_cursor].strip()
            self._line_cursor += 1
            if not raw:
                continue

            try:
                data = json.loads(raw)
            except Exception as exc:  # noqa: BLE001
                print("[WARN] asr_json_parse_failed reason=%s" % exc)
                continue

            text = str(data.get("text", "")).strip()
            if not text:
                print("[WARN] asr_empty_text_skipped")
                continue

            record_stage = str(data.get("stage", "")).strip()
            if record_stage and record_stage != stage:
                print("[WARN] asr_stage_mismatch_skipped expected=%s got=%s" % (stage, record_stage))
                continue

            duration_s = float(data.get("speech_duration_s", 0.0) or 0.0)
            if duration_s <= 0:
                duration_s = max(1.0, len(text) * 0.18)

            return UserInputSample(
                text=text,
                speech_duration_s=duration_s,
                gaze_contact_s=0.0,  # gaze 由独立视觉链路提供
                source="asr_jsonl",
                timestamp_ms=int(data.get("timestamp_ms", int(time.time() * 1000))),
            )

        return None


class RealtimeASRProvider(object):
    """基于实时桥接缓冲区的 ASR 适配器。"""

    def __init__(self, bridge: RealtimeStreamBridge, poll_timeout_s: float = 1.2, poll_interval_s: float = 0.1):
        self.bridge = bridge
        self.poll_timeout_s = max(0.0, float(poll_timeout_s))
        self.poll_interval_s = max(0.01, float(poll_interval_s))

    def transcribe_once(self, stage: str, prompt: str) -> Optional[UserInputSample]:
        del prompt

        deadline = time.time() + self.poll_timeout_s
        while True:
            record = self.bridge.pop_asr_record()
            if record is not None:
                sample = self._parse_record(stage=stage, data=record)
                if sample is not None:
                    return sample

            if self.poll_timeout_s <= 0:
                return None
            if time.time() >= deadline:
                return None

            time.sleep(self.poll_interval_s)

    def _parse_record(self, stage: str, data: dict) -> Optional[UserInputSample]:
        # 心跳包仅用于连通性保活，不应进入对话/指标链路。
        if bool(data.get("heartbeat", False)):
            return None

        text = str(data.get("text", "")).strip()
        if not text:
            print("[WARN] asr_empty_text_skipped")
            return None
        if text == "<heartbeat>":
            return None

        record_stage = str(data.get("stage", "")).strip()
        if record_stage and record_stage != stage:
            print("[WARN] asr_stage_mismatch_skipped expected=%s got=%s" % (stage, record_stage))
            return None

        duration_s = float(data.get("speech_duration_s", 0.0) or 0.0)
        if duration_s <= 0:
            duration_s = max(1.0, len(text) * 0.18)

        return UserInputSample(
            text=text,
            speech_duration_s=duration_s,
            gaze_contact_s=0.0,
            source="asr_realtime",
            timestamp_ms=int(data.get("timestamp_ms", int(time.time() * 1000))),
        )
