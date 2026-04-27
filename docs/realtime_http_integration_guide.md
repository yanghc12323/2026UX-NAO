# NAO 实时 HTTP 推送集成指南

> 版本：v1.0  
> 日期：2026-04-25  
> 适用场景：正式实验环境，使用 NAO SDK 进行实时 ASR 和视线追踪

---

## 1. 架构概览

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      实验环境                                 │
│                                                              │
│  ┌──────────────┐         ┌──────────────┐                 │
│  │  NAO 机器人   │         │  实验电脑     │                 │
│  │              │         │              │                 │
│  │  - 语音识别  │◄────────┤  Python 2.7  │                 │
│  │  - 人脸检测  │  NAOqi  │              │                 │
│  │  - 动作执行  │  SDK    │  ┌─────────┐ │                 │
│  └──────────────┘         │  │ ASR推送器│ │                 │
│                           │  └────┬────┘ │                 │
│                           │       │HTTP  │                 │
│                           │  ┌────▼────┐ │                 │
│                           │  │Gaze推送器│ │                 │
│                           │  └────┬────┘ │                 │
│                           └───────┼──────┘                 │
│                                   │                         │
│                                   │ HTTP POST               │
│                                   │                         │
│                           ┌───────▼──────┐                 │
│                           │  Python 3.x  │                 │
│                           │              │                 │
│                           │  ┌─────────┐ │                 │
│                           │  │HTTP服务器│ │                 │
│                           │  │(8765端口)│ │                 │
│                           │  └────┬────┘ │                 │
│                           │       │      │                 │
│                           │  ┌────▼────┐ │                 │
│                           │  │ 客户端  │ │                 │
│                           │  │ - LLM   │ │                 │
│                           │  │ - 指标  │ │                 │
│                           │  │ - 日志  │ │                 │
│                           │  └─────────┘ │                 │
│                           └──────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 数据流向

1. **ASR 数据流**：
   - NAO 麦克风 → ALSpeechRecognition → ASR推送器 → HTTP POST → Python3客户端

2. **Gaze 数据流**：
   - NAO 摄像头 → ALFaceDetection → Gaze推送器 → HTTP POST → Python3客户端

3. **动作控制流**：
   - Python3客户端 → HTTP POST → Python2服务端 → NAO动作执行

---

## 2. 环境准备

### 2.1 Python 2.7 环境（用于 NAO SDK）

```bash
# 1. 确认 Python 2.7 已安装
python --version  # 应显示 Python 2.7.x

# 2. 配置 NAOqi SDK
# 将 SDK 路径添加到 PYTHONPATH
set PYTHONPATH=D:\path\to\pynaoqi-python2.7-2.8.6.23-win64-vs2015-20191127_152649\lib;%PYTHONPATH%

# 或在脚本中添加：
import sys
sys.path.append(r"D:\path\to\pynaoqi-python2.7-2.8.6.23-win64-vs2015-20191127_152649\lib")
```

### 2.2 Python 3.x 环境（用于客户端）

```bash
# 确认 Python 3 已安装
python3 --version  # 应显示 Python 3.7+

# 安装依赖（如果还没安装）
cd client_py3
pip install -r requirements.txt
```

### 2.3 NAO 机器人准备

1. **开机并连接网络**
   - 按下 NAO 胸前按钮，等待启动完成
   - 确保 NAO 和实验电脑在同一局域网

2. **获取 NAO IP 地址**
   - 方法1：按一下胸前按钮，NAO 会语音报告 IP
   - 方法2：使用 Choregraphe 软件扫描
   - 示例：`192.168.93.152`

3. **测试连接**
   ```python
   # test_connection.py
   from naoqi import ALProxy
   
   robot_ip = "192.168.93.152"
   robot_port = 9559
   
   try:
       tts = ALProxy("ALTextToSpeech", robot_ip, robot_port)
       tts.say("Connection successful")
       print("连接成功！")
   except Exception as e:
       print("连接失败: %s" % str(e))
   ```

---

## 3. 启动流程（正式实验）

### 3.1 启动顺序

**重要：必须按以下顺序启动，否则会出现连接错误！**

```
1. Python3 客户端（启动 HTTP 服务器）
   ↓
2. ASR 推送器（连接 NAO 并推送数据）
   ↓
3. Gaze 推送器（连接 NAO 并推送数据）
```

### 3.2 详细启动步骤

