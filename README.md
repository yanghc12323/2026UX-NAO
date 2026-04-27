# 2026UX-NAO · NAO Interview Coach

用于高压模拟面试研究的人机交互实验平台。  
采用双端架构：

- **Python3 客户端（client_py3）**：实验流程编排、LLM 生成、指标计算、日志记录
- **Python2 机器人端（robot_server_py2）**：NAOqi SDK 动作执行、实时 ASR/Gaze 推送

---

## 1) 实验目标与条件设计

核心 2×2 条件：

- Persona：`encouraging` / `pressure`
- Backchanneling：`positive` / `negative`

实验阶段（固定四段）：

1. `warmup`
2. `task_intro`
3. `formal_interview`（施加条件）
4. `closing_and_questionnaire`

---

## 2) 总体架构

### Python3（`client_py3/`）

- 会话状态机与阶段推进
- LLM 问题/反馈生成（支持 DeepSeek，OpenAI-compatible）
- persona/backchanneling 条件化输出
- 指标计算：
  - `speech_rate_cpm`（语速）
  - `disfluency_ratio`（语言流畅性）
  - `gaze_contact_ratio`（注视机器人头部占比）
- JSONL 结构化日志：`stage_event` / `metric_event` / `action_event`
- 接收 Python2 推送器的实时数据（HTTP）

### Python2（`robot_server_py2/`）

- `command_server.py`：`POST /command` 动作执行服务
- `nao_behavior_lib.py`：NAO 物理行为封装
- `asr_realtime_pusher.py`：语音识别推送器
- `gaze_realtime_pusher.py`：视线追踪推送器

---

## 3) 当前项目完成度（代码层）

### 已完成

- Python3 客户端主链路可运行（mock / real / realtime）
- Python3 已具备可插拔输入模式：`mock/jsonl/realtime`
- Python3 已具备实时 HTTP 接收桥（默认 8765）
- Python2 `command_server` 已支持 canonical 命令路由：
  - `ping/speak/nod/gaze/reset_posture/gesture/perform_sequence`
- Python2 保留 legacy 兼容命令：
  - `shake_head/stare/avert_gaze/reset_gaze/rest`
- Python2 近期已修复控制台编码导致的启动崩溃（启动日志改为 ASCII）
- 已新增 Web 实验控制台：`client_py3/web_console_server.py`
  - 主试可在网页录入被试编号/姓名、选择 2×2 条件
  - 可手动切换四个实验阶段
  - 可实时查看 ASR/Gaze 驱动的指标（语速/流畅性/注视比例等）
  - 内置连接健康监控与告警（ASR/Gaze 推送、command_server 可达性）
  - 会话结束自动导出被试数据（优先 `.xlsx`，失败回退 `.csv`）

### 仍需实验联调/参数校准（非框架缺失）

- 真实 NAO 动作时序、姿态细节校准
- ASR/Gaze 实时阈值与稳定性校准
- backchannel 触发频率与时机调优

---

## 4) 环境与位数要求（重要）

### Python3 客户端

- 建议 Python 3.8+
- 在 Windows 上建议显式指定解释器（避免调用到 Python2）

### Python2 + NAOqi（机器人端）

- 必须 Python 2.7
- **Python 位数与 NAOqi SDK 位数必须一致**

你当前已确认：

- `.venv27` 是 **32-bit Python2.7**
- 若 SDK 路径为 `...win64...` 则会出现：
  `ImportError: DLL load failed: %1 不是有效的 Win32 应用程序`

即：**32-bit Python + 64-bit SDK 不兼容**。

---

## 5) 快速启动

> 以下示例均为 Windows。

### 5.1 Python3 客户端（Mock）

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --verbose
```

### 5.2 Python2 动作服务

```bash
cd robot_server_py2
python command_server.py
```

### 5.3 Web 控制台模式（推荐主试使用）

> 若希望主试通过网页控制实验（而不是命令行输入被试信息/条件/阶段），按本节执行。

#### Step 1：启动 Python2 动作服务（终端 1，可选但推荐）

```bash
cd robot_server_py2
python command_server.py
```

> 用途：Web 控制台可以把动作命令转发到 `POST /command`。

#### Step 2：启动 Web 控制台后端（终端 2，Python3）

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe web_console_server.py --host 127.0.0.1 --port 8780 --robot-server-url http://127.0.0.1:8000/command
```

