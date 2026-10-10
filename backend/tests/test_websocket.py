import asyncio
import websockets
import json
import numpy as np

async def test_ws():
    uri = "ws://localhost:8001/api/v1/ws-test/ws/test-chat"
    try:
        async with websockets.connect(uri, open_timeout=60) as websocket:
            print("Connected to WS.")
            
            # Wait for first message (AI greeting)
            msg = await websocket.recv()
            print(f"Received: {msg[:100]}...")
            
            print("Sending 20 chunks of loud binary audio to trigger STT...")
            # 4096 samples of int16 = 256ms of 16kHz
            # A 400Hz loud tone will definitely trigger VAD
            t = np.linspace(0, 0.256, 4096, endpoint=False)
            audio = (np.sin(2 * np.pi * 400 * t) * 30000).astype(np.int16).tobytes()
            
            for i in range(20):
                await websocket.send(audio)
                print(f"Sent chunk {i+1}")
                await asyncio.sleep(0.05)
                
            print("Sent successfully. Waiting for AI response or STT output...")
            # Now wait for the server's response
            msg = await websocket.recv()
            print(f"Server response after audio: {msg[:100]}")
            
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed by server: {e}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
