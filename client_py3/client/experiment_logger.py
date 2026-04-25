"""结构化实验日志（jsonl）。"""

import json
import os
import time
from typing import Any, Dict


class ExperimentLogger(object):
    """简单 JSONL 日志器。"""

    def __init__(self, session_id: str, enabled: bool = True, log_dir: str = "logs"):
        self.enabled = bool(enabled)
        self.session_id = session_id
        self.log_dir = log_dir
        self.file_path = os.path.join(self.log_dir, "session_%s.jsonl" % session_id)
        if self.enabled and not os.path.isdir(self.log_dir):
            os.makedirs(self.log_dir)

    def emit(self, event_type: str, data: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        payload = {
            "event_type": event_type,
            "timestamp_ms": int(time.time() * 1000),
        }
        payload.update(data)
        line = json.dumps(payload, ensure_ascii=False)
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def stage_event(self, session_id: str, stage: str, phase: str, meta: Dict[str, Any]) -> None:
        self.emit(
            "stage_event",
            {
                "session_id": session_id,
                "stage": stage,
                "phase": phase,
                "meta": dict(meta or {}),
            },
        )

    def metric_event(self, session_id: str, turn_id: str, stage: str, metrics: Dict[str, Any]) -> None:
        self.emit(
            "metric_event",
            {
                "session_id": session_id,
                "turn_id": turn_id,
                "stage": stage,
                "metrics": dict(metrics or {}),
            },
        )

    def action_event(
        self,
        session_id: str,
        stage: str,
        action: str,
        status: str,
        error_code: str,
        message: str,
        execution_ms: int,
    ) -> None:
        self.emit(
            "action_event",
            {
                "session_id": session_id,
                "stage": stage,
                "action": action,
                "status": status,
                "error_code": error_code,
                "message": message,
                "execution_ms": int(execution_ms),
            },
        )
