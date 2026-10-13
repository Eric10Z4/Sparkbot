# robot_api.py - SparkAgentServer HTTP 调用辅助脚本
# 放到 skills/ 目录根下
# 用法: python robot_api.py speak "你好" angry
#        python robot_api.py face happy
#        python robot_api.py move forward 2
#        python robot_api.py status

import sys, json, os

import requests
BASE = os.environ.get("SPARKBOT_API_URL", "http://127.0.0.1:5000/api").rstrip("/")

def request(method, endpoint, **kwargs):
    token = os.environ.get("SPARKBOT_API_TOKEN", "")
    if not token:
        raise SystemExit("Set SPARKBOT_API_TOKEN in the local environment")
    response = requests.request(method, BASE+endpoint,
        headers={"Authorization": "Bearer "+token}, timeout=30, **kwargs)
    response.raise_for_status()
    return response


def main():
    if len(sys.argv) < 2:
        print("用法: python robot_api.py <speak|face|move|camera|status> [args...]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "speak":
        text = sys.argv[2] if len(sys.argv) > 2 else ""
        emotion = sys.argv[3] if len(sys.argv) > 3 else "neutral"
        r = request("POST", "/speak", json={"text": text, "emotion": emotion})
    elif cmd == "face":
        expr = sys.argv[2] if len(sys.argv) > 2 else "neutral"
        r = request("POST", "/face", json={"expression_id": expr})
    elif cmd == "move":
        direction = sys.argv[2] if len(sys.argv) > 2 else "forward"
        duration = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        r = request("POST", "/move", json={"direction": direction, "duration": duration})
    elif cmd == "camera":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        interval_ms = int(sys.argv[3]) if len(sys.argv) > 3 else 500
        r = request("POST", "/camera/capture", json={"count": count, "interval_ms": interval_ms})
        if r.status_code == 200:
            print("已启动拍摄")
        else:
            print(f"拍摄启动失败: {r.text}")
        sys.exit(0)
    elif cmd == "status":
        r = request("GET", "/status")
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)

    print(r.text)

if __name__ == "__main__":
    main()
