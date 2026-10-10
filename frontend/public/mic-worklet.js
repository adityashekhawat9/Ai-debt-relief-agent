/**
 * AudioWorklet processor: runs on the audio rendering thread.
 * Receives raw Float32 PCM from the microphone, downsamples to 16kHz,
 * converts to Int16, and posts the ArrayBuffer to the main thread.
 */
class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = [];
    this._inputSampleRate = sampleRate; // global AudioWorklet sampleRate
    this._targetSampleRate = 16000;
    // Accumulate until we have ~256ms worth of target-rate samples (4096 samples @ 16kHz)
    this._targetChunkSize = 4096;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const float32 = input[0]; // mono channel

    // Downsample if needed
    let resampled = float32;
    if (this._inputSampleRate !== this._targetSampleRate) {
      const ratio = this._inputSampleRate / this._targetSampleRate;
      const outLen = Math.round(float32.length / ratio);
      resampled = new Float32Array(outLen);
      for (let i = 0; i < outLen; i++) {
        let idx = Math.round(i * ratio);
        if (idx >= float32.length) idx = float32.length - 1;
        resampled[i] = float32[idx];
      }
    }

    // Push to buffer
    for (let i = 0; i < resampled.length; i++) {
      this._buffer.push(resampled[i]);
    }

    // Flush when we have enough for a chunk
    while (this._buffer.length >= this._targetChunkSize) {
      const chunk = this._buffer.splice(0, this._targetChunkSize);
      const int16 = new Int16Array(this._targetChunkSize);
      for (let i = 0; i < this._targetChunkSize; i++) {
        const s = Math.max(-1, Math.min(1, chunk[i]));
        int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      // Transfer the buffer (zero-copy) to main thread
      this.port.postMessage(int16.buffer, [int16.buffer]);
    }

    return true; // keep processor alive
  }
}

registerProcessor('mic-processor', MicProcessor);
