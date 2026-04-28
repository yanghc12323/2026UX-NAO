"""面试实验策略配置。

该模块用于把实验条件（persona / backchanneling）与目标人群（本科生实习）
统一收口，避免业务代码里散落硬编码文本。
"""

from dataclasses import dataclass


CONDITION_MATRIX = {
    "C1": {"persona_style": "encouraging", "backchanneling_type": "positive", "label": "鼓励型 × 积极反馈"},
    "C2": {"persona_style": "encouraging", "backchanneling_type": "negative", "label": "鼓励型 × 消极反馈"},
    "C3": {"persona_style": "pressure", "backchanneling_type": "positive", "label": "压力型 × 积极反馈"},
    "C4": {"persona_style": "pressure", "backchanneling_type": "negative", "label": "压力型 × 消极反馈"},
}


@dataclass
class InterviewPolicy:
    """面试策略参数。

    字段说明：
    - `target_group`: 目标受试群体描述；默认是找企业实习的本科生。
    - `persona_style`: 机器人人设风格，例如 encouraging / pressure。
    - `backchanneling_type`: backchanneling 风格，例如 positive / negative。
    - `language`: 输出语言。
    """

    target_group: str = "正在寻找企业实习机会的本科生"
    persona_style: str = "encouraging"
    backchanneling_type: str = "positive"
    language: str = "zh"

    def persona_instruction(self) -> str:
        """根据人设返回简短行为约束文本。"""
        if self.persona_style == "encouraging":
            return "语气温和、鼓励式反馈、帮助对方稳定发挥。"
        if self.persona_style == "pressure":
            return "语气更具压力测试感，提问更直接，适度施压但保持专业与伦理边界。"
        return "语气专业，反馈简洁清晰。"

    def backchanneling_instruction(self) -> str:
        """根据 backchanneling 类型返回简短行为约束文本。"""
        if self.backchanneling_type == "positive":
            return "使用积极 backchanneling（如肯定、点头、鼓励性的短反馈）。"
        if self.backchanneling_type == "negative":
            return "使用消极 backchanneling（如更少肯定、审慎回应、轻微质疑式短反馈）。"
        return "使用中性 backchanneling。"


@dataclass
class ConditionPolicy:
    """从实验条件派生统一策略，供 Web 与 CLI 共用。"""

    condition_id: str
    persona_style: str
    backchanneling_type: str
    label: str = ""

    @classmethod
    def from_condition_id(cls, condition_id: str) -> "ConditionPolicy":
        c = CONDITION_MATRIX.get(str(condition_id or "").strip().upper())
        if c is None:
            raise ValueError("invalid_condition_id")
        return cls(
            condition_id=str(condition_id).strip().upper(),
            persona_style=str(c["persona_style"]),
            backchanneling_type=str(c["backchanneling_type"]),
            label=str(c.get("label", "")),
        )

    @classmethod
    def from_styles(cls, persona_style: str, backchanneling_type: str, condition_id: str = "CUSTOM") -> "ConditionPolicy":
        return cls(
            condition_id=str(condition_id),
            persona_style=str(persona_style or "encouraging"),
            backchanneling_type=str(backchanneling_type or "positive"),
            label="custom",
        )

    def to_interview_policy(self, target_group: str = "正在寻找企业实习机会的本科生", language: str = "zh") -> InterviewPolicy:
        return InterviewPolicy(
            target_group=target_group,
            persona_style=self.persona_style,
            backchanneling_type=self.backchanneling_type,
            language=language,
        )

    def backchannel_profile(self) -> dict:
        if self.backchanneling_type == "positive":
            return {"nod_frequency": "high", "ack_style": "affirmative"}
        if self.backchanneling_type == "negative":
            return {"nod_frequency": "low", "ack_style": "skeptical"}
        return {"nod_frequency": "medium", "ack_style": "neutral"}
