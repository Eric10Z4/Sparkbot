---
name: physical_speak
description: 让机器人扬声器说话，支持情绪语气。
user-invocable: true
---

# physical_speak

让机器人扬声器说出一句话。后端自动 TTS 合成。

## 调用（一行搞定）

```bash
python "C:\Users\<你的用户名>\.openclaw\skills\robot_api.py" speak "要说的话" [emotion]
```

## 参数

- `text`（必填）：要说的话，**20字以内最佳**，直接跟在 speak 后面
- `emotion`（选填）：`angry` / `happy` / `sad` / `neutral`（默认），写最后

## 示例

```bash
# 基础调用
python "C:\Users\<你的用户名>\.openclaw\skills\robot_api.py" speak "你好！"

# 带情绪
python "C:\Users\<你的用户名>\.openclaw\skills\robot_api.py" speak "别碰我！" angry

# 开心
python "C:\Users\<你的用户名>\.openclaw\skills\robot_api.py" speak "欢迎回来~" happy
```

## 返回值

```json
{"status": "success", "msg": "已合成并暂存：你好！", "audio_size": 255168, "emotion": "neutral"}
```

- `status: success` → TTS 合成成功（硬件连接则直接播放，未连接则暂存）
- `status: pending` → 硬件未连接，已暂存等待

## 注意

- ❌ 禁止用 curl -d 传含中文的 JSON（Windows 必乱码 ???）
- ✅ 必须用 robot_api.py 脚本，Python 原生 UTF-8 无编码问题