启动后访问：`http://127.0.0.1:8780`

#### Step 3：启动 ASR / Gaze 推送器并指向 Web 控制台（终端 3/4，Python2）

ASR：

```bash
cd robot_server_py2
python asr_realtime_pusher.py --robot-ip 192.168.93.152 --client-url http://127.0.0.1:8780/asr --stage warmup
```

Gaze：

```bash
cd robot_server_py2
python gaze_realtime_pusher.py --robot-ip 192.168.93.152 --client-url http://127.0.0.1:8780/gaze --stage warmup --push-interval 2.0
```

#### Step 4：主试在网页执行操作

1. 填写被试编号、姓名
2. 选择条件（C1~C4）
3. 点击「开始会话」
4. 按实验进度点击阶段按钮切换：
   - `warmup`
   - `task_intro`
   - `formal_interview`
   - `closing_and_questionnaire`
5. 实时观察指标和最近事件
   - 顶部「连接状态监控」会显示：ASR / Gaze / command_server 的正常或异常状态
   - 任一路异常时，会显示红色告警框并弹窗提醒主试
6. 点击「结束会话并导出」自动生成文件到 `client_py3/exports/`

---

### 5.4 实时实验模式（CLI 客户端模式，保留）

> 这是明天正式实验的主流程。请严格按顺序执行：
> **终端1（Python3客户端）→ 终端2（ASR推送器）→ 终端3（Gaze推送器）**。

#### Step 0：实验前检查（2分钟）

1. NAO 已开机，和实验电脑在同一局域网。
2. 记录机器人 IP（示例：`192.168.93.152`，下面命令中的 `--robot-ip` 必须替换为当天实际 IP）。
3. 确认 Python3 解释器可用（客户端）。
4. 确认 Python2 + NAOqi 位数匹配（推送器）：

```bash
python -c "import struct; print(struct.calcsize('P')*8)"
```

若输出 `32`，则 NAOqi SDK 必须是 win32；若输出 `64`，则必须用 win64。

---

#### Step 1：启动 Python3 客户端（终端 1）

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe run_client_demo.py --real --asr-mode realtime --gaze-mode realtime --persona-style encouraging --backchanneling-type positive --verbose
```

看到类似以下信息再进行下一步：

- HTTP 接收服务已启动（`127.0.0.1:8765`）
- 进入 `warmup` 阶段

---

#### Step 2：启动 ASR 推送器（终端 2，Python2）

```bash
cd robot_server_py2
python asr_realtime_pusher.py --robot-ip 192.168.93.152 --client-url http://127.0.0.1:8765/asr --stage warmup
```

预期现象：

- 显示已连接 NAO 语音识别服务
- 显示已订阅 `WordRecognized`
- 终端持续运行（不要关闭）

---

#### Step 3：启动 Gaze 推送器（终端 3，Python2）

```bash
cd robot_server_py2
python gaze_realtime_pusher.py --robot-ip 192.168.93.152 --client-url http://127.0.0.1:8765/gaze --stage warmup --push-interval 2.0
```

预期现象：

- 显示已连接 NAO 人脸检测服务
- 显示已订阅 `FaceDetected`
- 每隔一段时间推送 gaze 数据

---

#### Step 4：联通性确认（重点）

回到终端 1（客户端），应能看到：

- 收到 ASR 推送（文本、置信度、stage）
- 收到 Gaze 推送（gaze_contact_s、stage）
- 指标持续更新（语速/流畅性/注视比例）

如果终端 1 完全收不到数据：

1. 先检查 `--client-url` 是否写成 `http://127.0.0.1:8765/asr` 与 `http://127.0.0.1:8765/gaze`
2. 确认终端 1 比终端 2/3 先启动
3. 检查 `--robot-ip` 是否为当天真实 IP

---

#### Step 5：实验条件切换（2×2）

客户端命令里改这两个参数即可：

- `--persona-style encouraging|pressure`
- `--backchanneling-type positive|negative`

示例（压力型 + 消极反馈）：

