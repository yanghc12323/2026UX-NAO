# NAO 与被试实时对话能力与实验流程说明

## 1. 现在是否可以实现 NAO 和被试实时对话？

可以，**在满足部署条件时已经可以实现实时对话闭环**：

- 被试说话（由 ASR 端采集并推送）
- Python3 客户端接收 ASR 文本
- 客户端把文本发送给 LLM（DeepSeek）
- 收到 LLM 回复后下发给 Python2 机器人端
- NAO 执行 `speak` 播报回复

本轮已完成的关键改造：

1. `client_py3/run_client_demo.py` 新增 `freechat` 模式：
   - 参数：`--dialogue-mode freechat`
   - 流程：`ASR -> LLM -> robot.speak()`
2. `client_py3/client/input_provider.py` 增加心跳过滤：
   - 跳过 `heartbeat=true` 与 `text="<heartbeat>"`
   - 避免心跳包误触发一轮对话

---

## 2. 你提出的新流程要求（已实现）

你要求的目标是：

- 全流程仍然是 4 阶段：`warmup -> task_intro -> formal_interview -> closing`
- 其中 **warmup + formal_interview**：NAO 联通 LLM，实时基于被试回答反馈/追问
- 其中 **task_intro + closing**：只说固定脚本，不走 LLM

该逻辑已在 `client_py3/client/session_flow.py` 中落地：

- 新增 `llm_chat` 注入能力与 `_llm_stage_reply()`
- 只在 `stage in ("warmup", "formal_interview")` 时调用 LLM
- 若 LLM 不可用/异常，自动回退脚本反馈（不会中断实验）

---

## 3. 当前支持的两种流程模式

系统现在有两种可选模式：

### A) 实验脚本模式（默认）

- 参数：`--dialogue-mode interview`
- 特点：按固定实验阶段运行（warmup -> task_intro -> formal_interview -> closing）
- 适用：标准实验采集、条件对照

### B) 自由对话模式（新增）

- 参数：`--dialogue-mode freechat`
- 特点：逐轮实时对话（用户一句 -> NAO一句）
- 适用：演示真实对话感、压力面试“互动感”验证

---

## 4. 实验整体推荐流程（主试视角）

下面给出你们当前项目下可执行、易落地的标准流程。

## 阶段 0：启动后端服务

1. 启动 Python2 机器人命令服务（NAO 控制端）：
   - 文件：`robot_server_py2/command_server.py`
   - 作用：接收 Python3 指令并驱动 NAO 动作/语音

2. 启动 ASR 推送端（实时语音转写）：
   - 文件：`robot_server_py2/asr_realtime_pusher.py`
   - 作用：将识别文本 POST 到 Python3 realtime bridge

> 若同时做注视指标，也可并行启动 gaze 推送端。

---

## 阶段 1：启动 Python3 客户端

入口：`client_py3/run_client_demo.py`

根据实验目的选择模式：

1. **标准实验采集**：`--dialogue-mode interview`
2. **实时自由对话演示**：`--dialogue-mode freechat`

关键参数说明：

- `--real`：启用真实机器人 HTTP 调用
- `--server-url`：Python2 command server 地址
- `--asr-mode realtime`：接收实时 ASR
- `--realtime-host/--realtime-port`：本地 realtime bridge 地址
- `--llm-api-key`：LLM Key（freechat 模式必需）

---

## 阶段 2A：实验脚本模式（interview）详细流程（已按你的要求升级）

1. warmup（热身）
2. task_intro（任务说明）
3. formal_interview（正式面试：自我介绍 + STAR问题）
4. closing（结束语 + reset）

每个阶段中：

- 被试回答来自 ASR（失败时可回退 mock）
- **warmup/formal_interview 阶段优先走 LLM 实时回复**
- **task_intro/closing 阶段固定脚本播报**
- 指标可记录（语速、停顿比、注视占比等）

---

## 阶段 2B：自由对话模式（freechat）详细流程

循环 `N` 轮（`--chat-turns`）：

1. 从 ASR 获取被试当前话语（`stage=free_chat`）
2. 将话语发给 LLM 生成简短回复
3. NAO `speak` 播报回复
4. 进入下一轮

结束后 NAO 播报结束语。

---

## 5. 你现在这句“是不是已经可以实时对话”——准确回答

**是，可以。**

但要满足以下前提：

1. Python2 command server 可达；
2. ASR 推送正常（且词表/识别策略能覆盖自然句）；
3. LLM key 有效，外网可访问 DeepSeek；
4. 以 `--dialogue-mode interview --use-llm`（四阶段混合模式）或 `--dialogue-mode freechat`（纯自由对话）启动。

如果其中某一环断掉，就会出现“有时能说、有时不回”的现象。

---

## 6. 推荐启动命令（Windows / 项目根目录）

> 下面是示例，请替换成你的真实地址与 key。

### A) 你现在最需要的“四阶段混合模式”（推荐）

```bash
python client_py3/run_client_demo.py ^
  --real ^
  --server-url http://127.0.0.1:8000/command ^
  --dialogue-mode interview ^
  --use-llm ^
  --asr-mode realtime ^
  --realtime-host 127.0.0.1 ^
  --realtime-port 8765 ^
  --llm-api-key YOUR_DEEPSEEK_KEY ^
  --llm-model deepseek-chat ^
  --verbose
```

### B) 纯自由对话模式（非四阶段实验）

```bash
python client_py3/run_client_demo.py ^
  --real ^
  --server-url http://127.0.0.1:8000/command ^
  --dialogue-mode freechat ^
  --chat-turns 8 ^
  --asr-mode realtime ^
  --realtime-host 127.0.0.1 ^
  --realtime-port 8765 ^
  --llm-api-key YOUR_DEEPSEEK_KEY ^
  --llm-model deepseek-chat ^
  --verbose
```

> 你之前报错“系统找不到指定文件”，通常是命令执行目录或命令换行符导致。请在项目根目录执行，或使用一行命令。
