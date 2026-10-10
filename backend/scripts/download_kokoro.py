import os
import httpx
import asyncio

KOKORO_DIR = os.path.join("models", "kokoro")
MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

async def download_file(url: str, dest: str):
    print(f"Downloading {os.path.basename(dest)}...")
    async with httpx.AsyncClient(follow_redirects=True) as client:
        async with client.stream('GET', url) as response:
            response.raise_for_status()
            total = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(dest, 'wb') as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    
            print(f"Downloaded {downloaded / (1024*1024):.2f} MB")

async def main():
    os.makedirs(KOKORO_DIR, exist_ok=True)
    
    model_path = os.path.join(KOKORO_DIR, "kokoro-v1.0.onnx")
    voices_path = os.path.join(KOKORO_DIR, "voices-v1.0.bin")
    
    if not os.path.exists(model_path):
        await download_file(MODEL_URL, model_path)
    else:
        print(f"{model_path} already exists. Skipping.")
        
    if not os.path.exists(voices_path):
        await download_file(VOICES_URL, voices_path)
    else:
        print(f"{voices_path} already exists. Skipping.")
        
    print("Kokoro TTS download complete!")

if __name__ == "__main__":
    asyncio.run(main())
