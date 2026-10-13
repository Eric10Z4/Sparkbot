import asyncio
import logging
from main import notify_agent

# 提升一下日志级别，方便在终端看清楚
logging.getLogger("MAIN").setLevel(logging.INFO)

async def test_run():
    print("=" * 50)
    print("🚀 开始测试向 OpenClaw 注入消息...")
    print("=" * 50)
    
    # 调用 main.py 中已经修复了 Token 和大小写的函数
    await notify_agent("这是一条来自测试脚本的警报注入！测试大小写 Session ID 和 Token 是否生效。")
    
    print("=" * 50)
    print("✅ 测试调用完成。请检查终端输出是否成功 (HTTP 200)，以及微信是否收到了消息。")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_run())
