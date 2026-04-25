"""Python3 客户端骨架演示入口。

运行方式：
1) 默认 mock 模式（无需机器人）：
   python run_client_demo.py --verbose

2) 真实服务端模式：
   python run_client_demo.py --real --server-url http://127.0.0.1:8000/command --verbose
"""

import argparse
import os
from urllib import request, error
from typing import List

from client.config import ClientConfig, SessionContext
from client.command_client import CommandClient
from client.mock_client import MockCommandClient
from client.error_policy import ErrorPolicy
from client.action_adapter import RobotActionAdapter
from client.session_flow import InterviewSessionRunner, QuestionProvider, FeedbackProvider
from client.llm_provider import LLMClient, LLMConfig
from client.interview_policy import InterviewPolicy
from client.llm_interview_provider import LLMQuestionProvider, LLMFeedbackProvider


class DemoQuestionProvider(QuestionProvider):
    """示例问题提供器。"""

    def get_warmup_question(self) -> str:
        return "请你先做一个30秒的自我介绍。"

    def get_main_questions(self) -> List[str]:
        return [
            "请介绍一个你主导完成的项目，并说明你的关键贡献。",
            "在高压任务中，你如何安排优先级并保证质量？",
        ]

    def get_followup_prompt(self) -> str:
        return "如果给你一次重来的机会，你会如何优化刚才的回答？"

    def get_closing_words(self) -> str:
        return "今天的模拟面试到这里，感谢你的参与。"


class DemoFeedbackProvider(FeedbackProvider):
    """示例反馈提供器。"""

    def feedback_for_answer(self, answer_text: str) -> str:
        # 真实场景可替换为 LLM 推理结果
        return "你的回答结构不错。建议补充一个可量化结果，让说服力更强。"


def build_interview_providers(
    use_llm: bool,
    llm_api_key: str,
    llm_model: str,
    llm_base_url: str,
    persona_style: str,
    backchanneling_type: str,
) -> (QuestionProvider, FeedbackProvider):
    """构建问题与反馈提供器。

    说明：
    - 当 `use_llm=False` 时，始终走 demo 固定文案；
    - 当 `use_llm=True` 但未提供 API key 时，自动回退 demo 并打印提醒；
    - 当 `use_llm=True` 且有 API key 时，使用 DeepSeek API。
    """
    if not use_llm:
        return DemoQuestionProvider(), DemoFeedbackProvider()

    if not llm_api_key:
        print("[WARN] --use-llm 已启用，但未检测到 API key；自动回退到 Demo provider。")
        print("[HINT] 你可通过环境变量 DEEPSEEK_API_KEY 或参数 --llm-api-key 传入。")
        return DemoQuestionProvider(), DemoFeedbackProvider()

    policy = InterviewPolicy(
        target_group="正在寻找企业实习机会的本科生",
        persona_style=persona_style,
        backchanneling_type=backchanneling_type,
        language="zh",
    )
    llm = LLMClient(
        LLMConfig(
            api_key=llm_api_key,
            model=llm_model,
            base_url=llm_base_url,
        )
    )
    return LLMQuestionProvider(llm=llm, policy=policy), LLMFeedbackProvider(llm=llm, policy=policy)


def build_robot_adapter(use_real: bool, server_url: str) -> RobotActionAdapter:
    """构建动作适配器。"""
    config = ClientConfig(server_url=server_url)
    session = SessionContext(
        session_id="S_DEMO_001",
        participant_id="P_DEMO",
        condition_id="C1",
    )
    policy = ErrorPolicy()

    if use_real:
        client = CommandClient(config=config, session=session, error_policy=policy)
    else:
        client = MockCommandClient(config=config, session=session, error_policy=policy)

    return RobotActionAdapter(command_client=client)


def check_server_reachable(server_url: str, timeout_s: float = 1.5) -> bool:
    """快速检查服务端可达性（只做连通性探测，不保证协议正确）。"""
    probe = request.Request(url=server_url, data=b"{}", method="POST")
    try:
        with request.urlopen(probe, timeout=timeout_s):
            return True
    except error.HTTPError:
        # 能收到 HTTPError 也说明网络可达（只是接口可能拒绝该探测报文）
        return True
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="NAO Python3 Client Skeleton Demo")
    parser.add_argument("--real", action="store_true", help="Use real HTTP server instead of mock mode")
    parser.add_argument("--server-url", default="http://127.0.0.1:8000/command", help="Server endpoint URL")
    parser.add_argument("--verbose", action="store_true", help="Print per-action response details")
    parser.add_argument("--fail-fast", action="store_true", help="Abort immediately when any action fails")
    parser.add_argument("--use-llm", action="store_true", help="Use DeepSeek LLM to generate questions and feedback")
    parser.add_argument("--llm-api-key", default="", help="DeepSeek API key (optional; can use env DEEPSEEK_API_KEY)")
    parser.add_argument("--llm-model", default="deepseek-chat", help="DeepSeek model name")
    parser.add_argument(
        "--llm-base-url",
        default="https://api.deepseek.com/chat/completions",
        help="DeepSeek OpenAI-compatible chat completions endpoint",
    )
    parser.add_argument(
        "--persona-style",
        default="encouraging",
        help="Interview persona style: encouraging/pressure",
    )
    parser.add_argument(
        "--backchanneling-type",
        default="positive",
        help="Backchanneling type: positive/negative",
    )
    args = parser.parse_args()

    mode = "REAL" if args.real else "MOCK"
    print("[INFO] mode=%s server_url=%s" % (mode, args.server_url))

    llm_api_key = args.llm_api_key or os.environ.get("DEEPSEEK_API_KEY", "")
    if args.use_llm:
        print(
            "[INFO] llm_mode=enabled model=%s persona=%s backchanneling=%s"
            % (args.llm_model, args.persona_style, args.backchanneling_type)
        )
    else:
        print("[INFO] llm_mode=disabled (using demo providers)")

    if args.real:
        reachable = check_server_reachable(args.server_url)
        if reachable:
            print("[INFO] connectivity_check=reachable (%s)" % args.server_url)
        else:
            print("[WARN] connectivity_check=unreachable (%s)" % args.server_url)
            if args.fail_fast:
                raise RuntimeError("server_unreachable_and_fail_fast_enabled")

    robot = build_robot_adapter(use_real=args.real, server_url=args.server_url)
    questions, feedback = build_interview_providers(
        use_llm=args.use_llm,
        llm_api_key=llm_api_key,
        llm_model=args.llm_model,
        llm_base_url=args.llm_base_url,
        persona_style=args.persona_style,
        backchanneling_type=args.backchanneling_type,
    )
    runner = InterviewSessionRunner(
        robot=robot,
        questions=questions,
        feedback=feedback,
        verbose=args.verbose,
        fail_fast=args.fail_fast,
    )

    try:
        runner.run()
    except RuntimeError as exc:
        print("[ABORTED] %s" % exc)
        raise

    if runner.had_errors:
        print("[DONE_WITH_WARNINGS] Session flow finished with failed actions.")
    else:
        print("[DONE] Session flow finished.")


if __name__ == "__main__":
    main()
