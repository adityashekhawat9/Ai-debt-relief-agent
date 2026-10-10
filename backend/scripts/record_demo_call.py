import asyncio
import websockets
import json
import base64
import wave
import sys
import os

async def record_demo():
    uri = "ws://127.0.0.1:8000/api/v1/ws-test/ws/test-chat"
    audio_buffer = bytearray()
    
    # We will simulate a user going through the debt relief qualification flow
    script_steps = ["yes", "30000", "yes", "employed", "no", "yes, let's do it"]
    step_index = 0
    
    # 2 seconds of silence (16000 samples/sec * 2 bytes/sample * 2 seconds = 64000 bytes)
    # This creates a realistic "gap" in the audio where the user would be talking
    silence = b'\x00' * 64000
    
    print(f"Connecting to backend: {uri}")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected! Listening for AI audio...")
            
            while True:
                try:
                    # Wait up to 3.5 seconds for AI audio. If nothing arrives, the AI has finished its turn.
                    message = await asyncio.wait_for(websocket.recv(), timeout=3.5)
                    data = json.loads(message)
                    
                    if data.get("type") == "audio_chunk" and data.get("audio_base64"):
                        pcm = base64.b64decode(data["audio_base64"])
                        audio_buffer.extend(pcm)
                        print(f"Received {len(pcm)} bytes of AI speech...")
                        
                except asyncio.TimeoutError:
                    if step_index < len(script_steps):
                        reply = script_steps[step_index]
                        print(f"\nAI finished speaking. Inserting gap, simulating user saying: '{reply}'")
                        
                        audio_buffer.extend(silence)
                        
                        # Acknowledge TTS finished so the backend doesn't trigger a silence timeout
                        await websocket.send(json.dumps({"type": "tts_finished"}))
                        
                        # Send the user text
                        await websocket.send(json.dumps({"type": "text", "text": reply}))
                        step_index += 1
                    else:
                        print("\nScript finished! Ending call.")
                        break
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed by server.")
                    break
    except ConnectionRefusedError:
        print("ERROR: Could not connect to backend. Is uvicorn running on port 8000?")
        return

    filename = "elevenlabs_demo_call_2.wav"
    filepath = os.path.join(os.getcwd(), filename)
    print(f"\nSaving {len(audio_buffer)} bytes to {filepath}...")
    with wave.open(filepath, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2) # 16-bit PCM
        f.setframerate(16000)
        f.writeframes(audio_buffer)
    print(f"Done! Play {filename} to hear the demo.")

if __name__ == "__main__":
    asyncio.run(record_demo())