#### 步骤 1：启动 Python3 客户端

```bash
# 在终端 1 中运行
cd client_py3

python run_client_demo.py \
  --real \
  --asr-mode realtime \
  --gaze-mode realtime \
  --persona-style encouraging \
  --backchanneling-type positive \
  --verbose
```

**参数说明**：
- `--real`: 使用真实机器人（非 mock）
- `--asr-mode realtime`: 使用 HTTP 实时推送接收 ASR 数据
- `--gaze-mode realtime`: 使用 HTTP 实时推送接收 Gaze 数据
- `--persona-style`: 人格类型（encouraging 或 pressure）
- `--backchanneling-type`: 反馈类型（positive 或 negative）

**预期输出**：
```
============================================================
NAO 面试教练客户端
============================================================
模式: 真实机器人
Persona: encouraging
Backchannel: positive
被试ID: P001
条件ID: C1
============================================================

[INFO] HTTP 服务器已启动: http://127.0.0.1:8765
[INFO] 等待 ASR/Gaze 推送器连接...
```

#### 步骤 2：启动 ASR 推送器

```bash
# 在终端 2 中运行（使用 Python 2.7）
cd robot_server_py2

python asr_realtime_pusher.py \
  --robot-ip 192.168.93.152 \
  --client-url http://127.0.0.1:8765/asr \
  --stage warmup
```

**预期输出**：
```
============================================================
NAO 实时语音识别推送器
============================================================
NAO 机器人: 192.168.93.152:9559
客户端 URL: http://127.0.0.1:8765/asr
初始阶段: warmup
============================================================

[INFO] 本地 Broker 已创建
[INFO] 成功连接到 NAO 语音识别服务
[INFO] 语音识别配置完成
[INFO] 词汇表大小: 15
[INFO] 已订阅 WordRecognized 事件
[INFO] ASR 推送器已创建
[INFO] 语音识别已启动

[INFO] 推送器运行中... 按 Ctrl+C 停止
```

#### 步骤 3：启动 Gaze 推送器

```bash
# 在终端 3 中运行（使用 Python 2.7）
cd robot_server_py2

python gaze_realtime_pusher.py \
  --robot-ip 192.168.93.152 \
  --client-url http://127.0.0.1:8765/gaze \
  --stage warmup \
  --push-interval 2.0
```

**预期输出**：
```
============================================================
NAO 实时视线追踪推送器
============================================================
NAO 机器人: 192.168.93.152:9559
客户端 URL: http://127.0.0.1:8765/gaze
初始阶段: warmup
推送间隔: 2.0 秒
============================================================

[INFO] 本地 Broker 已创建
[INFO] 成功连接到 NAO 人脸检测服务
[INFO] 人脸检测配置完成
[INFO] 已订阅 FaceDetected 事件
[INFO] Gaze 推送器已创建
[INFO] 人脸检测已启动

[INFO] 推送器运行中... 按 Ctrl+C 停止
```

### 3.3 验证连接

在 Python3 客户端的终端中，应该看到：

```
[INFO] 收到 ASR 数据: text=你好 confidence=0.85 stage=warmup
[INFO] 收到 Gaze 数据: gaze_contact_s=3.2 stage=warmup
```

---

## 4. 实验流程控制

### 4.1 阶段切换

实验分为 4 个阶段，Python3 客户端会自动切换。但如果需要手动同步阶段到推送器：

**方式 1：重启推送器（推荐）**
```bash
# 停止当前推送器（Ctrl+C）
# 重新启动并指定新阶段
python asr_realtime_pusher.py --robot-ip 192.168.93.152 --stage formal_interview
python gaze_realtime_pusher.py --robot-ip 192.168.93.152 --stage formal_interview
```

**方式 2：动态切换（需要扩展代码）**
- 可以通过 HTTP 接口向推送器发送阶段切换命令
- 或使用共享文件/Redis 等机制同步阶段

### 4.2 实验阶段说明

| 阶段 | 英文名称 | 持续时间 | Persona | 说明 |
|------|---------|---------|---------|------|
| 热身 | warmup | 2-3分钟 | neutral | 中立态度，建立信任 |
| 任务介绍 | task_intro | 1-2分钟 | neutral | 说明面试规则 |
| 正式面试 | formal_interview | 10-15分钟 | 条件化 | 根据分组展现不同 persona |
| 结束问卷 | closing_and_questionnaire | 3-5分钟 | neutral | 感谢并引导问卷 |

