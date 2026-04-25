"""基于 LLM 的面试问题/反馈提供器实现。

该模块把 `session_flow.py` 中的协议接口落到具体实现：
- `LLMQuestionProvider`：生成热身题、任务引导、1分钟自我介绍提示、STAR 主问题、结束语；
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

    def __init__(self, llm: LLMClient, policy: InterviewPolicy, main_count: int = 4):
        self.llm = llm
        self.policy = policy
        self.main_count = int(main_count)

    def get_warmup_question(self) -> str:
        fallback = "请你先做一个30秒的自我介绍。"
        return self._generate_single_line(stage="warmup", fallback=fallback)

    def get_task_intro_words(self) -> str:
        fallback = "接下来我们进行模拟面试：先听说明，再完成1分钟自我介绍，然后回答几道行为面试题。"
        return self._generate_single_line(stage="task_intro", fallback=fallback)

    def get_self_intro_prompt(self) -> str:
        fallback = "请你用约1分钟做自我介绍，重点说明经历、优势和你期待的实习方向。"
        return self._generate_single_line(stage="self_intro", fallback=fallback)

    def get_main_questions(self) -> List[str]:
        fallback = [
            "请用 STAR 结构介绍一个你主导推进并最终落地的项目经历。",
            "请回忆一次团队协作冲突，你当时如何沟通并推动问题解决？",
            "面对高压 deadline 时，你如何安排优先级并保证交付质量？",
            "请分享一次你快速学习新技能并应用到任务中的经历。",
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

    def get_closing_words(self) -> str:
        fallback = "今天的模拟面试到这里，感谢你的参与。请继续完成问卷，帮助我们改进系统。"
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
