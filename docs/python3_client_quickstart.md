# Python3 客户端骨架快速使用说明

本文对应以下代码：
- `client_py3/client/`（核心客户端包）
- `client_py3/run_client_demo.py`（可运行示例）

## 1. 目录说明

```text
client_py3/
  client/
    __init__.py            # 对外导出
    config.py              # ClientConfig / SessionContext
    models.py              # CommandRequest / CommandResponse
    error_policy.py        # 错误码策略
    command_client.py      # HTTP 命令发送与重试
    action_adapter.py      # 高层动作接口（speak/nod/gaze...）
    session_flow.py        # 会话流程骨架（4阶段）
    mock_client.py         # 本地联调 mock 传输
  run_client_demo.py       # 运行入口
```

## 2. 运行演示

> ⚠️ 重要：你当前系统里 `python` 默认是 2.7。运行 Python3 客户端时请不要直接用 `python`。
> 建议使用：
> - `C:\\Users\\13807\\miniconda3\\python.exe`
> - 或在 VS Code 打开 `client_py3` 并确认解释器为 Python3 后再运行。

### 2.1 无设备（Mock）

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --verbose
```

### 2.2 对接真实服务端

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --real --server-url http://127.0.0.1:8000/command --verbose
```

### 2.3 建议的严格检查模式（发现错误立刻中止）

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --real --server-url http://127.0.0.1:8000/command --verbose --fail-fast
```

输出解读：
- `[INFO] connectivity_check=reachable`：地址可连通。
- `[WARN] action_failed ...`：该动作执行失败（会显示错误码）。
- `[DONE_WITH_WARNINGS]`：流程跑完但中间有失败动作。
- `[ABORTED] ...`：启用 `--fail-fast` 后首个失败即中止。

### 2.4 启用 DeepSeek LLM（自动生成问题与反馈）

先设置 API Key（PowerShell）：

```powershell
$env:DEEPSEEK_API_KEY="你的DeepSeek_API_Key"
```

再运行：

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --use-llm --verbose
```

可选参数：
- `--llm-model deepseek-chat`
- `--persona-style encouraging`（鼓励型）/ `--persona-style pressure`（压力型）
- `--backchanneling-type positive`（积极反馈）/ `--backchanneling-type negative`（消极反馈）

如果你启用了 `--use-llm` 但未提供 API key，程序会打印警告并自动回退到 Demo provider。

2×2 实验条件示例：

```bash
C:\Users\13807\miniconda3\python.exe run_client_demo.py --use-llm --persona-style encouraging --backchanneling-type positive --verbose
C:\Users\13807\miniconda3\python.exe run_client_demo.py --use-llm --persona-style encouraging --backchanneling-type negative --verbose
C:\Users\13807\miniconda3\python.exe run_client_demo.py --use-llm --persona-style pressure --backchanneling-type positive --verbose
C:\Users\13807\miniconda3\python.exe run_client_demo.py --use-llm --persona-style pressure --backchanneling-type negative --verbose
```

## 3. 业务层推荐调用方式

```python
from client.config import ClientConfig, SessionContext
from client.command_client import CommandClient
from client.error_policy import ErrorPolicy
from client.action_adapter import RobotActionAdapter

cfg = ClientConfig(server_url="http://127.0.0.1:8000/command")
session = SessionContext(session_id="S001", participant_id="P001", condition_id="C1")
cli = CommandClient(config=cfg, session=session, error_policy=ErrorPolicy())
robot = RobotActionAdapter(cli)

resp = robot.speak("你好，我们开始吧。")
print(resp.status, resp.error_code, resp.message)
```

## 4. 后续扩展建议

1. 在 `session_flow.py` 中接入真实 ASR 输入替换 `mock_user_answer`。  
2. 将 `DemoFeedbackProvider` 替换为 LLM 调用层。  
3. 增加日志落盘（jsonl）并记录 request_id/turn_id/latency。  
4. 在 `ErrorPolicy` 中按实验策略细化降级动作。
