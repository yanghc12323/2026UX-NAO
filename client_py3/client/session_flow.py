"""实验版会话流程（warmup -> task_intro -> formal_interview -> closing）。"""

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Protocol

from .action_adapter import RobotActionAdapter
from .config import SessionContext
from .experiment_logger import ExperimentLogger
from .gaze_provider import GazeProvider
from .input_provider import SessionInputProvider
from .metrics import compute_disfluency_ratio, compute_gaze_contact_ratio, compute_speech_rate_cpm
from .models import CommandResponse


class QuestionProvider(Protocol):
    """问题提供器接口（可由固定题库或 LLM 实现）。"""

    def get_warmup_question(self) -> str:
        ...

    def get_task_intro_words(self) -> str:
        ...

    def get_self_intro_prompt(self) -> str:
        ...

    def get_main_questions(self) -> List[str]:
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
    input_provider: SessionInputProvider
    gaze_provider: Optional[GazeProvider]
    session: SessionContext
    logger: Optional[ExperimentLogger] = None
    verbose: bool = False
    fail_fast: bool = False
    formal_question_count: int = 4
    had_errors: bool = field(default=False, init=False)
    _user_turn_counter: int = field(default=0, init=False, repr=False)

    def run(self) -> None:
        """执行完整会话。"""
        self._warmup_stage()
        self._task_intro_stage()
        self._formal_interview_stage()
        self._closing_stage()

    def _warmup_stage(self) -> None:
        self._emit_stage("warmup", "enter", {"persona_mode": "neutral"})
        self._do_action("warmup.speak_welcome", lambda: self.robot.speak("欢迎来到模拟面试，我们先做一个简短热身。"))
        question = self.questions.get_warmup_question()
        self._do_action("warmup.speak_question", lambda: self.robot.speak(question))
        sample = self.input_provider.collect_answer(stage="warmup", prompt=question)
        self._log_metrics(stage="warmup", sample_text=sample.text, speech_duration_s=sample.speech_duration_s, gaze_contact_s=self._resolve_gaze_contact("warmup", sample.text, sample.speech_duration_s, sample.gaze_contact_s))
        self._do_action("warmup.speak_ack", lambda: self.robot.speak("收到，谢谢你的介绍。"))
        self._emit_stage("warmup", "exit", {"persona_mode": "neutral"})

    def _task_intro_stage(self) -> None:
        self._emit_stage("task_intro", "enter", {"persona_mode": "neutral"})
        self._do_action("task_intro.speak", lambda: self.robot.speak(self.questions.get_task_intro_words()))
        self._emit_stage("task_intro", "exit", {"persona_mode": "neutral"})

    def _formal_interview_stage(self) -> None:
        self._emit_stage("formal_interview", "enter", {"persona_mode": "conditioned"})

        self_intro_prompt = self.questions.get_self_intro_prompt()
        self._do_action("formal.self_intro_prompt", lambda: self.robot.speak(self_intro_prompt))
        intro_sample = self.input_provider.collect_answer(stage="formal_interview", prompt=self_intro_prompt)
        self._do_action("formal.self_intro_nod", lambda: self.robot.nod(count=1))
        self._do_action("formal.self_intro_feedback", lambda: self.robot.speak(self.feedback.feedback_for_answer(intro_sample.text)))
        self._log_metrics(
            stage="formal_interview",
            sample_text=intro_sample.text,
            speech_duration_s=intro_sample.speech_duration_s,
            gaze_contact_s=self._resolve_gaze_contact("formal_interview", intro_sample.text, intro_sample.speech_duration_s, intro_sample.gaze_contact_s),
        )

        main_questions = self.questions.get_main_questions()[: max(1, int(self.formal_question_count))]
        for idx, q in enumerate(main_questions, start=1):
            self._do_action("formal.star[%d].speak_question" % idx, lambda q=q: self.robot.speak(q))
            sample = self.input_provider.collect_answer(stage="formal_interview", prompt=q)
            self._do_action("formal.star[%d].nod" % idx, lambda: self.robot.nod(count=1))
            self._do_action("formal.star[%d].gaze" % idx, lambda: self.robot.gaze(target="user", duration_ms=1200))
            self._do_action(
                "formal.star[%d].speak_feedback" % idx,
                lambda sample=sample: self.robot.speak(self.feedback.feedback_for_answer(sample.text)),
            )
            self._log_metrics(
                stage="formal_interview",
                sample_text=sample.text,
                speech_duration_s=sample.speech_duration_s,
                gaze_contact_s=self._resolve_gaze_contact("formal_interview", sample.text, sample.speech_duration_s, sample.gaze_contact_s),
            )

        self._emit_stage("formal_interview", "exit", {"persona_mode": "conditioned"})

    def _closing_stage(self) -> None:
        self._emit_stage("closing_and_questionnaire", "enter", {"persona_mode": "neutral"})
        self._do_action("closing.speak", lambda: self.robot.speak(self.questions.get_closing_words()))
        self._do_action("closing.reset", lambda: self.robot.reset())
        self._emit_stage("closing_and_questionnaire", "exit", {"persona_mode": "neutral"})

    def _log_metrics(self, stage: str, sample_text: str, speech_duration_s: float, gaze_contact_s: float) -> None:
        if self.logger is None:
            return
        self._user_turn_counter += 1
        turn_id = "U%03d" % self._user_turn_counter
        metrics = {
            "speech_rate_cpm": compute_speech_rate_cpm(sample_text, speech_duration_s),
            "disfluency_ratio": compute_disfluency_ratio(sample_text),
            "gaze_contact_ratio": compute_gaze_contact_ratio(gaze_contact_s, speech_duration_s),
        }
        self.logger.metric_event(session_id=self.session.session_id, turn_id=turn_id, stage=stage, metrics=metrics)

    def _emit_stage(self, stage: str, phase: str, meta: dict) -> None:
        if self.logger is not None:
            self.logger.stage_event(session_id=self.session.session_id, stage=stage, phase=phase, meta=meta)

    def _resolve_gaze_contact(self, stage: str, answer_text: str, speech_duration_s: float, fallback_gaze_contact_s: float) -> float:
        """优先使用视觉链路观测，否则回退输入样本内的 gaze 值。"""
        if self.gaze_provider is not None:
            try:
                observed = self.gaze_provider.estimate_gaze_contact_s(
                    stage=stage,
                    answer_text=answer_text,
                    speech_duration_s=speech_duration_s,
                )
                if observed is not None:
                    return max(0.0, float(observed))
            except Exception as exc:  # noqa: BLE001
                print("[WARN] gaze_estimate_failed stage=%s reason=%s" % (stage, exc))
        return max(0.0, float(fallback_gaze_contact_s))

    def _do_action(self, action_name: str, action: Callable[[], CommandResponse]) -> CommandResponse:
        """执行单个动作并统一处理日志与失败策略。"""
        resp = action()

        if self.logger is not None:
            exec_ms = int(resp.result.get("execution_ms", 0) or 0)
            stage_name = action_name.split(".")[0] if "." in action_name else "unknown"
            self.logger.action_event(
                session_id=self.session.session_id,
                stage=stage_name,
                action=action_name,
                status=resp.status,
                error_code=resp.error_code,
                message=resp.message,
                execution_ms=exec_ms,
            )

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
