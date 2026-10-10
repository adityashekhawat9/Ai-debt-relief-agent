import av
import wave
import numpy as np
import os
import glob

def mux_audio(user_webm, ai_wav, output_wav):
    print(f"Muxing {user_webm} and {ai_wav}...")
    
    # Read user audio (WebM)
    user_audio = None
    try:
        container = av.open(user_webm)
        stream = container.streams.audio[0]
        # Resample everything to 16kHz mono
        resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
        frames = []
        for frame in container.decode(stream):
            frame.pts = None
            resampled_frames = resampler.resample(frame)
            for rf in resampled_frames:
                arr = rf.to_ndarray()
                frames.append(arr[0])
        
        # Flush resampler
        for rf in resampler.resample(None):
            arr = rf.to_ndarray()
            frames.append(arr[0])
            
        if frames:
            user_audio = np.concatenate(frames)
    except Exception as e:
        print(f"Error reading {user_webm}: {e}")
        
    # Read AI audio (WAV)
    ai_audio = None
    try:
        with wave.open(ai_wav, 'rb') as wf:
            n_frames = wf.getnframes()
            audio_bytes = wf.readframes(n_frames)
            ai_audio = np.frombuffer(audio_bytes, dtype=np.int16)
    except Exception as e:
        print(f"Error reading {ai_wav}: {e}")
        
    if user_audio is None and ai_audio is None:
        print("Both audio files empty.")
        return
        
    if user_audio is None: user_audio = np.array([], dtype=np.int16)
    if ai_audio is None: ai_audio = np.array([], dtype=np.int16)
    
    # Pad to same length
    max_len = max(len(user_audio), len(ai_audio))
    
    # Left channel = User, Right channel = AI
    user_padded = np.zeros(max_len, dtype=np.int16)
    user_padded[:len(user_audio)] = user_audio
    
    ai_padded = np.zeros(max_len, dtype=np.int16)
    ai_padded[:len(ai_audio)] = ai_audio
    
    # Stereo (User Left, AI Right)
    stereo = np.empty((max_len, 2), dtype=np.int16)
    stereo[:, 0] = user_padded
    stereo[:, 1] = ai_padded
    
    print(f"Writing {output_wav} (Length: {max_len} samples)")
    with wave.open(output_wav, 'wb') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(stereo.tobytes())
    
    print("Muxing complete!")

if __name__ == "__main__":
    records = glob.glob("records/call_*")
    if records:
        latest = sorted(records)[-1]
        mux_audio(f"{latest}/user.webm", f"{latest}/ai.wav", f"{latest}/combined.wav")
    else:
        print("No records found.")
