# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import struct
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, List

try:
    import websockets
except Exception:  # pragma: no cover
    websockets = None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _persona_prompt(condition_id: str) -> str:
    m = {
        "C1": "你是高人格化、反应式附和的NAO面试官。语气温暖、有同理心、适度鼓励，回答简洁自然（1-3句）。",
        "C2": "你是高人格化、最小附和的NAO面试官。语气友好但克制，减少附和词，回答简洁自然（1-3句）。",
        "C3": "你是低人格化、反应式附和的NAO面试官。语气中性偏正式，可少量附和，回答简洁直接（1-3句）。",
        "C4": "你是低人格化、最小附和的NAO面试官。语气简洁、正式、低情感，尽量短句（1-2句）。",
    }
    return m.get(condition_id, m["C1"])


@dataclass
class RealtimeConfig:
    enabled: bool = True
    provider: str = "doubao_realtime"
    # TODO(user): 填入豆包实时 API Key
    doubao_api_key: str = "3A0xkIeyG2lXx989umri2Cz3E3lGsEGb"
    # 官方文档：wss://openspeech.bytedance.com/api/v3/realtime/dialogue
    doubao_ws_url: str = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
    # TODO(user): 按官方文档填写 app/resource 标识（如不需要可留空）
    doubao_app_id: str = "1851125574"
    doubao_resource_id: str = ""
    audio_format: str = "pcm"
    sample_rate: int = 16000
    channels: int = 1
    enable_interim: bool = True


@dataclass
class RealtimeSession:
    session_id: str
    condition_id: str
    ws: object
    created_at_ms: int = field(default_factory=_now_ms)
    turn_id: int = 0
    history: Deque[Dict[str, str]] = field(default_factory=lambda: deque(maxlen=20))
    running_tasks: List[asyncio.Task] = field(default_factory=list)
    interrupted: bool = False
    current_reply: str = ""


