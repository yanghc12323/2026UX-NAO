"""视觉 gaze 观测抽象层。

设计目标：
1. 将会话流程与具体视觉 SDK/模型解耦；
2. 支持 mock 回退，保证无设备环境可运行；
3. 提供 JSONL 桥接实现，便于与外部视觉进程集成。
"""

import json
import os
from typing import Optional, Protocol

from .realtime_bridge import RealtimeStreamBridge


class GazeProvider(Protocol):
    """视线观测接口。

    返回值含义：
    - ``None``: 当前无可用观测；
    - ``float``: 本轮回答中的视线接触时长（秒）。
    """

    def estimate_gaze_contact_s(self, stage: str, answer_text: str, speech_duration_s: float) -> Optional[float]:
        ...


class MockGazeProvider(object):
    """默认 mock 视线观测。"""

    def estimate_gaze_contact_s(self, stage: str, answer_text: str, speech_duration_s: float) -> Optional[float]:
        del stage, answer_text
        duration = max(0.1, float(speech_duration_s))
        return min(duration, duration * 0.62)


class JsonlGazeProvider(object):
    """基于 JSONL 文件的 gaze 适配器。

    每行示例：
    {
      "gaze_contact_s": 5.2,
      "stage": "formal_interview"
    }

    注意：默认按写入顺序逐条消费。
    """

    def __init__(self, jsonl_path: str):
        self.jsonl_path = jsonl_path
        self._line_cursor = 0

    def estimate_gaze_contact_s(self, stage: str, answer_text: str, speech_duration_s: float) -> Optional[float]:
        del answer_text, speech_duration_s
        if not self.jsonl_path or not os.path.isfile(self.jsonl_path):
            return None

        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if self._line_cursor >= len(lines):
            return None

        raw = lines[self._line_cursor].strip()
        self._line_cursor += 1
        if not raw:
            return None

        data = json.loads(raw)
        record_stage = str(data.get("stage", "")).strip()
        if record_stage and record_stage != stage:
            print("[WARN] gaze_stage_mismatch expected=%s got=%s" % (stage, record_stage))

        if "gaze_contact_s" not in data:
            return None

        value = float(data.get("gaze_contact_s", 0.0) or 0.0)
        return max(0.0, value)


class RealtimeGazeProvider(object):
    """基于实时桥接缓冲区的 gaze 适配器。"""

    def __init__(self, bridge: RealtimeStreamBridge, max_age_s: float = 2.0):
        self.bridge = bridge
        self.max_age_s = max(0.0, float(max_age_s))

    def estimate_gaze_contact_s(self, stage: str, answer_text: str, speech_duration_s: float) -> Optional[float]:
        del answer_text, speech_duration_s
        return self.bridge.get_latest_gaze(stage=stage, max_age_s=self.max_age_s)
