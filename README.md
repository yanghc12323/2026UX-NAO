# 2026UX-NAO · NAO Interview Coach

用于高压模拟面试研究的人机交互实验平台。  
采用双端架构：

- **Python3 客户端（client_py3）**：Web控制台、实验流程编排、LLM生成、指标计算、日志记录
- **Python2 机器人端（robot_server_py2）**：NAOqi SDK动作执行、实时ASR/Gaze推送

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

- Web控制台：主试通过网页控制实验流程
- LLM问题/反馈生成（DeepSeek API）
- persona/backchanneling条件化输出
- 指标计算：
  - `speech_rate_cpm`（语速）
  - `disfluency_ratio`（语言不流畅比率）
  - `pause_ratio`（停顿占比）
  - `repetition_ratio`（重复词占比）
  - `self_correction_ratio`（自我修正占比）
  - `fluency_score`（综合流畅度分数）
  - `gaze_contact_ratio`（注视机器人头部占比）
- JSONL结构化日志
- 接收Python2推送器的实时数据（HTTP）

### Python2（`robot_server_py2/`）

- `command_server.py`：`POST /command` 动作执行服务
- `nao_behavior_lib.py`：NAO物理行为封装
- `asr_realtime_pusher.py`：语音识别推送器
- `gaze_realtime_pusher.py`：视线追踪推送器

---

## 3) 环境与位数要求（重要）

### Python3 客户端

- 建议 Python 3.8+
- 在 Windows 上建议显式指定解释器

### Python2 + NAOqi（机器人端）

- 必须 Python 2.7
- **Python 位数与 NAOqi SDK 位数必须一致**

检查Python位数：

```bash
python -c "import struct; print(struct.calcsize('P')*8)"
```

- 输出 `32` → 使用 win32 SDK
- 输出 `64` → 使用 win64 SDK

---

## 4) 快速启动（Web控制台模式）

### Step 1：启动 Python2 动作服务（终端 1）

```bash
cd robot_server_py2
python command_server.py --robot-ip 172.20.10.4 --robot-port 9559 --port 8000
```

> 替换 `--robot-ip` 为实际NAO机器人IP地址

### Step 2：启动 Web 控制台后端（终端 2，Python3）

```bash
cd client_py3
C:\Users\13807\miniconda3\python.exe web_console_server.py --host 127.0.0.1 --port 8780 --robot-server-url http://127.0.0.1:8000/command

```

启动后访问：`http://127.0.0.1:8780`

### Step 3：启动 ASR 推送器（终端 3，Python2）

```bash
cd robot_server_py2
python asr_realtime_pusher.py --robot-ip 172.20.10.4 --robot-port 9559 --client-url http://127.0.0.1:8780/asr --stage warmup
```

可选参数：
- `--vocab-file <path>`：自定义词表文件（UTF-8编码，每行一个词）

### Step 4：启动 Gaze 推送器（终端 4，Python2）

```bash
cd robot_server_py2
python gaze_realtime_pusher.py --robot-ip 172.20.10.4 --robot-port 9559 --client-url http://127.0.0.1:8780/gaze --stage warmup
```

### Step 5：主试在网页执行操作

1. 填写被试编号、姓名
2. 选择条件（C1~C4）
3. 点击「开始会话」
4. 按实验进度点击阶段按钮切换：
   - `warmup`
   - `task_intro`
   - `formal_interview`
   - `closing_and_questionnaire`
5. 实时观察指标和最近事件
   - 顶部「连接状态监控」显示：ASR / Gaze / command_server 状态
   - 任一路异常时，显示红色告警框并弹窗提醒
6. 点击「结束会话并导出」自动生成文件到 `client_py3/exports/`

---

## 5) Web 控制台接口速查

- 页面：`GET /`（或 `/index.html`）
- 健康检查：`GET /api/health`
- 状态轮询：`GET /api/status`
- 开始会话：`POST /api/session/start`
- 结束会话（含自动导出）：`POST /api/session/end`
- 手动导出：`POST /api/session/export`
- 切换阶段：`POST /api/stage`
- 接收实时数据：`POST /asr`、`POST /gaze`
- 转发机器人命令：`POST /api/robot/command`

---

## 6) 常见问题（FAQ）

### Q1: `DLL load failed: %1 不是有效的 Win32 应用程序`

原因：Python2 与 NAOqi SDK 位数不一致。

修复：
- 32-bit Python2 搭配 win32 SDK
- 64-bit Python2 搭配 win64 SDK

### Q2: `command_server.py` 启动时中文日志崩溃

已修复为 ASCII 日志；若仍遇编码问题，优先在 `cmd` 终端运行。

### Q3: 推送器连接失败

- 确认 NAO 与实验机同网段
- 确认 Web 控制台已启动：`127.0.0.1:8780`
- 确认 URL 路径正确：`/asr`、`/gaze`

### Q4: 网页出现连接告警

按顺序排查：

1. **command_server 异常**
   - 确认 `command_server.py` 已启动
   - 确认 `--robot-server-url` 正确

2. **ASR 异常**
   - 确认 `asr_realtime_pusher.py` 正在运行
   - 确认 `--client-url` 指向 `http://127.0.0.1:8780/asr`

3. **Gaze 异常**
   - 确认 `gaze_realtime_pusher.py` 正在运行
   - 确认 `--client-url` 指向 `http://127.0.0.1:8780/gaze`

---

## 7) 仓库结构

```text
nao_interview_coach/
├── client_py3/
│   ├── web_console_server.py
│   ├── web_console/
│   │   └── index.html
│   ├── exports/
│   └── client/
│       ├── llm_provider.py
│       ├── llm_interview_provider.py
│       ├── interview_policy.py
│       ├── metrics.py
│       └── ...
├── robot_server_py2/
│   ├── command_server.py
│   ├── nao_behavior_lib.py
│   ├── asr_realtime_pusher.py
│   ├── gaze_realtime_pusher.py
│   └── setup_naoqi_env.bat
└── docs/
    ├── communication_protocol_v1.md
    ├── experiment_condition_matrix_and_operationalization.md
    └── realtime_http_integration_guide.md
```

---

## 8) 文档索引

- 协议定义：`docs/communication_protocol_v1.md`
- 条件矩阵与操作化：`docs/experiment_condition_matrix_and_operationalization.md`
- 实时集成指南：`docs/realtime_http_integration_guide.md`

---

## 9) 代码审查状态

**最近审查日期**：2026年4月28日

**审查结果**：
- ✅ 0个严重错误
- ✅ 所有核心功能正常
- ✅ 错误处理完善
- ✅ 线程安全
- ✅ 编码处理稳健（Python2中文兼容）

**已修复问题**：
- 修复 `gaze_realtime_pusher.py` 重复import语句

**代码质量**：良好，可安全运行

---

## 10) 安全与提交建议

- 不要提交 API Key 或真实被试隐私数据
- 若 key 泄露，立即旋转
- 提交前建议：

```bash
git status
git diff -- . ':!*.pptx' ':!*.zip'
```
