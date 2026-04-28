"""面向实验日志的核心指标计算。"""

import re
from typing import Dict, Iterable


DEFAULT_DISFLUENCY_WORDS = ("额", "呃", "那个", "然后")
DEFAULT_SELF_CORRECTION_MARKERS = ("我是说", "不对", "更准确", "准确说")


def compute_speech_rate_cpm(text: str, speech_duration_s: float) -> float:
    """语速：每分钟字符数（char/min）。"""
    duration = max(0.1, float(speech_duration_s))
    return round((len(text.strip()) / duration) * 60.0, 3)


def compute_disfluency_ratio(text: str, disfluency_words: Iterable[str] = DEFAULT_DISFLUENCY_WORDS) -> float:
    """流利度代理指标：停顿词总次数 / 总字数。"""
    clean = text.strip()
    total_chars = max(1, len(clean))
    count = 0
    for word in disfluency_words:
        count += clean.count(word)
    return round(float(count) / float(total_chars), 6)


def compute_fluency_metrics(text: str, speech_duration_s: float) -> Dict[str, float]:
    """更稳健的流畅度代理指标（保持轻量、可实时计算）。"""
    clean = str(text or "").strip()
    total_chars = max(1, len(clean))

    disfluency_ratio = compute_disfluency_ratio(clean)

    pause_count = clean.count("，") + clean.count("。") + clean.count("…") + clean.count("...")
    pause_ratio = round(float(pause_count) / float(total_chars), 6)

    tokens = [t for t in re.split(r"[，。！？；、\s]+", clean) if t]
    rep_count = 0
    for i in range(1, len(tokens)):
        if tokens[i] == tokens[i - 1]:
            rep_count += 1
    repetition_ratio = round(float(rep_count) / float(max(1, len(tokens))), 6)

    correction_count = 0
    for marker in DEFAULT_SELF_CORRECTION_MARKERS:
        correction_count += clean.count(marker)
    self_correction_ratio = round(float(correction_count) / float(total_chars), 6)

    # 越高越流畅（0~1）。仅作为在线代理分数，不替代离线精细标注。
    raw_score = 1.0 - (1.2 * disfluency_ratio + 0.8 * repetition_ratio + 0.6 * self_correction_ratio + 0.2 * pause_ratio)
    fluency_score = round(max(0.0, min(1.0, raw_score)), 6)

    return {
        "disfluency_ratio": disfluency_ratio,
        "pause_ratio": pause_ratio,
        "repetition_ratio": repetition_ratio,
        "self_correction_ratio": self_correction_ratio,
        "fluency_score": fluency_score,
        "speech_rate_cpm": compute_speech_rate_cpm(clean, speech_duration_s),
    }


def compute_gaze_contact_ratio(gaze_contact_s: float, speech_duration_s: float) -> float:
    """视线接触比例：看向机器人时长 / 回答时长。"""
    duration = max(0.1, float(speech_duration_s))
    ratio = max(0.0, min(float(gaze_contact_s) / duration, 1.0))
    return round(ratio, 6)
