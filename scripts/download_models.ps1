$ErrorActionPreference = "Stop"

# Base models directory relative to script location
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ModelsDir = Join-Path -Path $ScriptDir -ChildPath "..\models"
$ModelsDir = [System.IO.Path]::GetFullPath($ModelsDir)

# Create directories if they do not exist
$LlmDir = Join-Path -Path $ModelsDir -ChildPath "llm"
$PiperDir = Join-Path -Path $ModelsDir -ChildPath "piper"
New-Item -ItemType Directory -Force -Path $LlmDir | Out-Null
New-Item -ItemType Directory -Force -Path $PiperDir | Out-Null

Write-Host "Downloading Qwen2.5-3B-Instruct-GGUF to $LlmDir"
# Using python directly to avoid CLI pathing and deprecation issues
$PythonCode = @"
from huggingface_hub import hf_hub_download
import sys
try:
    path = hf_hub_download(
        repo_id='Qwen/Qwen2.5-3B-Instruct-GGUF',
        filename='qwen2.5-3b-instruct-q4_k_m.gguf',
        local_dir=r'$LlmDir',
        local_dir_use_symlinks=False
    )
    print(f'Successfully downloaded to: {path}')
except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
"@

python -c $PythonCode

Write-Host "Downloading Piper voice en_US-ryan-medium to $PiperDir"
$PiperOnnxUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx"
$PiperJsonUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json"

Invoke-WebRequest -Uri $PiperOnnxUrl -OutFile (Join-Path -Path $PiperDir -ChildPath "en_US-ryan-medium.onnx")
Invoke-WebRequest -Uri $PiperJsonUrl -OutFile (Join-Path -Path $PiperDir -ChildPath "en_US-ryan-medium.onnx.json")

Write-Host "Faster-Whisper downloads its own weights automatically upon first run."
Write-Host "Model downloads complete."
