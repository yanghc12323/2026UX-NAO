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


def build_question_user_prompt(stage: str, main_count: int = 4) -> str:
    """构造题目阶段用户提示词。"""
    if stage == "warmup":
        return "请生成1条轻松、低压力的破冰话题，用于让本科生实习候选人放松情绪并自然开口。"
    if stage == "task_intro":
        return "请生成1段任务引导词，介绍模拟面试目的、流程、时长与作答建议。"
    if stage == "self_intro":
        return "请生成1条引导语，要求候选人进行1分钟自我介绍，用于后续问题个性化。"
    if stage == "main":
        return "请生成%d条 STAR 风格行为面试问题，覆盖项目经历、协作冲突、高压应对、学习成长。" % int(main_count)
    if stage == "closing":
        return "请生成1句结束语，礼貌结束面试并引导参与者完成问卷。"
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


def build_warmup_chat_system_prompt(policy: InterviewPolicy) -> str:
    """构造 warmup 轻松聊天系统提示词。"""
    return (
        "你是模拟面试机器人的热身聊天助手，受试者是%s。\n"
        "目标：缓解紧张、建立安全感、鼓励表达。\n"
        "语气：温和、支持、自然口语，不评判，不施压。\n"
        "请输出1-2句中文：先共情/肯定，再给一个轻松追问。\n"
        "避免使用‘面试表现建议/量化结果/STAR’等正式评估措辞。\n"
        "保持与实验人设一致：%s；backchanneling：%s。"
        % (policy.target_group, policy.persona_instruction(), policy.backchanneling_instruction())
    )


def build_warmup_chat_user_prompt(user_text: str) -> str:
    """构造 warmup 轻松聊天用户提示词。"""
    return (
        "受试者刚刚说：\n"
        "---\n"
        "%s\n"
        "---\n"
        "请给出一段轻松回应（1-2句）：先简短肯定，再抛一个容易回答的小问题（如校园生活/兴趣/今天状态）。"
        % user_text
    )
