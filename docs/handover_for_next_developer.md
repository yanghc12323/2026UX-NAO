# 交接说明（给歌晴）

> 更新时间：基于当前“文档对齐版”实验目标（warmup -> task_intro -> formal_interview -> closing_and_questionnaire）

## 1. 你将接手什么

当前仓库已经完成 **Python3 客户端主链路**，位置：`client_py3/`。

已完成能力：
- 协议请求封装（CommandClient / ActionAdapter）
- Mock 联调流程（无需机器人）
- DeepSeek LLM 接入
- 2×2 实验条件参数化：
  - persona: `encouraging` / `pressure`
  - backchanneling: `positive` / `negative`
- 4阶段实验流程（`warmup -> task_intro -> formal_interview -> closing_and_questionnaire`）
- 输入采集抽象（`ASRProvider` + mock/jsonl/realtime 模式）
- **HTTP 实时推送模式**（`RealtimeASRProvider` + `RealtimeGazeProvider`）
- Python2 推送器示例（`robot_server_py2/asr_realtime_pusher.py` 和 `gaze_realtime_pusher.py`）
- 三项指标计算模块（语速/流畅性/注视比例）
- 结构化日志落盘（`stage_event/metric_event/action_event`）

当前明确边界：
- ✅ 有：LLM 生成问题与反馈 + 动作命令下发 + 4阶段流程 + 指标与日志框架 + HTTP 实时推送模式
- ⚠️ 仍待：Python2 服务端的 `/command` 接口实现（对接 NAO SDK 动作执行）

## 2. 当前未完成部分（你主要要做的）

1. **Python2 机器人服务端完善**（`robot_server_py2/`）
   - 当前仅 `Demo.py`，尚未形成完整 `POST /command` 服务。
   - 需实现：接收 Python3 客户端的命令请求，调用 NAO SDK 执行动作，返回标准响应。
   
2. **NAO SDK 与真实设备联调**
   - 对接 `speak / nod / gaze / reset_posture` 等指令。
   - 确保错误码与协议文档对齐。
   
3. **端到端 real 模式验收**
   - 目标：`client_py3 --real --asr-mode realtime --gaze-mode realtime` 在真实环境下稳定运行。
   - 验证 Python2 推送器（ASR/Gaze）-> Python3 客户端 -> Python2 服务端 -> NAO 机器人的完整链路。
   
4. **真实设备实验参数校准**
   - 校准 `positive/negative` backchannel 的触发频率与时延。
   - 对齐实验记录字段与后续统计脚本。

## 3. 建议你先跑通的最小链路

1) 在 Python2 server 侧先实现：
- `ping`
- `speak`
- `nod`
- `gaze`
- `reset_posture`

2) 返回结构严格对齐：`docs/communication_protocol_v1.md`

3) 用客户端验证：

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --real --server-url http://127.0.0.1:8000/command --use-llm --persona-style encouraging --backchanneling-type positive --verbose --fail-fast
```

4) 再进入真实信号联调（建议顺序）
- **推荐方式**：使用 HTTP 实时推送模式（`--asr-mode realtime --gaze-mode realtime`）
  - 启动 Python3 客户端（会自动启动 HTTP 服务器监听 8765 端口）
  - 启动 Python2 ASR 推送器：`python asr_realtime_pusher.py`
  - 启动 Python2 Gaze 推送器：`python gaze_realtime_pusher.py`
  - 详细说明：`docs/realtime_http_integration_guide.md`
- 验证 `stage_event/metric_event/action_event` 的字段完整性。
- 最后校准条件化参数（formal 阶段 persona/backchanneling 强度）。

## 4. 重要文件导航

### Python3 客户端
- 客户端入口：`client_py3/run_client_demo.py`
- LLM 调用层：`client_py3/client/llm_interview_provider.py`
- Prompt 模板：`client_py3/client/prompt_templates.py`
- 会话流程：`client_py3/client/session_flow.py`
- 输入采集：`client_py3/client/input_provider.py`
- 视线估计：`client_py3/client/gaze_provider.py`
- 实时桥接：`client_py3/client/realtime_bridge.py`
- 指标计算：`client_py3/client/metrics.py`
- 日志记录：`client_py3/client/experiment_logger.py`

### Python2 推送器（示例）
- ASR 推送器：`robot_server_py2/asr_realtime_pusher.py`
- Gaze 推送器：`robot_server_py2/gaze_realtime_pusher.py`
- 环境配置：`robot_server_py2/setup_naoqi_env.bat`

### 文档
- **客户端使用说明**：`client_py3/README.md`
- **HTTP 实时推送集成指南**：`docs/realtime_http_integration_guide.md`（重要！）
- **协议文档**：`docs/communication_protocol_v1.md`
- **实验矩阵**：`docs/experiment_condition_matrix_and_operationalization.md`

建议先读文档顺序：
1. `docs/experiment_condition_matrix_and_operationalization.md`（了解实验设计）
2. `docs/communication_protocol_v1.md`（了解通信协议）
3. `docs/realtime_http_integration_guide.md`（了解实时推送模式）
4. `client_py3/README.md`（了解客户端使用）

## 5. 安全提醒

- 不要提交 API key 到仓库。
- 若 key 曾泄露，先旋转再继续开发。
- 提交前检查：

```bash
git status
git diff
```
