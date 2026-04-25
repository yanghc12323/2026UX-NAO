"""LLM Prompt 模板。

说明：
- 该文件仅放“提示词文本组织逻辑”；
- 网络请求、重试等放在 `llm_provider.py`；
- 业务流程编排放在 provider / session_flow。
"""

from .interview_policy import InterviewPolicy


def build_question_system_prompt(policy: InterviewPolicy) -> str:
    """构造题目生成系统提示词。"""
    backchannel_note = policy.backchanneling_instruction()

    return (
        "你是一名面向中文场景的模拟面试官，服务对象是%s。\n"
        "你的角色要求：%s\n"
        "%s\n"
        "请保持与实验条件一致的人设与互动风格。\n"
        "请输出可直接口语播报的中文文本，避免冗长。"
        % (policy.target_group, policy.persona_instruction(), backchannel_note)
    )


def build_feedback_system_prompt(policy: InterviewPolicy) -> str:
    """构造反馈生成系统提示词。"""
    return (
        "你是模拟面试反馈助手，受试者是%s。\n"
        "请给出简明、可执行、不过度打击自信的反馈。\n"
        "语气要求：%s\n"
        "backchanneling 要求：%s\n"
        "输出中文，格式为一段自然语言。"
        % (policy.target_group, policy.persona_instruction(), policy.backchanneling_instruction())
    )


def build_question_user_prompt(stage: str, main_count: int = 2) -> str:
    """构造题目阶段用户提示词。"""
    if stage == "warmup":
        return "请生成1条热身问题，用于让本科生实习候选人快速进入状态。"
    if stage == "main":
        return "请生成%d条正式面试问题，聚焦企业实习常见能力（项目、协作、抗压、学习能力）。" % int(main_count)
    if stage == "followup":
        return "请生成1条追问提示，引导候选人复盘并优化上一轮回答。"
    if stage == "closing":
        return "请生成1句结束语，礼貌结束面试并鼓励后续改进。"
    return "请生成1条适合面试流程的中文引导语。"


def build_feedback_user_prompt(answer_text: str) -> str:
    """构造反馈阶段用户提示词。"""
    return (
        "以下是候选人的回答，请给出反馈：\n"
        "---\n"
        "%s\n"
        "---\n"
        "请给出：1) 一个优点；2) 一个可改进点；3) 一个可立即执行的改进建议。"
        % answer_text
    )