```bash
C:\Users\13807\miniconda3\python.exe run_client_demo.py --real --asr-mode realtime --gaze-mode realtime --persona-style pressure --backchanneling-type negative --verbose
```

---

#### Step 6：收尾与日志

实验结束后按顺序停止：

1. 先停推送器（终端2、3，`Ctrl+C`）
2. 再停客户端（终端1）

若启用了日志参数（`--enable-logging --log-dir logs`），请备份日志目录用于后续分析。

---

## 6) Web 控制台接口速查

- 页面：`GET /`（或 `/index.html`）
- 健康检查：`GET /api/health`
- 状态轮询：`GET /api/status`
  - 包含 `connectivity` 字段：
    - `asr`（最后接收时间、超时判定）
    - `gaze`（最后接收时间、超时判定）
    - `command_server`（后台 ping 可达性探测）
    - `warnings`（面向主试的告警文案）
- 开始会话：`POST /api/session/start`
- 结束会话（含自动导出）：`POST /api/session/end`
- 手动导出：`POST /api/session/export`
- 切换阶段：`POST /api/stage`
- 接收实时数据：`POST /asr`、`POST /gaze`
- 转发机器人命令：`POST /api/robot/command`

---

## 7) 常见问题（FAQ）

### Q1: `DLL load failed: %1 不是有效的 Win32 应用程序`

原因：Python2 与 NAOqi SDK 位数不一致（最常见）。

排查：

```bash
python -c "import struct; print(struct.calcsize('P')*8)"
```

修复：

- 32-bit Python2 搭配 win32 SDK
- 64-bit Python2 搭配 win64 SDK

### Q2: `command_server.py` 启动时中文日志崩溃

已在仓库中修复为 ASCII 日志；若仍遇编码问题，优先在 `cmd` 终端运行。

### Q3: 推送器连接失败

- 确认 NAO 与实验机同网段
- 确认接收端已启动：
  - Web 控制台模式：`127.0.0.1:8780`
  - CLI 客户端模式：`127.0.0.1:8765`
- 确认 URL 路径正确：`/asr`、`/gaze`

### Q4: 网页出现连接告警（ASR/Gaze/command_server 异常）

先看页面「连接状态监控」中的具体提示，再按顺序排查：

1. **command_server 异常**
   - 确认 `robot_server_py2/command_server.py` 已启动
   - 确认 Web 启动参数 `--robot-server-url` 正确（默认 `http://127.0.0.1:8000/command`）
2. **ASR 异常**
   - 确认 `asr_realtime_pusher.py` 正在运行
   - 确认 `--client-url` 指向 `http://127.0.0.1:8780/asr`
3. **Gaze 异常**
   - 确认 `gaze_realtime_pusher.py` 正在运行
   - 确认 `--client-url` 指向 `http://127.0.0.1:8780/gaze`

说明：当前默认策略是 **10 秒未收到数据即判定 ASR/Gaze 超时**，因此推送中断时主试会快速收到提醒。

---

## 8) 仓库结构

```text
nao_interview_coach/
├── client_py3/
│   ├── run_client_demo.py
│   ├── web_console_server.py
│   ├── web_console/
│   │   └── index.html
│   ├── data/
│   └── client/
├── robot_server_py2/
│   ├── command_server.py
│   ├── nao_behavior_lib.py
│   ├── asr_realtime_pusher.py
│   ├── gaze_realtime_pusher.py
│   └── setup_naoqi_env.bat
└── docs/
    ├── communication_protocol_v1.md
    ├── experiment_condition_matrix_and_operationalization.md
    ├── realtime_http_integration_guide.md
    └── handover_for_next_developer.md
```

---

## 9) 文档索引

- 协议定义：`docs/communication_protocol_v1.md`
- 条件矩阵与操作化：`docs/experiment_condition_matrix_and_operationalization.md`
- 实时集成指南：`docs/realtime_http_integration_guide.md`
- 交接文档：`docs/handover_for_next_developer.md`

---

## 10) 安全与提交建议

- 不要提交 API Key 或真实被试隐私数据
- 若 key 泄露，立即旋转
- 提交前建议：

```bash
git status
git diff -- . ':!*.pptx' ':!*.zip'
```