class RealtimeDialogService(object):
    def __init__(self, speak_func: Callable[[str, str], dict], state_provider: Callable[[], dict]):
        self._cfg = RealtimeConfig()
        self._speak_func = speak_func
        self._state_provider = state_provider
        self._lock = threading.RLock()
        self._sessions: Dict[str, RealtimeSession] = {}

    def update_config(self, data: Dict) -> Dict:
        with self._lock:
            self._cfg.enabled = bool(data.get("enabled", self._cfg.enabled))
            # 新字段
            self._cfg.doubao_api_key = str(data.get("doubao_api_key", self._cfg.doubao_api_key)).strip()
            self._cfg.doubao_ws_url = str(data.get("doubao_ws_url", self._cfg.doubao_ws_url)).strip() or self._cfg.doubao_ws_url
            self._cfg.doubao_app_id = str(data.get("doubao_app_id", self._cfg.doubao_app_id)).strip()
            self._cfg.doubao_resource_id = str(data.get("doubao_resource_id", self._cfg.doubao_resource_id)).strip()
            self._cfg.audio_format = str(data.get("audio_format", self._cfg.audio_format)).strip() or "pcm"
            self._cfg.sample_rate = int(data.get("sample_rate", self._cfg.sample_rate) or 16000)
            self._cfg.channels = int(data.get("channels", self._cfg.channels) or 1)
            self._cfg.enable_interim = bool(data.get("enable_interim", self._cfg.enable_interim))

            # 兼容旧前端字段，避免页面未刷新时报错
            legacy_key = str(data.get("deepgram_api_key", "")).strip()
            legacy_url = str(data.get("deepgram_url", "")).strip()
            if legacy_key and not self._cfg.doubao_api_key:
                self._cfg.doubao_api_key = legacy_key
            if legacy_url and not data.get("doubao_ws_url"):
                self._cfg.doubao_ws_url = legacy_url
        return self.status()

    def status(self) -> Dict:
        with self._lock:
            return {
                "ok": True,
                "enabled": self._cfg.enabled,
                "provider": self._cfg.provider,
                "config": {
                    "doubao_key_set": bool(self._cfg.doubao_api_key),
                    "doubao_ws_url": self._cfg.doubao_ws_url,
                    "doubao_app_id": self._cfg.doubao_app_id,
                    "doubao_resource_id": self._cfg.doubao_resource_id,
                    "audio_format": self._cfg.audio_format,
                    "sample_rate": self._cfg.sample_rate,
                    "channels": self._cfg.channels,
                    "enable_interim": self._cfg.enable_interim,
                },
                "active_sessions": list(self._sessions.keys()),
            }

    async def handle_ws(self, ws, path):
        if path != "/ws/realtime-dialog":
            await ws.send(json.dumps({"type": "error", "message": "invalid_ws_path"}, ensure_ascii=False))
            await ws.close()
            return

        sid = "RT_%s" % uuid.uuid4().hex[:10]
        s = RealtimeSession(session_id=sid, condition_id="C1", ws=ws)
        with self._lock:
            self._sessions[sid] = s

        await ws.send(json.dumps({"type": "session", "session_id": sid}, ensure_ascii=False))
        try:
            await self._run_session(s)
        finally:
            await self._interrupt_session(s)
            with self._lock:
                self._sessions.pop(sid, None)

    async def _run_session(self, s: RealtimeSession):
        if websockets is None:
            await s.ws.send(json.dumps({"type": "error", "message": "websockets_package_required"}, ensure_ascii=False))
            return

        cfg = self._cfg
        if not cfg.doubao_api_key:
            await s.ws.send(json.dumps({"type": "error", "message": "doubao_api_key_required"}, ensure_ascii=False))
            await self._idle_until_client_close(s)
            return

        headers = {
            "X-Api-App-ID": cfg.doubao_app_id,
            "X-Api-Access-Key": cfg.doubao_api_key,
            "X-Api-Resource-Id": cfg.doubao_resource_id or "volc.speech.dialog",
            "X-Api-App-Key": "PlgvMymc7f3tQnJ6",
            "X-Api-Connect-Id": "CONN_%s" % uuid.uuid4().hex,
        }
        try:
            async with websockets.connect(cfg.doubao_ws_url, extra_headers=headers, ping_interval=20, ping_timeout=20) as db_ws:
                await self._send_event(db_ws, event_id=1, payload={})  # StartConnection
                await self._send_doubao_session_init(s, db_ws)
                sender = asyncio.create_task(self._pipe_user_to_doubao(s, db_ws))
                receiver = asyncio.create_task(self._pipe_doubao_to_user(s, db_ws))
                s.running_tasks.extend([sender, receiver])
                await asyncio.wait([sender, receiver], return_when=asyncio.FIRST_COMPLETED)
        except Exception as exc:  # noqa: BLE001
            await s.ws.send(json.dumps({"type": "error", "message": "doubao_realtime_failed:%s" % str(exc)}, ensure_ascii=False))
            await self._idle_until_client_close(s)

    async def _send_doubao_session_init(self, s: RealtimeSession, db_ws):
        cfg = self._cfg
        # 说明：该消息体按官方Realtime协议可能需调整字段名；这里给出可工作的占位骨架。
        init_msg = {
            "asr": {
                "audio_info": {
                    "format": "pcm",
                    "sample_rate": cfg.sample_rate,
                    "channel": cfg.channels,
                },
                "extra": {
                    "enable_asr_twopass": True,
                },
            },
            "tts": {
                "speaker": "zh_female_vv_jupiter_bigtts",
            },
            "dialog": {
                "bot_name": "NAO",
                "system_role": _persona_prompt(s.condition_id),
                "speaking_style": "简洁、礼貌、面试官风格",
                "dialog_context": [
                    {"role": x.get("role", "user"), "text": x.get("content", ""), "timestamp": _now_ms()}
                    for x in list(s.history)[-20:]
                ],
                "extra": {
                    "input_mod": "push_to_talk",
                    "enable_custom_vad": True,
                    "end_smooth_window_ms": 1200,
                    "strict_audit": False,
                    "model": "1.2.1.1",
                },
            },
        }
        await self._send_event(db_ws, event_id=100, payload=init_msg, session_id=s.session_id)  # StartSession

    async def _idle_until_client_close(self, s: RealtimeSession):
        async for msg in s.ws:
            if isinstance(msg, (bytes, bytearray)):
                continue
            try:
                obj = json.loads(msg)
            except Exception:
                continue
            t = str(obj.get("type", "")).lower()
            if t == "config":
                cid = str(obj.get("condition_id", "C1")).strip() or "C1"
                s.condition_id = cid
                await s.ws.send(json.dumps({"type": "ack", "message": "config_updated", "condition_id": cid}, ensure_ascii=False))

    async def _pipe_user_to_doubao(self, s: RealtimeSession, db_ws):
        async for msg in s.ws:
            if isinstance(msg, (bytes, bytearray)):
                await self._send_audio(db_ws, bytes(msg), session_id=s.session_id)
                continue

            try:
                obj = json.loads(msg)
            except Exception:
                continue

            t = str(obj.get("type", "")).lower()
            if t == "config":
                cid = str(obj.get("condition_id", "C1")).strip() or "C1"
                s.condition_id = cid
                await s.ws.send(json.dumps({"type": "ack", "message": "config_updated", "condition_id": cid}, ensure_ascii=False))
                continue

            if t == "interrupt":
                s.interrupted = True
                s.current_reply = ""
                # 不再取消主收发pipe，只通知上游执行打断
                await self._send_doubao_interrupt(db_ws)
                await s.ws.send(json.dumps({"type": "ack", "message": "interrupted"}, ensure_ascii=False))
                continue

            if t == "end_of_utterance":
                try:
                    await self._send_event(db_ws, event_id=400, payload={}, session_id=s.session_id)  # EndASR
                except Exception:
                    pass
                continue

    async def _send_doubao_interrupt(self, db_ws):
        try:
            await self._send_event(db_ws, event_id=515, payload={}, session_id="")
        except Exception:
            return

    async def _pipe_doubao_to_user(self, s: RealtimeSession, db_ws):
        async for raw in db_ws:
            if isinstance(raw, (bytes, bytearray)):
                parsed = self._decode_server_frame(bytes(raw))
                if parsed.get("kind") == "audio":
                    # 该项目用NAO本地TTS，不消费服务端音频
                    continue
                if parsed.get("kind") == "error":
                    await s.ws.send(json.dumps({"type": "error", "message": parsed.get("error", "unknown_error")}, ensure_ascii=False))
                    continue
                if parsed.get("kind") == "event":
                    await self._handle_doubao_event(s, parsed)
                continue
            # 兼容：若服务端/网关返回了文本JSON
            try:
                data = json.loads(raw)
                await self._handle_doubao_event(s, {"event_id": -1, "payload": data})
            except Exception:
                continue

    async def _handle_doubao_event(self, s: RealtimeSession, data: Dict):
        event_id = int(data.get("event_id", -1))
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}

        # 599 DialogCommonError
        if event_id == 599:
            msg = str(payload.get("message") or payload.get("error") or "dialog_common_error")
            await s.ws.send(json.dumps({"type": "error", "message": msg}, ensure_ascii=False))
            return

        # 451 ASRResponse
        if event_id == 451:
            for r in (payload.get("results") or []):
                txt = str((r or {}).get("text") or "").strip()
                if not txt:
                    continue
                interim = bool((r or {}).get("is_interim", False))
                await s.ws.send(json.dumps({
                    "type": "asr",
                    "text": txt,
                    "is_final": (not interim),
                    "speech_final": False,
                    "confidence": None,
                }, ensure_ascii=False))
                if not interim:
                    s.history.append({"role": "user", "content": txt})
            return

        # 459 ASREnded
        if event_id == 459:
            await s.ws.send(json.dumps({"type": "asr", "text": "", "is_final": True, "speech_final": True}, ensure_ascii=False))
            return

        # 550 ChatResponse
        if event_id == 550:
            delta = str(payload.get("content") or "")
            if delta:
                if not s.current_reply:
                    s.turn_id += 1
                s.current_reply += delta
                await s.ws.send(json.dumps({"type": "llm_token", "token": delta, "turn_id": s.turn_id}, ensure_ascii=False))
            return

        # 559 ChatEnded
        if event_id == 559:
            text = s.current_reply.strip()
            if text:
                s.history.append({"role": "assistant", "content": text})
                await s.ws.send(json.dumps({"type": "assistant_final", "text": text, "turn_id": s.turn_id}, ensure_ascii=False))
                await self._speak_async(text, "rt_tts_turn_%s" % s.turn_id)
            s.current_reply = ""
            return

    async def _speak_by_punctuation(self, s: RealtimeSession, turn_id: int):
        text = s.current_reply
        if not text:
            return
        if any(text.endswith(p) for p in ["。", "！", "？", ".", "!", "?"]) or len(text) >= 42:
            seg = text
            s.current_reply = ""
            if seg.strip() and not s.interrupted:
                await self._speak_async(seg.strip(), "rt_tts_turn_%s" % turn_id)

    async def _flush_speak_tail(self, s: RealtimeSession, turn_id: int):
        if s.current_reply.strip() and not s.interrupted:
            await self._speak_async(s.current_reply.strip(), "rt_tts_turn_%s" % turn_id)
        s.current_reply = ""

    async def _interrupt_session(self, s: RealtimeSession):
        s.interrupted = True
        s.current_reply = ""
        for t in list(s.running_tasks):
            if t is not asyncio.current_task() and not t.done():
                t.cancel()
        s.running_tasks = []

    async def _interrupt_generation_only(self, s: RealtimeSession):
        s.current_reply = ""

    async def _speak_async(self, text: str, label: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: self._speak_func(text, label))

    # -----------------------------
    # Doubao binary frame helpers
    # -----------------------------
    def _build_header(self, msg_type: int, flags: int, serialization: int, compression: int = 0) -> bytes:
        b0 = ((1 & 0x0F) << 4) | (1 & 0x0F)  # version=1, header_size=1(4bytes)
        b1 = ((msg_type & 0x0F) << 4) | (flags & 0x0F)
        b2 = ((serialization & 0x0F) << 4) | (compression & 0x0F)
        b3 = 0
        return bytes([b0, b1, b2, b3])

    async def _send_event(self, db_ws, event_id: int, payload: dict, session_id: str = ""):
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        frame = bytearray()
        frame.extend(self._build_header(msg_type=0b0001, flags=0b0100, serialization=0b0001))
        frame.extend(struct.pack(">I", int(event_id)))
        if session_id:
            sid = session_id.encode("utf-8")
            frame.extend(struct.pack(">I", len(sid)))
            frame.extend(sid)
        frame.extend(struct.pack(">I", len(body)))
        frame.extend(body)
        await db_ws.send(bytes(frame))

    async def _send_audio(self, db_ws, audio_bytes: bytes, session_id: str):
        frame = bytearray()
        frame.extend(self._build_header(msg_type=0b0010, flags=0b0100, serialization=0b0000))
        frame.extend(struct.pack(">I", 200))  # TaskRequest
        sid = session_id.encode("utf-8")
        frame.extend(struct.pack(">I", len(sid)))
        frame.extend(sid)
        frame.extend(struct.pack(">I", len(audio_bytes)))
        frame.extend(audio_bytes)
        await db_ws.send(bytes(frame))

    def _decode_server_frame(self, raw: bytes) -> Dict:
        if len(raw) < 8:
            return {"kind": "unknown"}
        b1 = raw[1]
        msg_type = (b1 >> 4) & 0x0F
        # flags = b1 & 0x0F
        idx = 4

        if msg_type == 0b1111:  # error
            if len(raw) < idx + 4:
                return {"kind": "error", "error": "invalid_error_frame"}
            code = struct.unpack(">I", raw[idx:idx + 4])[0]
            idx += 4
            payload_size = struct.unpack(">I", raw[idx:idx + 4])[0] if len(raw) >= idx + 4 else 0
            idx += 4
            payload = raw[idx:idx + payload_size]
            try:
                obj = json.loads(payload.decode("utf-8", errors="ignore"))
                return {"kind": "error", "code": code, "error": obj.get("message") or obj.get("error") or str(obj)}
            except Exception:
                return {"kind": "error", "code": code, "error": payload.decode("utf-8", errors="ignore")}

        if msg_type == 0b1011:  # audio-only response
            return {"kind": "audio", "payload": raw}

        if msg_type == 0b1001:  # full-server response
            if len(raw) < idx + 4:
                return {"kind": "unknown"}
            event_id = struct.unpack(">I", raw[idx:idx + 4])[0]
            idx += 4
            session_id = ""
            if len(raw) >= idx + 4:
                sid_len = struct.unpack(">I", raw[idx:idx + 4])[0]
                idx += 4
                if sid_len > 0 and len(raw) >= idx + sid_len:
                    session_id = raw[idx:idx + sid_len].decode("utf-8", errors="ignore")
                    idx += sid_len
            if len(raw) < idx + 4:
                return {"kind": "event", "event_id": event_id, "session_id": session_id, "payload": {}}
            payload_size = struct.unpack(">I", raw[idx:idx + 4])[0]
            idx += 4
            payload_bytes = raw[idx:idx + payload_size]
            payload = {}
            try:
                payload = json.loads(payload_bytes.decode("utf-8", errors="ignore"))
            except Exception:
                payload = {}
            return {"kind": "event", "event_id": int(event_id), "session_id": session_id, "payload": payload}

        return {"kind": "unknown"}
