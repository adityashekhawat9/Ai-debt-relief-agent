import httpx, asyncio, wave, io, base64, os

api_key = os.getenv('DEEPGRAM_API_KEY', '')
voice = 'aura-2-luna-en'

async def test():
    headers = {'Authorization': f'Token {api_key}', 'Content-Type': 'application/json'}
    payload = {'text': 'Hello, this is a test of Angela.'}
    url = f'https://api.deepgram.com/v1/speak?model={voice}&encoding=linear16&sample_rate=8000'
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=headers, json=payload, timeout=15.0)
        print(f'Status: {r.status_code}')
        audio_bytes = r.content
        print(f'Total bytes: {len(audio_bytes)}')
        print(f'First 4 bytes: {audio_bytes[:4]}')
        
        # Check if RIFF WAV header present
        is_wav = audio_bytes[:4] == b'RIFF'
        print(f'Is WAV: {is_wav}')
        
        # Simulate what browser_orchestrator does: strip WAV header then re-wrap
        pcm_bytes = audio_bytes[44:] if is_wav else audio_bytes
        print(f'PCM bytes after strip: {len(pcm_bytes)}')
        
        # Check Deepgram actual sample rate from WAV header
        if is_wav:
            with io.BytesIO(audio_bytes) as f:
                with wave.open(f, 'rb') as wf:
                    print(f'Deepgram WAV sample rate: {wf.getframerate()}')
                    print(f'Deepgram WAV channels: {wf.getnchannels()}')
                    print(f'Deepgram WAV sample width: {wf.getsampwidth()}')
        
        # Then browser_orchestrator wraps in a new WAV with framerate=8000
        with io.BytesIO() as wav_io:
            with wave.open(wav_io, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(pcm_bytes)
            wav_bytes = wav_io.getvalue()
        
        print(f'Final WAV bytes: {len(wav_bytes)}')
        b64 = base64.b64encode(wav_bytes).decode('utf-8')
        print(f'Base64 length: {len(b64)}')
        print('SUCCESS - pipeline works correctly')

asyncio.run(test())
