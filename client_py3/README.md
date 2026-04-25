# client_py3（Python3 决策层）

本目录是 NAO 面试系统的 Python3 客户端骨架，负责：

- 构造并发送协议命令到 Python2 机器人服务端；
- 提供高层动作 API（`speak/nod/gaze/reset`）；
- 承载实验会话状态机、输入采集、指标计算与日志落盘。

## 当前能力边界（重要）

- ✅ 已有：
  - 4阶段会话流程：`warmup -> task_intro -> formal_interview -> closing_and_questionnaire`
  - 可插拔输入采集接口：`ASRProvider` + `ASRFirstInputProvider`（支持 `mock/jsonl/realtime`）
  - 可插拔视线估计接口：`GazeProvider`（支持 `mock/jsonl/realtime/none`）
  - **HTTP 实时推送模式**：通过 HTTP 服务器接收外部进程推送的 ASR/Gaze 数据
  - 三项指标计算：`speech_rate_cpm` / `disfluency_ratio` / `gaze_contact_ratio`
  - 结构化日志：`stage_event` / `metric_event` / `action_event`（jsonl）
  - LLM 生成问题与反馈 + persona/backchanneling 条件化
- ✅ 已提供：Python2 推送器示例（`robot_server_py2/asr_realtime_pusher.py` 和 `gaze_realtime_pusher.py`）
- 📖 详细说明：`docs/realtime_http_integration_guide.md`

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
    input_provider.py
    metrics.py
    experiment_logger.py
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

# 启用日志落盘
C:\Users\13807\miniconda3\python.exe run_client_demo.py --verbose --enable-logging --log-dir logs
```

### 2) 真实服务端模式

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --real --server-url http://127.0.0.1:8000/command --verbose
```

### 2.1 接入真实 ASR / 视觉信号

#### 方式 1：HTTP 实时推送模式（推荐用于真实实验）

运行参数：
- `--asr-mode realtime`：启用 HTTP 实时推送接收 ASR 数据
- `--gaze-mode realtime`：启用 HTTP 实时推送接收 Gaze 数据
- `--realtime-port 8765`：HTTP 服务器端口（默认 8765）

示例：

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py \
  --real \
  --asr-mode realtime \
  --gaze-mode realtime \
  --persona-style encouraging \
  --backchanneling-type positive \
  --verbose
```

此模式下，客户端会启动 HTTP 服务器监听 8765 端口，等待外部进程推送数据：
- ASR 数据推送到：`POST http://127.0.0.1:8765/asr`
- Gaze 数据推送到：`POST http://127.0.0.1:8765/gaze`

**配套使用**：
- Python2 ASR 推送器：`robot_server_py2/asr_realtime_pusher.py`
- Python2 Gaze 推送器：`robot_server_py2/gaze_realtime_pusher.py`

**详细说明**：请参考 `docs/realtime_http_integration_guide.md`

---

#### 方式 2：JSONL 文件模式（用于离线测试）

运行参数：
- `--asr-mode jsonl`：从 JSONL 文件读取 ASR 数据
- `--asr-jsonl-path <path>`：JSONL 文件路径
- `--gaze-mode jsonl`：从 JSONL 文件读取 Gaze 数据
- `--gaze-jsonl-path <path>`：JSONL 文件路径

示例：

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py \
  --real \
  --asr-mode jsonl \
  --asr-jsonl-path .\data\asr_stream.jsonl \
  --gaze-mode jsonl \
  --gaze-jsonl-path .\data\gaze_stream.jsonl \
  --verbose
```

ASR JSONL 单行示例：

```json
{"text":"我在一个校园项目里负责后端重构","speech_duration_s":8.3,"timestamp_ms":1714012345678,"stage":"formal_interview"}
```

Gaze JSONL 单行示例：

```json
{"gaze_contact_s":5.2,"stage":"formal_interview"}
```

### 3) 严格模式（首个失败即中止）

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --real --server-url http://127.0.0.1:8000/command --verbose --fail-fast
```

### 4) 启用 DeepSeek LLM（面向本科生实习模拟）

PowerShell 先注入 API key：

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
- `--persona-style encouraging`（鼓励型）
- `--persona-style pressure`（压力型）
- `--backchanneling-type positive`（积极反馈）
- `--backchanneling-type negative`（消极反馈）
- `--formal-question-count 4`（正式 STAR 题数量，建议 3~4）
- `--enable-logging`（开启 jsonl 日志）
- `--log-dir logs`（日志目录）

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

## 与实验文档对齐说明

- `warmup/task_intro` 阶段固定中立风格；
- `formal_interview` 阶段执行条件化人格（`encouraging/pressure`）与 backchannel（`positive/negative`）；
- 正式阶段流程：1 分钟自我介绍 + STAR 3~4 题；
- 会话结束阶段为 `closing_and_questionnaire`，并记录阶段事件。

## 下一步（建议）

1. **使用 HTTP 实时推送模式**：启动 Python2 推送器（`asr_realtime_pusher.py` 和 `gaze_realtime_pusher.py`）配合客户端使用。
2. **完善 Python2 服务端**：实现 `POST /command` 接口，对接 NAO SDK 动作 API。
3. **端到端测试**：在真实 NAO 环境下运行完整流程，校准 backchannel 触发频率与时延参数。
4. **可选扩展**：如需 SDK 直连（不通过 HTTP），可在 `input_provider.py` 中添加新的 Provider 实现。
