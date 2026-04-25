"""面试会话流程骨架。

该模块提供一个最小可维护状态机，覆盖：
- warmup
- interview_main
- followup
- closing
四个阶段

你可以把 LLM 生成器接入 `QuestionProvider` / `FeedbackProvider` 两个接口。
"""

from dataclasses import dataclass, field
from typing import Callable, List, Protocol

from .action_adapter import RobotActionAdapter
from .models import CommandResponse


class QuestionProvider(Protocol):
    """问题提供器接口（可由固定题库或 LLM 实现）。"""

    def get_warmup_question(self) -> str:
        ...

    def get_main_questions(self) -> List[str]:
        ...

    def get_followup_prompt(self) -> str:
        ...

    def get_closing_words(self) -> str:
        ...


class FeedbackProvider(Protocol):
    """反馈提供器接口（可由规则引擎或 LLM 实现）。"""

    def feedback_for_answer(self, answer_text: str) -> str:
        ...


@dataclass
class InterviewSessionRunner:
    """面试会话执行器。"""

    robot: RobotActionAdapter
    questions: QuestionProvider
    feedback: FeedbackProvider
    verbose: bool = False
    fail_fast: bool = False
    had_errors: bool = field(default=False, init=False)

    def run(self) -> None:
        """执行完整会话。

        注意：
        - 当前骨架仅演示流程控制与接口风格；
        - 用户回答采集部分可后续接 ASR 或文本输入。
        """
        self._warmup_stage()
        self._main_stage()
        self._followup_stage()
        self._closing_stage()

    def _warmup_stage(self) -> None:
        question = self.questions.get_warmup_question()
        self._do_action("warmup.speak_welcome", lambda: self.robot.speak("欢迎来到模拟面试，我们先做一个简短热身。"))
        self._do_action("warmup.speak_question", lambda: self.robot.speak(question))

    def _main_stage(self) -> None:
        for idx, q in enumerate(self.questions.get_main_questions(), start=1):
            self._do_action("main[%d].speak_question" % idx, lambda q=q: self.robot.speak(q))
            # TODO: 接入真实输入采集
            mock_user_answer = "这是一个示例回答。"
            self._do_action("main[%d].nod" % idx, lambda: self.robot.nod(count=1))
            self._do_action(
                "main[%d].speak_feedback" % idx,
                lambda: self.robot.speak(self.feedback.feedback_for_answer(mock_user_answer)),
            )

    def _followup_stage(self) -> None:
        self._do_action("followup.gaze", lambda: self.robot.gaze(target="user", duration_ms=1200))
        self._do_action("followup.speak_prompt", lambda: self.robot.speak(self.questions.get_followup_prompt()))

    def _closing_stage(self) -> None:
        self._do_action("closing.speak", lambda: self.robot.speak(self.questions.get_closing_words()))
        self._do_action("closing.reset", lambda: self.robot.reset())

    def _do_action(self, action_name: str, action: Callable[[], CommandResponse]) -> CommandResponse:
        """执行单个动作并统一处理日志与失败策略。"""
        resp = action()

        if self.verbose:
            print(
                "[ACTION] %s -> status=%s error_code=%s message=%s"
                % (action_name, resp.status, resp.error_code, resp.message)
            )

        if not resp.is_ok:
            self.had_errors = True
            print(
                "[WARN] action_failed: %s (status=%s, error_code=%s, message=%s)"
                % (action_name, resp.status, resp.error_code, resp.message)
            )
            if self.fail_fast:
                raise RuntimeError("fail_fast_triggered_at_%s" % action_name)

        return resp
