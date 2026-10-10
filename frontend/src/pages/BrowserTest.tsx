import { useState, useEffect, useRef } from 'react';
import { Mic, MicOff, Send, Phone, PhoneCall, Activity, Volume2, VolumeX } from 'lucide-react';
import '../index.css';

type Message = {
  id: string;
  speaker: 'user' | 'ai';
  text: string;
};

// Temporary PhoneOff icon until imported properly
const PhoneOff = ({ size }: { size: number }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7 2 2 0 0 1 1.72 2v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.42 19.42 0 0 1-3.33-2.67m-2.67-3.34a19.79 19.79 0 0 1-3.07-8.63A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91"/><line x1="22" y1="2" x2="2" y2="22"/></svg>
);

function BrowserTest() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [callStatus, setCallStatus] = useState<'idle' | 'connecting' | 'connected'>('idle');
  const [isRecording, setIsRecording] = useState(false);
  const [aiVoiceEnabled, setAiVoiceEnabled] = useState(true);
  const [fsmState, setFsmState] = useState('OFFLINE');
  const [scriptStep, setScriptStep] = useState(0);
  
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isBargedInRef = useRef<boolean>(false);
  
  // Web Audio API playback refs
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const nextStartTimeRef = useRef<number>(0);
  
  const stopAllAudio = () => {
    activeSourcesRef.current.forEach(source => {
      try { source.stop(); } catch(e) {}
    });
    activeSourcesRef.current = [];
    nextStartTimeRef.current = 0;
  };

  // Audio Streaming Refs
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const micAudioCtxRef = useRef<AudioContext | null>(null);
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const startCall = () => {
    if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
    if (audioContextRef.current.state === 'suspended') {
        audioContextRef.current.resume();
    }
    
    setCallStatus('connecting');
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/api/v1/ws-test/ws/test-chat`;
    const ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
      setCallStatus('connected');
      setFsmState('QUALIFICATION');
      startRecording();
    };
    
    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'ready') {
            // Backend is ready, audio context is already unlocked from our click
            console.log("Backend ready signal received");
          } else if (data.type === 'barge_in') {
             stopAllAudio();
             isBargedInRef.current = true;
          } else if (data.type === 'text') {
            setMessages(prev => [...prev, {
              id: Math.random().toString(),
              speaker: data.speaker,
              text: data.text
            }]);
            
            if (data.fsm_state) setFsmState(data.fsm_state);
            if (data.script_step !== undefined) setScriptStep(data.script_step);
          } else if (data.type === 'sentence') {
            isBargedInRef.current = false;
            setMessages(prev => {
              const newMessages = [...prev];
              if (newMessages.length > 0 && newMessages[newMessages.length - 1].speaker === 'ai') {
                  const lastMsg = newMessages[newMessages.length - 1];
                  // append text with a space
                  newMessages[newMessages.length - 1] = {
                      ...lastMsg,
                      text: lastMsg.text + ' ' + data.text
                  };
              } else {
                  newMessages.push({
                      id: Math.random().toString(),
                      speaker: data.speaker,
                      text: data.text
                  });
              }
              return newMessages;
            });
          } else if (data.type === 'audio_chunk') {
              if (isBargedInRef.current) return;
              if (data.audio_base64 && audioContextRef.current) {
                  const binaryString = atob(data.audio_base64);
                  const alignedLen = binaryString.length - (binaryString.length % 2);
                  const bytes = new Uint8Array(alignedLen);
                  for (let i = 0; i < alignedLen; i++) {
                      bytes[i] = binaryString.charCodeAt(i);
                  }
                  
                  // 16-bit PCM at 24000Hz Studio HD
                  const pcm16 = new Int16Array(bytes.buffer, 0, alignedLen / 2);
                  const float32 = new Float32Array(pcm16.length);
                  for (let i = 0; i < pcm16.length; i++) {
                      float32[i] = pcm16[i] / 32768.0;
                  }

                  // Eliminate zero-crossing clicks/pops with a 32-sample micro-ramp (~1.3ms)
                  const rampLen = Math.min(32, Math.floor(float32.length / 4));
                  for (let i = 0; i < rampLen; i++) {
                      const factor = i / rampLen;
                      float32[i] *= factor;
                      float32[float32.length - 1 - i] *= factor;
                  }
                  
                  const audioCtx = audioContextRef.current;
                  const sampleRate = data.sample_rate || 24000;
                  const buffer = audioCtx.createBuffer(1, float32.length, sampleRate);
                  buffer.getChannelData(0).set(float32);
                  
                  const source = audioCtx.createBufferSource();
                  source.buffer = buffer;
                  source.connect(audioCtx.destination);
                  
                  const currentTime = audioCtx.currentTime;
                  // If nothing is currently playing or if buffer underrun occurred, schedule with tight 20ms lookahead.
                  // While audio is actively playing, chain onto nextStartTimeRef for seamless gapless playback.
                  if (activeSourcesRef.current.length === 0 || nextStartTimeRef.current < currentTime) {
                      nextStartTimeRef.current = currentTime + 0.02;
                  }
                  
                  source.start(nextStartTimeRef.current);
                  nextStartTimeRef.current += buffer.duration;
                  
                  activeSourcesRef.current.push(source);
                  
                  // Clean up finished sources from array
                  source.onended = () => {
                      activeSourcesRef.current = activeSourcesRef.current.filter(s => s !== source);
                      if (activeSourcesRef.current.length === 0) {
                          nextStartTimeRef.current = 0; // Hard reset time drift between conversational turns
                          if (wsRef.current?.readyState === WebSocket.OPEN) {
                              wsRef.current.send(JSON.stringify({ type: 'tts_finished' }));
                          }
                      }
                  };
              }
          } else if (data.type === 'state_update') {
            if (data.fsm_state) setFsmState(data.fsm_state);
            if (data.script_step !== undefined) setScriptStep(data.script_step);
          }
        } catch (e) {
          console.error("Failed to parse WS message", e);
        }
      }
    };
    
    ws.onclose = () => {
      setCallStatus('idle');
      setFsmState('OFFLINE');
      setMessages([]);
      stopAndCloseAudioContext(); // Full cleanup on disconnect
    };
    
    wsRef.current = ws;
  };

  const endCall = () => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    stopAllAudio();
    setCallStatus('idle');
    setMessages([]);
    setScriptStep(0);
    stopAndCloseAudioContext(); // Close everything on full call end
  };

  const sendMessage = (text: string) => {
    if (!text.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    
    // Stop any playing audio immediately (barge-in)
    stopAllAudio();
    isBargedInRef.current = true;

    setMessages(prev => [...prev, {
      id: Math.random().toString(),
      speaker: 'user',
      text: text
    }]);
    
    wsRef.current.send(JSON.stringify({ 
      type: 'text', 
      text: text, 
      play_voice: aiVoiceEnabled 
    }));
    setInputText('');
  };

  const stopRecording = () => {
    // Stop MediaRecorder
    if (mediaRecorderRef.current) {
      try { mediaRecorderRef.current.stop(); } catch(e) {}
      mediaRecorderRef.current = null;
    }
    // Disconnect VAD processor
    if (processorRef.current) {
      try { processorRef.current.disconnect(); } catch(e) {}
      processorRef.current = null;
    }
    // Stop mic stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    // Close the dedicated mic audio context
    if (micAudioCtxRef.current) {
      try { micAudioCtxRef.current.close(); } catch(e) {}
      micAudioCtxRef.current = null;
    }
    setIsRecording(false);
  };

  const stopAndCloseAudioContext = () => {
    // Called only when the entire call ends
    stopRecording();
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        video: false,
      });

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : 'audio/ogg;codecs=opus';

      const mediaRecorder = new MediaRecorder(stream, { mimeType });

      mediaRecorder.ondataavailable = (event) => {
        if (!event.data || event.data.size === 0) return;
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        wsRef.current.send(event.data);
      };

      mediaRecorder.onerror = (e) => {
        console.error('[Mic] MediaRecorder error:', e);
      };

      mediaRecorder.start(250);

      streamRef.current = stream;
      mediaRecorderRef.current = mediaRecorder;
      setIsRecording(true);

    } catch (err) {
      console.error('[Mic] Error starting recording:', err);
    }
  };

  const toggleRecording = async () => {
    if (isRecording) {
      stopRecording();
    } else {
      await startRecording();
    }
  };



  return (
    <div className="app-container">
      {/* Dynamic Background Glow based on status */}
      <div className={`ambient-glow status-${callStatus}`}></div>



      <div className="glass-panel">
        
        {/* Header */}
        <div className="panel-header">
          <h2 className="header-title">
            <div className={`status-indicator ${callStatus === 'connected' ? 'active' : callStatus === 'connecting' ? 'connecting' : 'idle'}`}></div>
            {callStatus === 'connected' ? <Activity size={24} style={{color: 'var(--accent-secondary)'}} /> : <Phone size={24} />} 
            Debt Relief AI
          </h2>
          
          {callStatus === 'connected' && (
            <div className="badge-group">
              <span className="badge badge-primary">FSM: {fsmState}</span>
              <span className="badge badge-warning">STEP: {scriptStep}/5</span>
            </div>
          )}
        </div>

        {callStatus === 'idle' ? (
          /* Idle State (Dial Button) */
          <div className="idle-screen">
            <div className="idle-icon-wrapper">
              <PhoneCall size={56} />
            </div>
            <h1 className="idle-title">Ready to test the script?</h1>
            <p className="idle-subtitle">Click below to simulate a live outbound call. The AI will instantly connect and deliver the Step 0 pitch.</p>
            <button onClick={startCall} className="btn-primary btn-start">
              Start Live Call <Phone size={20} />
            </button>
            <button 
              onClick={() => {
                const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
                const osc = ctx.createOscillator();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(440, ctx.currentTime);
                osc.connect(ctx.destination);
                osc.start();
                osc.stop(ctx.currentTime + 0.5);
              }} 
              className="btn-secondary" 
              style={{marginTop: '10px'}}
            >
              Test Speaker Output
            </button>
          </div>
        ) : (
          /* Active Call State */
          <>
            {/* Chat Log */}
            <div className="chat-area">
              {messages.length === 0 ? (
                <div style={{ textAlign: 'center', color: 'var(--text-muted)', opacity: 0.5 }}>
                  Connecting to AI Pipeline...
                </div>
              ) : (
                messages.map((msg) => (
                  <div key={msg.id} className={`message-wrapper ${msg.speaker}`}>
                    <div className={`message-bubble ${msg.speaker}`}>
                      <p>{msg.text}</p>
                    </div>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div className="input-area">
              <button 
                onClick={endCall}
                className="icon-btn danger-state"
                title="Hang up"
              >
                <PhoneOff size={22} />
              </button>
              
              <button 
                onClick={() => setAiVoiceEnabled(!aiVoiceEnabled)}
                className={`icon-btn ${aiVoiceEnabled ? 'active-state' : ''}`}
                title={aiVoiceEnabled ? "AI Voice Enabled" : "AI Voice Disabled"}
              >
                {aiVoiceEnabled ? <Volume2 size={22} /> : <VolumeX size={22} />}
              </button>

              <button 
                onClick={toggleRecording}
                className={`icon-btn ${isRecording ? 'recording' : ''}`}
                title={isRecording ? "Stop Streaming Microphone" : "Start Live Mic Streaming (VAD)"}
              >
                {isRecording ? <MicOff size={22} /> : <Mic size={22} />}
              </button>
              
              <div className="input-field-wrapper">
                <input 
                  type="text" 
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && sendMessage(inputText)}
                  placeholder="Type or speak (raw audio stream)..."
                  className="text-input"
                />
                <button 
                  onClick={() => sendMessage(inputText)}
                  disabled={!inputText.trim()}
                  className="btn-primary btn-send"
                >
                  <Send size={18} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default BrowserTest;
