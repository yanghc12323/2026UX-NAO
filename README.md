# 2026UX-NAO

## NAO Interview Coach

用于高压模拟面试研究的人机交互项目仓库。

本仓库当前聚焦两部分：
- `client_py3/`：Python3 决策层客户端（已可运行，支持 DeepSeek）
- `robot_server_py2/`：Python2 机器人执行层占位（当前仅示例 `Demo.py`）

## 0. 能力边界（截至当前版本）

- ✅ 已具备：`Python3(流程/LLM)` -> `Python2(动作执行)` 的命令链路骨架
- ✅ 已具备：LLM 生成问题与反馈（可按 persona/backchanneling 切换）
- ✅ 已具备：HTTP 实时推送模式，支持外部 ASR/Gaze 进程推送数据到客户端
- ✅ 已具备：三项客观指标自动化计算（语速、流畅性、注视比例）
- ⚠️ 需配置：真实 NAO 机器人环境下的 ASR/Gaze 推送器（已提供 Python2 示例脚本）
- ⚠️ 待完善：Python2 服务端的动作执行接口（`POST /command`）

> 推荐职责划分：
> - Python3：实验流程编排、ASR/视觉分析、指标计算、日志落盘、LLM 决策
> - Python2：NAO 硬件动作执行与设备连接稳定性

## 1. 当前状态（给歌晴）

- ✅ Python3 客户端主链路已跑通（Mock 模式 + 实时推送模式）
- ✅ 已接入 DeepSeek（OpenAI-compatible Chat Completions）
- ✅ 已支持 2×2 实验条件：
  - Persona：`encouraging` / `pressure`
  - Backchanneling：`positive` / `negative`
- ✅ 已支持 HTTP 实时推送模式接收 ASR/Gaze 数据
- ✅ 已提供 Python2 推送器示例（`robot_server_py2/asr_realtime_pusher.py` 等）
- ⏳ 真实机器人端动作执行（Python2 + NAO SDK）由后续同学继续接手完善

## 2. 快速开始

> Windows 下如系统默认 `python` 为 2.7，请显式使用 Python3 可执行文件。

### 2.1 进入客户端目录并运行（Mock）

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --verbose
```

### 2.2 启用 DeepSeek

```powershell
$env:DEEPSEEK_API_KEY="你的DeepSeek_API_Key"
```

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --use-llm --persona-style encouraging --backchanneling-type positive --verbose
```

## 3. 文档索引

- **Python3 客户端说明**：`client_py3/README.md`
- **HTTP 实时推送集成指南**：`docs/realtime_http_integration_guide.md`（重要！）
- **通信协议**：`docs/communication_protocol_v1.md`
- **实验条件矩阵**：`docs/experiment_condition_matrix_and_operationalization.md`
- **交接说明**：`docs/handover_for_next_developer.md`

## 4. 目标实验流程（文档对齐版）

1. **Warmup（中立）**：生活化闲聊 + 基线数据采集（语速/流利度/视线接触）
2. **任务引入**：说明面试背景、规则与时长
3. **正式面试**：1 分钟自我介绍（用于用户画像）+ 3~4 个 STAR 行为题
4. **结束与问卷**：宣布结束并引导联系主试填写问卷

上述流程已写入 docs 文档，用于后续按阶段实现。

## 5. 安全与开源注意事项

- 不要在代码、文档、commit 中提交任何 API Key。
- 若曾在聊天或终端记录中暴露 key，请立即在平台控制台旋转/作废。
- 建议提交前执行：

```bash
git status
git diff -- . ':!*.pptx' ':!*.zip'
```

确保没有误提交大型临时文件或敏感信息。
