# SparkBot 项目状态报告

> 历史开发记录，功能现状和配置以根目录 README、DEPLOYMENT 为准。

---

## 架构总览

```
手机微信 ──→ WeChat插件 ──→ OpenClaw Agent (我/小怼) ──→ SparkAgentServer ──→ ESP32机器人
                                           ↑  systemEvent 注入                │
                                           └──── SparkAgentServer ←──────────┘
                                                    (哨兵检测)  ✅ 已完成
```

---

## ✅ 已完成（21 项）

### A. OpenClaw Agent — 大模型大脑 + 通讯通道

| # | 项 | 说明 |
|:---:|------|------|
| 1 | 人设系统 | SOUL.md 毒舌小精灵 + persona-switch 三套可切换 |
| 2 | 记忆系统 | 日记 `memory/` + MEMORY.md + 梦境 `.dreams/` |
| 3 | 工作空间还原 | AGENTS.md / IDENTITY.md / USER.md / TOOLS.md 全部就位 |
| 4 | `physical_speak` 技能 | TTS 合成 → robot_api.py → API 调通（暂存模式，等 ESP32） |
| 5 | `change_face` 技能 | 表情切换 → API 调通（暂存模式） |
| 6 | `robot_move` 技能 | 履带移动 → API 调通（暂存模式） |
| 7 | **哨兵→OpenClaw→微信通知** | `notify_agent()` 已写入 `main.py`，检测到异常自动推微信 |
| 8 | `persona-switch` 技能 | 人设三套切换就绪 |
| 9 | 备份还原 | robot_api.py + memory 文件还原 + 路径修正 `.qclaw`→`.openclaw` |
| 10 | WeChat 插件安装 | `@tencent-weixin/openclaw-weixin` v2.4.3 已启用 |
| 11 | WeChat 扫码登录 | 通道 running，in/out 收发正常 |
| 12 | 跨会话 visibility | 改为 `all`，webchat ⇄ 微信互通 |
| 13 | 跨会话消息发送 | sessions_send 验证通过 |

### B. SparkAgentServer — Python 后端

| # | 项 | 说明 |
|:---:|------|------|
| 14 | Python 环境 | Anaconda base，fastapi/uvicorn/edge-tts/dashscope/websockets/httpx 全齐 |
| 15 | FastAPI HTTP 服务器 | `http://127.0.0.1:5000`，Swagger `/docs` 可用 |
| 16 | 硬件 WebSocket 服务器 | `ws://0.0.0.0:8765` 监听中就绪 |
| 17 | STT 语音识别（云端） | DashScope SenseVoice，含情感检测，测试脚本 `test_stt.py` |
| 18 | TTS 语音合成（云端） | Edge-TTS 微软女声，测试脚本 `test_tts.py` 通过 |
| 19 | API 全链路测试 | speak 255KB / face eye_roll / move spin 全部返回成功 |
| 20 | STT/TTS 本地 GPU 版 | 代码已写好（注释状态），改 `config.py` 一行即切换 |
| 21 | 项目文档 | 总架构计划 / 团队分工 / 两套开发路线 / RESTORE-GUIDE / PROJECT_STATUS |

---

## ❌ 未完成（17 项）

### 🟡 第二梯队：需要 B 同学

| # | 项 | 所在 | 说明 |
|:---:|------|------|------|
| 1 | **ESP32 WebSocket 客户端** | B 同学 ESP-IDF C 代码 | 砍百度云代码 → 加 WS 连 `ws://你的IP:8765` |
| 2 | **ESP32 麦克风录音上报** | 同上 | 录音 → 二进制 bytes 直发 WebSocket |
| 3 | **ESP32 摄像头拍照上报** | 同上 | 拍照 → `{"type":"image","data":"<base64 jpeg>"}` |
| 4 | **ESP32 电量/姿态上报** | 同上 | `{"type":"status","battery":85,"pitch":12.5,"roll":-3.2}` |
| 5 | **音频闭环联调** | `main.py` 第331行 | 收到音频 → STT → LLM → TTS → WebSocket 推回 ESP32 播放 |
| 6 | **表情/移动指令联调** | `main.py` | 验证 ESP32 收到 `set_face`/`move` 正确调硬件 |
| 7 | **全链路端到端测试** | 整条 | "对着机器人说话 → 机器人回嘴+变脸" 走通 |

### 🟡 第三梯队：需要 C 同学

| # | 项 | 说明 |
|:---:|------|------|
| 8 | **视觉模块真实代码** | `visual.py` 的 `face_recognize()` 和 `detect_anomaly()` 目前是占位桩 |

### 🔵 第四梯队：游戏本迁移 + GPU 加速

| # | 项 | 说明 | 工作量 |
|:---:|------|------|:---:|
| 9 | **游戏本环境搭建** | 装 Anaconda → 克隆 base 环境 → `pip install funasr sensevoice modelscope` 等 | 30 分钟 |
| 10 | **STT 切本地 FunASR + SenseVoice** | `stt_service.py` 解除注释，GPU 推理 | 延迟 2s→50ms |
| 11 | **TTS 切本地 GPT-SoVITS** | `tts_service.py` 解除注释，一键切换 | 声音变熟人 |
| 12 | **`config.py` 切模式** | `USE_LOCAL_GPU = True` 一行改动 | 10 秒 |
| 13 | **OpenClaw 配置迁移** | 复制 `~/.openclaw/openclaw.json` + workspace → 游戏本 `~/.openclaw/` | 5 分钟 |
| 14 | **WeChat 重新登录** | 新机器需重新 `openclaw channels login --channel openclaw-weixin` | 1 分钟 |
| 15 | **ESP32 重连新 IP** | B 同学把 WebSocket 地址改成游戏本局域网地址 | B 改一行 |
| 16 | **SparkAgentServer 迁移** | 复制整个目录到游戏本，`pip install -r requirements.txt` | 10 分钟 |
| 17 | **游戏本性能基准测试** | 对比云端 vs 本地 STT/TTS 延迟和准确率 | 30 分钟 |

---

## 进度总览

```
Agent 大脑    ████████████████  100%   (13/13)
微信通道      ████████████████  100%   (4/4)
Python 后端   ████████████████  100%   (7/7)
项目文档      ████████████████  100%   (1/1)
哨兵通知      ████████████████  100%   (1/1)   ✅ 刚完成
──────────────────────────────────────
ESP32 硬件    ░░░░░░░░░░░░░░░░    0%   (0/7)   ← B同学
视觉模块      ░░░░░░░░░░░░░░░░    0%   (0/1)   ← C同学
游戏本 GPU    ░░░░░░░░░░░░░░░░    0%   (0/9)   ← 等机器
──────────────────────────────────────
总体          █████████░░░░░░░░   55%   (21/38)
```

---

## 附：微信 vs QQ Bot 迁移结论

| 功能 | 原方案 | 现方案 |
|------|--------|--------|
| 远程报警 | NapCatQQ → QQ | WeChat 插件 → 微信 ✅ |
| 远程操控 | QQ 打字 → NapCatQQ | 微信打字 → WeChat 插件 ✅ |
| 警报注入 | 无方案 | `notify_agent()` → Gateway systemEvent ✅ |
| 跨会话 | 无方案 | visibility=all ✅ |
