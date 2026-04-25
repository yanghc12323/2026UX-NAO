# 交接说明（给下一位同学）

## 1. 你将接手什么

当前仓库已经完成 **Python3 客户端主链路**，位置：`client_py3/`。

已完成能力：
- 协议请求封装（CommandClient / ActionAdapter）
- Mock 联调流程（无需机器人）
- DeepSeek LLM 接入
- 2×2 实验条件参数化：
  - persona: `encouraging` / `pressure`
  - backchanneling: `positive` / `negative`

## 2. 当前未完成部分（你主要要做的）

1. **Python2 机器人服务端完善**（`robot_server_py2/`）
   - 当前仅 `Demo.py`，尚未形成完整 `POST /command` 服务。
2. **NAO SDK 与真实设备联调**
   - 对接 `speak / nod / gaze / reset_posture` 等指令。
3. **端到端 real 模式验收**
   - 目标：`client_py3 --real` 在真实 server 下稳定运行。

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

## 4. 重要文件导航

- 客户端入口：`client_py3/run_client_demo.py`
- LLM 调用层：`client_py3/client/llm_provider.py`
- 实验条件策略：`client_py3/client/interview_policy.py`
- Prompt 模板：`client_py3/client/prompt_templates.py`
- 客户端使用说明：`client_py3/README.md`
- 快速文档：`docs/python3_client_quickstart.md`
- 协议文档：`docs/communication_protocol_v1.md`
- 实验矩阵：`docs/experiment_condition_matrix_and_operationalization.md`

## 5. 安全提醒

- 不要提交 API key 到仓库。
- 若 key 曾泄露，先旋转再继续开发。
- 提交前检查：

```bash
git status
git diff
```