---

## 5. 数据格式规范

### 5.1 ASR 推送数据格式

**推送端点**：`POST http://127.0.0.1:8765/asr`

**请求体**：
```json
{
  "text": "我在上一个项目中负责后端开发",
  "speech_duration_s": 8.3,
  "confidence": 0.85,
  "stage": "formal_interview",
  "timestamp_ms": 1714012345678
}
```

**字段说明**：
- `text`（必需）：识别的文本内容
- `speech_duration_s`（必需）：语音时长（秒）
- `confidence`（可选）：识别置信度（0.0-1.0）
- `stage`（推荐）：当前阶段，用于客户端验证
- `timestamp_ms`（推荐）：时间戳（毫秒）

**响应**：
```json
{
  "ok": true
}
```

### 5.2 Gaze 推送数据格式

**推送端点**：`POST http://127.0.0.1:8765/gaze`

**请求体**：
```json
{
  "gaze_contact_s": 5.2,
  "stage": "formal_interview",
  "timestamp_ms": 1714012345678
}
```

**字段说明**：
- `gaze_contact_s`（必需）：累计注视时长（秒）
- `stage`（推荐）：当前阶段
- `timestamp_ms`（推荐）：时间戳（毫秒）

**响应**：
```json
{
  "ok": true
}
```

---

## 6. 常见问题排查

### 6.1 连接问题

**问题：ASR/Gaze 推送器无法连接到 NAO**

```
[ERROR] 连接 NAO 失败: timed out
```

**解决方案**：
1. 检查 NAO IP 地址是否正确
2. 确认 NAO 和电脑在同一网络
3. 尝试 ping NAO IP：`ping 192.168.93.152`
4. 检查防火墙设置
5. 重启 NAO 机器人

---

**问题：推送器无法连接到 Python3 客户端**

```
[ERROR] HTTP 请求失败: Connection refused
```

**解决方案**：
1. 确认 Python3 客户端已启动
2. 检查客户端 URL 是否正确（默认 `http://127.0.0.1:8765`）
3. 确认端口 8765 未被占用
4. 检查防火墙是否阻止本地连接

### 6.2 语音识别问题

**问题：识别率低或无法识别**

**解决方案**：
1. **调整词汇表**：编辑 `asr_realtime_pusher.py` 中的 `vocabulary` 列表
   ```python
   vocabulary = [
       u"项目", u"开发", u"团队", u"负责", u"完成",
       u"学习", u"经验", u"能力", u"挑战", u"解决",
       # 添加更多实验相关词汇
   ]
   ```

2. **调整置信度阈值**：降低 `onWordRecognized` 中的阈值
   ```python
   if confidence < 0.2:  # 从 0.3 降低到 0.2
       return
   ```

3. **检查麦克风**：确保 NAO 麦克风正常工作
   ```python
   # 测试麦克风
   audio = ALProxy("ALAudioDevice", robot_ip, robot_port)
   print(audio.getOutputVolume())
   ```

4. **环境噪音**：减少实验环境的背景噪音

### 6.3 视线追踪问题

**问题：无法检测到人脸或注视判定不准确**

**解决方案**：
1. **调整光照**：确保被试面部光照充足
2. **调整距离**：被试距离 NAO 约 1-2 米
3. **调整阈值**：编辑 `gaze_realtime_pusher.py` 中的参数
   ```python
   # 放宽角度阈值
   alpha_threshold = 0.7  # 从 0.5 增加到 0.7
   beta_threshold = 0.7
   
   # 放宽人脸大小阈值
   min_size_x = 0.10  # 从 0.15 降低到 0.10
   max_size_x = 0.70  # 从 0.60 增加到 0.70
   ```

4. **检查摄像头**：确认 NAO 摄像头正常
   ```python
   # 测试摄像头
   video = ALProxy("ALVideoDevice", robot_ip, robot_port)
   print(video.getCameraName(0))
   ```

### 6.4 性能问题

**问题：推送延迟过高**

**解决方案**：
1. **减少推送频率**：
   ```bash
   # Gaze 推送器
   python gaze_realtime_pusher.py --robot-ip 192.168.93.152 --push-interval 3.0
   ```

2. **优化网络**：确保局域网稳定，避免 WiFi 干扰

