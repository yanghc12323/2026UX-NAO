# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import json
import threading
import uuid
from dataclasses import dataclass, field
from typing import Dict, List
from urllib import request


def _build_multipart(fields, files, boundary):
    lines = []
    for k, v in fields.items():
        lines.append("--%s" % boundary)
        lines.append('Content-Disposition: form-data; name="%s"' % k)
        lines.append("")
        lines.append(str(v))
    for name, filename, content_type, content in files:
        lines.append("--%s" % boundary)
        lines.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (name, filename))
        lines.append("Content-Type: %s" % content_type)
        lines.append("")
        head = "\r\n".join(lines).encode("utf-8") + b"\r\n"
        tail = b"\r\n"
        lines = []
        body = head + content + tail
    end = ("--%s--\r\n" % boundary).encode("utf-8")
    if lines:
        body = "\r\n".join(lines).encode("utf-8") + b"\r\n" + end
    else:
        body = body + end
    return body


@dataclass
class AsrConfig:
    api_base: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "whisper-1"
    language: str = "zh"


@dataclass
class AsrRuntime:
    running: bool = False
    transcript: List[dict] = field(default_factory=list)


class AsrService(object):
    def __init__(self):
        self._lock = threading.RLock()
        self._cfg = AsrConfig()
        self._rt = AsrRuntime()

    def update_config(self, data: Dict) -> Dict:
        with self._lock:
            self._cfg.api_base = str(data.get("api_base", self._cfg.api_base)).rstrip("/")
            self._cfg.api_key = str(data.get("api_key", self._cfg.api_key)).strip()
            self._cfg.model = str(data.get("model", self._cfg.model)).strip() or "whisper-1"
            self._cfg.language = str(data.get("language", self._cfg.language)).strip() or "zh"
            return self.status()

    def start(self) -> Dict:
        with self._lock:
            self._rt.running = True
            self._rt.transcript = []
            return self.status()

    def stop(self) -> Dict:
        with self._lock:
            self._rt.running = False
            return self.status()

    def status(self) -> Dict:
        with self._lock:
            return {
                "ok": True,
                "running": self._rt.running,
                "config": {
                    "api_base": self._cfg.api_base,
                    "api_key_set": bool(self._cfg.api_key),
                    "model": self._cfg.model,
                    "language": self._cfg.language,
                },
                "transcript": list(self._rt.transcript[-100:]),
                "transcript_text": "\n".join([x.get("text", "") for x in self._rt.transcript]),
            }

    def accept_chunk(self, audio_base64: str, mime_type: str = "audio/webm") -> Dict:
        with self._lock:
            if not self._rt.running:
                return {"ok": False, "error": "asr_not_running"}
            cfg = AsrConfig(
                api_base=self._cfg.api_base,
                api_key=self._cfg.api_key,
                model=self._cfg.model,
                language=self._cfg.language,
            )
        if not cfg.api_key:
            return {"ok": False, "error": "api_key_required"}

        audio_bytes = base64.b64decode(audio_base64)
        boundary = "----ClineBoundary%s" % uuid.uuid4().hex
        body = _build_multipart(
            fields={"model": cfg.model, "language": cfg.language, "response_format": "json"},
            files=[("file", "chunk.webm", mime_type, audio_bytes)],
            boundary=boundary,
        )
        url = cfg.api_base + "/audio/transcriptions"
        req = request.Request(
            url,
            data=body,
            headers={
                "Authorization": "Bearer %s" % cfg.api_key,
                "Content-Type": "multipart/form-data; boundary=%s" % boundary,
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = str(data.get("text", "")).strip()
            if text:
                with self._lock:
                    self._rt.transcript.append({"text": text})
            return {"ok": True, "text": text}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": "transcribe_failed", "reason": str(exc)}
