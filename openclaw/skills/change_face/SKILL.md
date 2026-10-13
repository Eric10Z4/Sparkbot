---
name: change_face
description: 切换机器人屏幕表情。
user-invocable: true
---

# change_face

切换机器人屏幕表情动画。

## 调用（一行搞定）

```bash
python "C:\Users\<你的用户名>\.openclaw\skills\robot_api.py" face <expression_id>
```

## 可用表情

`angry` / `eye_roll` / `happy` / `speak` / `sad`

## 示例

```bash
python "C:\Users\<你的用户名>\.openclaw\skills\robot_api.py" face angry
python "C:\Users\<你的用户名>\.openclaw\skills\robot_api.py" face eye_roll
python "C:\Users\<你的用户名>\.openclaw\skills\robot_api.py" face happy
```

## 返回值

```json
{"status": "pending", "msg": "表情已暂存（硬件未连接）：angry"}
```
