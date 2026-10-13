---
name: robot_move
description: 控制机器人履带移动，慎用。
user-invocable: true
---

# robot_move

控制机器人履带物理移动。

## 调用（一行搞定）

```bash
python "C:\Users\<你的用户名>\.openclaw\skills\robot_api.py" move <direction> <duration>
```

## 参数

- `direction`：`forward` / `backward` / `spin`
- `duration`：1~5 秒（**禁止超过5秒**，会掉桌子）

## 示例

```bash
# 原地转1秒
python "C:\Users\<你的用户名>\.openclaw\skills\robot_api.py" move spin 1

# 前进2秒
python "C:\Users\<你的用户名>\.openclaw\skills\robot_api.py" move forward 2

# 后退1秒
python "C:\Users\<你的用户名>\.openclaw\skills\robot_api.py" move backward 1
```

## ⚠️ 安全提醒

- 移动是最重的物理动作，只在真正需要时调用
- 确保机器人在安全位置（远离桌沿、楼梯）
- 优先用短时间动作测试（1秒），确认安全后再加长时间

## 额外：查状态

```bash
python "C:\Users\<你的用户名>\.openclaw\skills\robot_api.py" status
```

返回：`{"status":"success","robot":{"connected":false,"battery":-1,"pitch":0.0,"roll":0.0}}`
