"""基于 LLM 的面试问题/反馈提供器实现。

该模块把 `session_flow.py` 中的协议接口落到具体实现：
- `LLMQuestionProvider`：生成热身题、主问题、追问、结束语；
- `LLMFeedbackProvider`：基于回答生成反馈。

注意：
- 当 LLM 请求失败时，模块会回退到本地默认文案，确保流程可继续；
- 这样实验现场即使网络波动，也不会直接中断演示。
"""

from typing import List

from .interview_policy import InterviewPolicy
from .llm_provider import LLMClient
from .prompt_templates import (
    build_feedback_system_prompt,
    build_feedback_user_prompt,
    build_question_system_prompt,
    build_question_user_prompt,
)


class LLMQuestionProvider(object):
    """基于 LLM 的问题提供器。"""

    def __init__(self, llm: LLMClient, policy: InterviewPolicy, main_count: int = 2):
        self.llm = llm
        self.policy = policy
        self.main_count = int(main_count)

    def get_warmup_question(self) -> str:
        fallback = "请你先做一个30秒的自我介绍。"
        return self._generate_single_line(stage="warmup", fallback=fallback)

    def get_main_questions(self) -> List[str]:
        fallback = [
            "请介绍一个你主导完成的项目，并说明你的关键贡献。",
            "在高压任务中，你如何安排优先级并保证质量？",
        ]
        text = self._ask_llm(stage="main")
        if not text:
            return fallback[: self.main_count]

        lines = _extract_candidate_lines(text)
        if not lines:
            return fallback[: self.main_count]

        result = lines[: self.main_count]
        if len(result) < self.main_count:
            result.extend(fallback[len(result) : self.main_count])
        return result

    def get_followup_prompt(self) -> str:
        fallback = "如果给你一次重来的机会，你会如何优化刚才的回答？"
        return self._generate_single_line(stage="followup", fallback=fallback)

    def get_closing_words(self) -> str:
        fallback = "今天的模拟面试到这里，感谢你的参与。"
        return self._generate_single_line(stage="closing", fallback=fallback)

    def _generate_single_line(self, stage: str, fallback: str) -> str:
        text = self._ask_llm(stage=stage)
        if not text:
            return fallback
        lines = _extract_candidate_lines(text)
        return lines[0] if lines else fallback

    def _ask_llm(self, stage: str) -> str:
        system_prompt = build_question_system_prompt(self.policy)
        user_prompt = build_question_user_prompt(stage=stage, main_count=self.main_count)
        try:
            return self.llm.chat_completion_text(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception as exc:  # noqa: BLE001
            print("[WARN] llm_question_provider_fallback stage=%s reason=%s" % (stage, exc))
            return ""


class LLMFeedbackProvider(object):
    """基于 LLM 的反馈提供器。"""

    def __init__(self, llm: LLMClient, policy: InterviewPolicy):
        self.llm = llm
        self.policy = policy

    def feedback_for_answer(self, answer_text: str) -> str:
        fallback = "你的回答结构不错。建议补充一个可量化结果，让说服力更强。"
        system_prompt = build_feedback_system_prompt(self.policy)
        user_prompt = build_feedback_user_prompt(answer_text=answer_text)

        try:
            text = self.llm.chat_completion_text(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception as exc:  # noqa: BLE001
            print("[WARN] llm_feedback_provider_fallback reason=%s" % exc)
            return fallback

        lines = _extract_candidate_lines(text)
        if lines:
            return " ".join(lines[:3])
        return fallback


def _extract_candidate_lines(text: str) -> List[str]:
    """从模型输出中提取候选句子列表。

    兼容常见格式：
    - 多行文本
    - 编号列表（1. / 2) / 一、）
    - 无换行的一整段
    """
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not raw_lines:
        return []

    cleaned: List[str] = []
    for line in raw_lines:
        line = _strip_list_prefix(line)
        if line:
            cleaned.append(line)

    return cleaned


def _strip_list_prefix(line: str) -> str:
    """去除编号/项目符号前缀，保留核心文本。"""
    prefixes = ["-", "•", "*", "一、", "二、", "三、"]
    for p in prefixes:
        if line.startswith(p):
            return line[len(p) :].strip()

    # 处理 1. xxx / 2) xxx / 3、xxx
    if len(line) >= 3 and line[0].isdigit() and line[1] in (".", ")", "、"):
        return line[2:].strip()
    return line.strip()
