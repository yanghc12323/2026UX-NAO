# client_py3（Python3 决策层）

本目录是 NAO 面试系统的 Python3 客户端骨架，负责：

- 构造并发送协议命令到 Python2 机器人服务端；
- 提供高层动作 API（`speak/nod/gaze/reset`）；
- 承载会话流程骨架，便于后续接 LLM/ASR。

## 目录结构

```text
client_py3/
  client/
    __init__.py
    config.py
    models.py
    error_policy.py
    command_client.py
    action_adapter.py
    session_flow.py
    mock_client.py
  run_client_demo.py
```

## 运行方式（Windows）

> 你的系统 `python` 默认指向 2.7，请显式使用 Python3 解释器：
> `C:\Users\13807\miniconda3\python.exe`

### 1) Mock 模式（无需机器人）

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --verbose
```

### 2) 真实服务端模式

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --real --server-url http://127.0.0.1:8000/command --verbose
```

### 3) 严格模式（首个失败即中止）

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --real --server-url http://127.0.0.1:8000/command --verbose --fail-fast
```

### 4) 启用 DeepSeek LLM（面向本科生实习模拟）

PowerShell 先注入 API key：

```powershell
$env:DEEPSEEK_API_KEY="sk-768a6e0f68494b5f9ad551ae9c6398d2"
```

再运行：

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --use-llm --verbose
```

可选参数：
- `--llm-model deepseek-chat`
- `--persona-style encouraging`（鼓励型）
- `--persona-style pressure`（压力型）
- `--backchanneling-type positive`（积极反馈）
- `--backchanneling-type negative`（消极反馈）

若未提供 API key 且使用 `--use-llm`，会自动回退到 Demo provider。

示例（2×2 实验条件）：

```bash
# 鼓励型 + 积极反馈
C:\Users\13807\miniconda3\python.exe run_client_demo.py --use-llm --persona-style encouraging --backchanneling-type positive --verbose

# 鼓励型 + 消极反馈
C:\Users\13807\miniconda3\python.exe run_client_demo.py --use-llm --persona-style encouraging --backchanneling-type negative --verbose

# 压力型 + 积极反馈
C:\Users\13807\miniconda3\python.exe run_client_demo.py --use-llm --persona-style pressure --backchanneling-type positive --verbose

# 压力型 + 消极反馈
C:\Users\13807\miniconda3\python.exe run_client_demo.py --use-llm --persona-style pressure --backchanneling-type negative --verbose
```

## VS Code 解释器

已在 `client_py3/.vscode/settings.json` 固定为 Python3 解释器。

## 输出说明

- `[INFO] connectivity_check=reachable`：目标地址可连通。
- `[ACTION] ...`：每个动作执行后的状态输出（`--verbose`）。
- `[WARN] action_failed ...`：该动作失败并给出错误码。
- `[DONE_WITH_WARNINGS]`：流程结束但包含失败动作。
- `[ABORTED] ...`：启用 `--fail-fast` 后在首次失败处中止。
