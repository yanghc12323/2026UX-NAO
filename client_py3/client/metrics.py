"""面向实验日志的核心指标计算。"""

from typing import Iterable


DEFAULT_DISFLUENCY_WORDS = ("额", "呃", "那个", "然后")


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


def compute_gaze_contact_ratio(gaze_contact_s: float, speech_duration_s: float) -> float:
    """视线接触比例：看向机器人时长 / 回答时长。"""
    duration = max(0.1, float(speech_duration_s))
    ratio = max(0.0, min(float(gaze_contact_s) / duration, 1.0))
    return round(ratio, 6)
