import asyncio
import websockets
import json
import base64
import wave
import io

async def test_ws():
    uri = "ws://127.0.0.1:8000/api/v1/ws-test/ws/test-chat"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to WebSocket.")
            
            # Send test message
            msg = {
                "type": "text",
                "text": "Hello, I want to talk about my debt.",
                "play_voice": True
            }
            await websocket.send(json.dumps(msg))
            print("Sent message.")
            
            # Receive response
            text_received = False
            audio_received = False
            while not (text_received and audio_received):
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") == "text":
                    print(f"Received text: {data.get('text')}")
                    text_received = True
                
                elif data.get("type") == "audio":
                    b64 = data.get("audio_base64")
                    audio_bytes = base64.b64decode(b64)
                    print(f"Received audio: {len(audio_bytes)} bytes")
                    
                    # Verify wav headers
                    try:
                        with wave.open(io.BytesIO(audio_bytes), 'rb') as w:
                            print(f"WAV Headers - Channels: {w.getnchannels()}, Width: {w.getsampwidth()}, Rate: {w.getframerate()}")
                        audio_received = True
                    except Exception as e:
                        print(f"Failed to parse WAV headers: {e}")
                        audio_received = True
    except Exception as e:
        print(f"WebSocket error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