3. **减少日志输出**：注释掉 DEBUG 级别的 print 语句

---

## 7. 高级配置

### 7.1 自定义 HTTP 端口

如果端口 8765 被占用，可以修改：

**Python3 客户端**：
```bash
# 修改 run_client_demo.py 中的默认端口
python run_client_demo.py --realtime-port 9000 ...
```

**推送器**：
```bash
python asr_realtime_pusher.py --robot-ip 192.168.93.152 --client-url http://127.0.0.1:9000/asr
python gaze_realtime_pusher.py --robot-ip 192.168.93.152 --client-url http://127.0.0.1:9000/gaze
```

### 7.2 多机器人支持

如果有多个 NAO 机器人，可以为每个机器人启动独立的推送器：

```bash
# 机器人 1
python asr_realtime_pusher.py --robot-ip 192.168.93.152 --broker-port 10001
python gaze_realtime_pusher.py --robot-ip 192.168.93.152 --broker-port 10002

# 机器人 2
python asr_realtime_pusher.py --robot-ip 192.168.93.153 --broker-port 10003
python gaze_realtime_pusher.py --robot-ip 192.168.93.153 --broker-port 10004
```

### 7.3 日志记录

**启用详细日志**：
```python
# 在推送器脚本开头添加
import logging
logging.basicConfig(level=logging.DEBUG)
```

**保存日志到文件**：
```bash
python asr_realtime_pusher.py --robot-ip 192.168.93.152 > asr_log.txt 2>&1
python gaze_realtime_pusher.py --robot-ip 192.168.93.152 > gaze_log.txt 2>&1
```

---

## 8. 实验检查清单

### 8.1 实验前检查

- [ ] NAO 机器人已充电并开机
- [ ] NAO 和电脑在同一网络
- [ ] 已获取 NAO IP 地址
- [ ] Python 2.7 环境已配置 NAOqi SDK
- [ ] Python 3.x 环境已安装依赖
- [ ] 测试连接成功
- [ ] 实验环境光照充足
- [ ] 实验环境安静（低噪音）

### 8.2 启动检查

- [ ] Python3 客户端已启动（HTTP 服务器运行中）
- [ ] ASR 推送器已启动并连接成功
- [ ] Gaze 推送器已启动并连接成功
- [ ] 客户端收到测试数据
- [ ] 日志文件正常写入

### 8.3 实验中监控

- [ ] ASR 识别率正常（> 70%）
- [ ] Gaze 检测正常（能检测到人脸）
- [ ] 推送延迟可接受（< 500ms）
- [ ] 无异常错误日志
- [ ] NAO 动作执行正常

### 8.4 实验后检查

- [ ] 日志文件已保存
- [ ] 数据完整性检查
- [ ] 推送器统计信息已记录
- [ ] NAO 机器人已关机或充电

---

## 9. 快速参考

### 9.1 常用命令

```bash
# 启动 Python3 客户端（实时模式）
python run_client_demo.py --real --asr-mode realtime --gaze-mode realtime --persona-style encouraging --backchanneling-type positive

# 启动 ASR 推送器
python asr_realtime_pusher.py --robot-ip 192.168.93.152

# 启动 Gaze 推送器
python gaze_realtime_pusher.py --robot-ip 192.168.93.152

# 测试 NAO 连接
python -c "from naoqi import ALProxy; tts = ALProxy('ALTextToSpeech', '192.168.93.152', 9559); tts.say('Hello')"

# 查看端口占用
netstat -ano | findstr 8765
```

### 9.2 关键文件路径

```
nao_interview_coach/
├── client_py3/
│   ├── run_client_demo.py          # Python3 客户端入口
│   └── client/
│       ├── realtime_bridge.py      # HTTP 服务器实现
│       ├── input_provider.py       # ASR 接收逻辑
│       └── gaze_provider.py        # Gaze 接收逻辑
│
├── robot_server_py2/
│   ├── asr_realtime_pusher.py      # ASR 推送器（Python2）
│   └── gaze_realtime_pusher.py     # Gaze 推送器（Python2）
│
└── docs/
    └── realtime_http_integration_guide.md  # 本文档
```

---

## 10. 联系与支持

如有问题，请参考：
- 项目文档：`docs/handover_for_next_developer.md`
- 通信协议：`docs/communication_protocol_v1.md`
- 统一入口：`README.md`

祝实验顺利！🎉
