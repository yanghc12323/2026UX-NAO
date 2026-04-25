# NAO Interview Coach

用于高压模拟面试研究的人机交互项目仓库。

本仓库当前聚焦两部分：
- `client_py3/`：Python3 决策层客户端（已可运行，支持 DeepSeek）
- `robot_server_py2/`：Python2 机器人执行层占位（当前仅示例 `Demo.py`）

## 1. 当前状态（给 GitHub 读者）

- ✅ Python3 客户端主链路已跑通（Mock 模式）
- ✅ 已接入 DeepSeek（OpenAI-compatible Chat Completions）
- ✅ 已支持 2×2 实验条件：
  - Persona：`encouraging` / `pressure`
  - Backchanneling：`positive` / `negative`
- ⏳ 真实机器人端（Python2 + NAO SDK）由后续同学继续接手完善

## 2. 快速开始

> Windows 下如系统默认 `python` 为 2.7，请显式使用 Python3 可执行文件。

### 2.1 进入客户端目录并运行（Mock）

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --verbose
```

### 2.2 启用 DeepSeek

```powershell
$env:DEEPSEEK_API_KEY="sk-768a6e0f68494b5f9ad551ae9c6398d2"
```

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --use-llm --persona-style encouraging --backchanneling-type positive --verbose
```

## 3. 文档索引

- Python3 客户端说明：`client_py3/README.md`
- Python3 快速使用：`docs/python3_client_quickstart.md`
- 通信协议：`docs/communication_protocol_v1.md`
- 实验条件矩阵：`docs/experiment_condition_matrix_and_operationalization.md`
- 交接说明：`docs/handover_for_next_developer.md`

## 4. 安全与开源注意事项

- 不要在代码、文档、commit 中提交任何 API Key。
- 若曾在聊天或终端记录中暴露 key，请立即在平台控制台旋转/作废。
- 建议提交前执行：

```bash
git status
git diff -- . ':!*.pptx' ':!*.zip'
```

确保没有误提交大型临时文件或敏感信息。
