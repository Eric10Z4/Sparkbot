import asyncio
import websockets
import json
import base64
import httpx
import ssl
import certifi
_orig = ssl.create_default_context
ssl.create_default_context = lambda *args, **kwargs: _orig(cafile=certifi.where(), *args, **kwargs) if "cafile" not in kwargs else _orig(*args, **kwargs)

async def simulate_robot():
    uri = "ws://127.0.0.1:8765"
    print(f"[Robot] Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("[Robot] Connected successfully!")
            
            # 1. Simulate sending an audio file (STT test)
            with open("ref_audio.wav", "rb") as f:
                audio_data = f.read()
            print(f"[Robot] Sending audio data: {len(audio_data)} bytes...")
            await websocket.send(audio_data)
            
            # Wait for 2 seconds for STT to process and print logs on server
            await asyncio.sleep(2)
            
            # 2. Simulate QClaw triggering TTS response (TTS test)
            print("[Robot] Triggering TTS via HTTP API...")
            async with httpx.AsyncClient() as client:
                resp = await client.post("http://127.0.0.1:5000/api/speak", json={
                    "text": "测试通路完成！这段语音是合成的！",
                    "emotion": "happy"
                })
                print(f"[Robot] HTTP API response: {resp.status_code} {resp.text}")
            
            # 3. Wait for hardware push command
            print("[Robot] Waiting for hardware push command (play_audio)...")
            message = await websocket.recv()
            data = json.loads(message)
            if data.get("type") == "play_audio":
                audio_b64 = data["data"]
                audio_bytes = base64.b64decode(audio_b64)
                with open("test_output.wav", "wb") as f:
                    f.write(audio_bytes)
                print(f"[Robot] SUCCESS! Received play_audio command. Saved test_output.wav ({len(audio_bytes)} bytes).")
            else:
                print(f"[Robot] Unknown command received: {data.get('type')}")
                
    except Exception as e:
        print(f"[Robot] Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(simulate_robot())
