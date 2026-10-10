import asyncio
import time
import json
import base64
import io
import wave
import os
from datetime import datetime, timezone
from langchain_core.messages import HumanMessage
from fastapi import WebSocket, WebSocketDisconnect

from core.logging import get_logger, async_log_error
from conversation_engine.langgraph_dialogue import DialogueManager, DialogueState
from services.ai.tts_engine import TTSEngine
from services.ai.stt_engine import STTEngine, DeepgramStreamingClient

logger = get_logger(__name__)

# Global in-memory cache for conversational fillers (bridges latency gap in 0ms)
_RAM_FILLER_CACHE: dict[str, list[str]] = {}

class BrowserTestOrchestrator:
    """
    Orchestrator that runs the AI pipeline over a WebSocket.
    Accepts text (JSON) or binary audio frames (PCM).
    """
    def __init__(
        self,
        websocket: WebSocket,
        llm_engine,
        qdrant_service,
        embedder_service,
    ):
        self.websocket = websocket
        self.llm_engine = llm_engine
        self.tts_engine = TTSEngine()
        self.stt_engine = STTEngine()
        self.streaming_stt = None
        
        self.dialogue_manager = DialogueManager(
            llm_engine=llm_engine,
            qdrant_service=qdrant_service,
            embedder_service=embedder_service
        )
        import uuid
        self.session_id = f"browser_{uuid.uuid4().hex[:8]}"
        
        self._fsm_state = "QUALIFICATION"
        self._dialogue_state: DialogueState = {
            "messages": [],
            "fsm_state": self._fsm_state,
            "qualification_answers": {},
            "objection_count": 0,
            "intent": None,
            "script_step": 1,
            "lead_first_name": None
        }
        
        self.audio_queue = asyncio.Queue(maxsize=200)  # Bounded to prevent memory blowup
        self.interruption_event = asyncio.Event()
        self.is_active = True
        self.vad_task = None
        self.ai_speaking = False
        self.last_interaction_time = time.time()
        self.silence_warnings = 0
        self._audio_chunk_count = 0  # For rate-limiting audio log spam
        self.accumulated_text = ""
        self.last_word_time = time.time()
        self._stt_buffer_task = None
        self._recent_ai_transcripts = ""
        self._wpm_history = []
        self._pace_profile = "NORMAL"
        
        self.io_queue = asyncio.Queue()
        self.io_task = None
        
        from core.config import get_settings
        self.settings = get_settings()
        self.user_record_file = None
        self.ai_record_file = None
        
        if self.settings.ENABLE_CALL_RECORDING:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            self.record_dir = os.path.join(os.getcwd(), "records", f"call_{timestamp}")
            os.makedirs(self.record_dir, exist_ok=True)
            
            self.user_record_path = os.path.join(self.record_dir, "user.webm")
            self.ai_record_path = os.path.join(self.record_dir, "ai.wav")
            self.combined_record_path = os.path.join(self.record_dir, "combined.wav")
            
            self.user_record_file = open(self.user_record_path, "wb")
            self.ai_record_file = wave.open(self.ai_record_path, "wb")
            self.ai_record_file.setnchannels(1)
            self.ai_record_file.setsampwidth(2) # 16-bit
            self.ai_record_file.setframerate(16000)
            logger.info(f"Call recording enabled. Saving to {self.record_dir}")

    async def _deepgram_keepalive_task(self):
        """Sends periodic KeepAlive to Deepgram to prevent WebSocket drops during silence."""
        while self.is_active:
            await asyncio.sleep(3.0)
            if self.streaming_stt and self.streaming_stt.is_connected:
                await self.streaming_stt.keepalive()

    async def _audio_sender_task(self):
        """Pulls from audio queue and sends continuously to Deepgram WebSocket."""
        logger.info("[DEBUG] _audio_sender_task STARTED")
        sent_count = 0
        while self.is_active:
            chunk = await self.audio_queue.get()
            if chunk is None:
                logger.info("[DEBUG] _audio_sender_task received None sentinel, exiting")
                break
            if self.streaming_stt is None or not self.streaming_stt.is_connected:
                logger.info("[STT Sender] Deepgram not connected. Attempting to connect/reconnect...")
                try:
                    if self.streaming_stt is None:
                        from services.ai.stt_engine import DeepgramStreamingClient
                        self.streaming_stt = DeepgramStreamingClient(sample_rate=16000)
                    await self.streaming_stt.connect()
                    logger.info("[STT Sender] Deepgram connected successfully.")
                    
                    if getattr(self, 'receiver_task', None) and not self.receiver_task.done():
                        self.receiver_task.cancel()
                    self.receiver_task = asyncio.create_task(self._stt_receiver_task())
                except Exception as e:
                    logger.error(f"[STT Sender] Failed to connect to Deepgram: {e}")
                    await asyncio.sleep(1.0)
                    continue

            if self.streaming_stt and self.streaming_stt.is_connected:
                await self.streaming_stt.send_audio(chunk)
                sent_count += 1
                if sent_count == 1 or sent_count % 50 == 0:
                    logger.info(f"[STT Sender] Forwarded chunk #{sent_count} to Deepgram ({len(chunk)} bytes)")
            else:
                logger.warning(f"[STT Sender] Deepgram not connected — dropping chunk")

    async def _commit_user_turn(self, text: str, source: str = "stt"):
        """Commits user spoken text, notifies the frontend, and generates AI reply."""
        clean_text = text.strip()
        if not clean_text:
            return
            
        logger.info(f"User ({source}): {clean_text}")
        try:
            await self.websocket.send_json({
                "type": "text",
                "speaker": "user",
                "text": clean_text
            })
        except Exception:
            pass
            
        self.interruption_event.clear()
        await self.handle_user_text(clean_text, play_voice=True)

    async def _stt_receiver_task(self):
        """Listens for results from Deepgram WebSocket and commits conversational turns."""
        logger.info("[DEBUG] _stt_receiver_task STARTED")
        if not self.streaming_stt:
            logger.warning("[DEBUG] _stt_receiver_task: No streaming_stt instance — exiting immediately!")
            return

        self.accumulated_text = ""
        logger.info(f"[DEBUG] _stt_receiver_task: About to call receive_results(). streaming_stt.is_connected={self.streaming_stt.is_connected}")
        try:
            async for result in self.streaming_stt.receive_results():
                if not self.is_active:
                    logger.info("[DEBUG] _stt_receiver_task: is_active=False, breaking")
                    break
                    
                text = result.get("text", "")
                is_final = result.get("is_final", False)
                speech_final = result.get("speech_final", False)
                is_utterance_end = result.get("utterance_end", False)
                
                logger.info(f"[DEBUG] STT result: text='{text}' is_final={is_final} speech_final={speech_final} utterance_end={is_utterance_end} ai_speaking={self.ai_speaking}")

                wpm = result.get("wpm")
                if text:
                    self.last_interaction_time = time.time()
                    self.silence_warnings = 0

                # Barge-in: only interrupt if the AI is actively speaking
                if text and self.ai_speaking:
                    import difflib
                    import string
                    clean_stt = text.lower().translate(str.maketrans('', '', string.punctuation)).strip()

                    # 1. Check for residual delayed STT of the user's OWN previous speech
                    messages = self._dialogue_state.get("messages", [])
                    if messages and getattr(messages[-1], "type", "") == "human":
                        clean_last_user = messages[-1].content.lower().translate(str.maketrans('', '', string.punctuation)).strip()
                        if clean_stt and clean_stt in clean_last_user:
                            logger.info(f"[AEC] Ignored delayed STT of user's own speech: '{text}'")
                            continue

                    # 2. Software AEC: check if STT text is just an echo of what the AI recently said
                    if self._recent_ai_transcripts:
                        ai_words = self._recent_ai_transcripts.split()[-20:]
                        clean_ai = " ".join(ai_words).lower().translate(str.maketrans('', '', string.punctuation)).strip()
                        if clean_stt and ((len(clean_stt) > 6 and clean_stt in clean_ai) or difflib.SequenceMatcher(None, clean_stt, clean_ai).ratio() > 0.75):
                            logger.info(f"[AEC] Ignored echo from speakerphone: '{text}'")
                            continue

                    logger.info(f"[DEBUG] Barge-in triggered by Deepgram result: '{text}' (ai_speaking was True)")
                    self.interruption_event.set()
                    try:
                        await self.websocket.send_json({"type": "barge_in"})
                    except Exception:
                        pass
                    self.ai_speaking = False
                    
                if is_final and text:
                    # Accumulate text avoiding duplicated full strings
                    if not self.accumulated_text:
                        self.accumulated_text = text
                    elif text not in self.accumulated_text:
                        self.accumulated_text = f"{self.accumulated_text} {text}"
                    self.last_word_time = time.time()
                    
                    if wpm:
                        self._wpm_history.append(wpm)
                        if len(self._wpm_history) > 5:
                            self._wpm_history.pop(0)
                        
                        avg_wpm = sum(self._wpm_history) / len(self._wpm_history)
                        if avg_wpm > 150:
                            self._pace_profile = "FAST"
                        elif avg_wpm < 110:
                            self._pace_profile = "SLOW"
                        else:
                            self._pace_profile = "NORMAL"
                        logger.debug(f"[Pacing] Avg WPM: {avg_wpm:.1f} -> Profile: {self._pace_profile}")
                        
                    logger.info(f"[DEBUG] STT accumulated text so far: '{self.accumulated_text}'")

                    # Snappy debounce timer: if speech_final doesn't arrive within 0.75s of a final segment, commit automatically
                    if self._stt_buffer_task and not self._stt_buffer_task.done():
                        self._stt_buffer_task.cancel()

                    async def auto_flush(expected_text: str):
                        try:
                            await asyncio.sleep(0.75)
                            if self.accumulated_text == expected_text and self.accumulated_text.strip():
                                text_to_commit = self.accumulated_text.strip()
                                self.accumulated_text = ""
                                await self._commit_user_turn(text_to_commit, source="Audio Debounce 0.75s")
                        except asyncio.CancelledError:
                            pass

                    self._stt_buffer_task = asyncio.create_task(auto_flush(self.accumulated_text))

                if speech_final or is_utterance_end:
                    logger.info(f"[DEBUG] speech_final/utterance_end fired. accumulated_text='{self.accumulated_text}'")
                    if self._stt_buffer_task and not self._stt_buffer_task.done():
                        self._stt_buffer_task.cancel()

                    if self.accumulated_text:
                        # Hanging word detection
                        hanging_words = {"to", "and", "but", "around", "about", "if", "or", "so", "like", "because", "then", "maybe"}
                        words = self.accumulated_text.split()
                        if words:
                            import string
                            last_word_clean = words[-1].lower().translate(str.maketrans('', '', string.punctuation))
                            if last_word_clean in hanging_words:
                                logger.info(f"[STT Receiver] Hanging word detected ('{last_word_clean}'). Waiting...")
                                continue

                        text_to_commit = self.accumulated_text.strip()
                        self.accumulated_text = ""
                        # Deepgram endpointing=300 has already verified user silence. Commit turn immediately with 0ms delay!
                        await self._commit_user_turn(text_to_commit, source="Audio Final fast-tracked")
                    else:
                        logger.info("[DEBUG] speech_final/utterance_end but accumulated_text is EMPTY — nothing to process")
        except Exception as e:
            logger.exception(f"[DEBUG] _stt_receiver_task CRASHED: {e}")
        logger.info("[DEBUG] _stt_receiver_task EXITED")

    async def _io_writer_task(self):
        """Dedicated background task for writing audio to disk without blocking the event loop."""
        while self.is_active or not self.io_queue.empty():
            try:
                item = await asyncio.wait_for(self.io_queue.get(), timeout=0.5)
                target, data = item
                if target == "user" and self.user_record_file:
                    await asyncio.to_thread(self.user_record_file.write, data)
                elif target == "ai" and self.ai_record_file:
                    await asyncio.to_thread(self.ai_record_file.writeframes, data)
                self.io_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in IO writer task: {e}")

    async def _idle_monitor(self):
        """Monitors conversational turns and sends check-ins during prolonged user silence."""
        while self.is_active:
            try:
                await asyncio.sleep(1.0)
                if not self.is_active:
                    break
                
                # Check if there is pending uncommitted speech buffered longer than 2.0s
                if self.accumulated_text and (time.time() - self.last_word_time > 2.0):
                    text_to_process = self.accumulated_text.strip()
                    self.accumulated_text = ""
                    logger.info(f"User (Audio Fallback Forced Final): {text_to_process}")
                    await self._commit_user_turn(text_to_process, source="Audio Fallback Forced Final")
                    
                if self.ai_speaking:
                    self.last_interaction_time = time.time()
                    continue
                
                # Check for 20s of total silence after AI finishes speaking
                idle_time = time.time() - self.last_interaction_time
                if idle_time > 20.0 and self.silence_warnings == 0:
                    self.silence_warnings = 1
                    logger.info("Prolonged silence (> 20s) detected.")
                    self.call_disposition = "DAIR"
                    try:
                        await self.websocket.send_json({
                            "type": "text",
                            "speaker": "ai",
                            "text": "Are you still with me? Just checking in."
                        })
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Error in _idle_monitor: {e}")

    async def run(self):
        """Main WebSocket loop."""
        await self.websocket.accept()
        logger.info("Browser test session connected via WebSocket")
        
        # Start Streaming STT connection — wrapped so a Deepgram failure doesn't crash the session
        try:
            self.streaming_stt = DeepgramStreamingClient(sample_rate=16000)
            await self.streaming_stt.connect()
            logger.info("Deepgram streaming STT connected successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to Deepgram streaming STT: {e}. Audio mic input will be disabled.")
            self.streaming_stt = None
        
        self.sender_task = asyncio.create_task(self._audio_sender_task())
        self.receiver_task = asyncio.create_task(self._stt_receiver_task())
        self.idle_task = asyncio.create_task(self._idle_monitor())
        self.io_task = asyncio.create_task(self._io_writer_task())
        self.keepalive_task = asyncio.create_task(self._deepgram_keepalive_task())
        
        # Trigger initial AI greeting (Step 0)
        # Small delay to let browser WebSocket handler + AudioContext initialize
        await asyncio.sleep(0.5)
        
        try:
            # Send a "ready" signal so the browser can unlock its AudioContext
            try:
                await self.websocket.send_json({"type": "ready"})
            except Exception:
                pass
            await asyncio.sleep(0.3)
            
            asyncio.create_task(self.stream_ai_reply(play_voice=True))
            
            print("[DEBUG] Entering main WebSocket receive loop", flush=True)
            while self.is_active:
                message = await self.websocket.receive()
                msg_type = message.get("type", "unknown")
                has_text = message.get("text") is not None
                has_bytes = message.get("bytes") is not None
                byte_len = len(message.get("bytes", b"")) if has_bytes else 0
                
                # Log every message type (but suppress repetitive binary audio logs)
                if has_text:
                    logger.info(f"[DEBUG] WS recv: type={msg_type} text={message.get('text', '')[:200]}")
                elif has_bytes and (self._audio_chunk_count == 0 or self._audio_chunk_count % 50 == 0):
                    logger.info(f"[DEBUG] WS recv: type={msg_type} bytes={byte_len} (chunk #{self._audio_chunk_count + 1})")
                
                if msg_type == "websocket.disconnect":
                    logger.info("[DEBUG] WebSocket disconnect received")
                    break
                    
                if message.get("text") is not None:
                    try:
                        msg = json.loads(message["text"])
                        if msg.get("type") == "text":
                            user_text = msg.get("text", "")
                            if user_text:
                                logger.info(f"User (Text): {user_text}")
                                # Manual text barge-in
                                self.interruption_event.set()
                                try:
                                    await self.websocket.send_json({"type": "barge_in"})
                                except Exception:
                                    pass # Ignore if client closed
                                await asyncio.sleep(0.1) # allow TTS to halt
                                self.interruption_event.clear()
                                await self.handle_user_text(user_text, play_voice=msg.get("play_voice", True))
                        elif msg.get("type") == "tts_finished":
                            self.ai_speaking = False
                            self._recent_ai_transcripts = ""
                            self.last_interaction_time = time.time()
                            logger.info("Frontend signaled TTS finished playback. Resetting idle timer and AEC echo buffer.")
                        elif msg.get("type") == "debug":
                            with open("vad_debug.log", "a") as f:
                                f.write(f"Frontend DEBUG: {msg}\n")
                    except (json.JSONDecodeError, TypeError):
                        logger.error("Invalid JSON from browser")
                        
                elif message.get("bytes") is not None:
                    raw_bytes = message.get("bytes")
                    chunk_size = len(raw_bytes)
                    self._audio_chunk_count += 1

                    # 86-byte chunks = WebM silence heartbeat frames (MediaRecorder keepalive).
                    # We must NOT drop them because WebM is a stateful container and dropping chunks corrupts the stream for Deepgram!

                    # Log first chunk and every 100th thereafter to avoid log spam
                    if self._audio_chunk_count == 1 or self._audio_chunk_count % 100 == 0:
                        logger.info(f"[Audio] Streaming mic audio — chunk #{self._audio_chunk_count}, {chunk_size} bytes")

                    if self.user_record_file:
                        try:
                            self.io_queue.put_nowait(("user", raw_bytes))
                        except Exception as e:
                            logger.error(f"Failed to queue user audio: {e}")

                    # Real audio arriving means user is active — reset the idle timer
                    self.last_interaction_time = time.time()

                    if not self.audio_queue.full():
                        await self.audio_queue.put(raw_bytes)
                    else:
                        logger.warning("[Audio] audio_queue is full — dropping chunk to avoid backlog")
                        
        except WebSocketDisconnect:
            logger.info("Browser test session disconnected")
        except Exception as e:
            logger.exception("Error in browser test session", exc_info=e)
        finally:
            self.is_active = False
            self.interruption_event.set()
            await self.audio_queue.put(None)
            
            if getattr(self, 'sender_task', None):
                self.sender_task.cancel()
            if getattr(self, 'receiver_task', None):
                self.receiver_task.cancel()
            if getattr(self, 'idle_task', None):
                self.idle_task.cancel()
            if getattr(self, 'keepalive_task', None):
                self.keepalive_task.cancel()
                
            if getattr(self, 'io_task', None):
                try:
                    await asyncio.wait_for(self.io_queue.join(), timeout=3.0)
                except asyncio.TimeoutError:
                    logger.warning("IO writer task queue did not finish in time.")
                except Exception:
                    pass
                self.io_task.cancel()
                
            if self.streaming_stt:
                await self.streaming_stt.close()
                
            if self.user_record_file:
                try:
                    self.user_record_file.close()
                except:
                    pass
            if self.ai_record_file:
                try:
                    self.ai_record_file.close()
                except:
                    pass
                    
            if self.settings.ENABLE_CALL_RECORDING:
                # Trigger muxing in a background thread so we don't block the event loop
                asyncio.create_task(asyncio.to_thread(self._mux_records))
                
            if not hasattr(self, "call_disposition") or not self.call_disposition:
                self.call_disposition = "HU"
                logger.info("User disconnected abruptly. Tagging disposition as HU.")
                
            # Fire webhook
            asyncio.create_task(self.sync_disposition_to_lms(self.call_disposition))
                
            try:
                await self.websocket.close()
            except:
                pass

    async def sync_disposition_to_lms(self, status: str):
        logger.info(f"Final Disposition computed: '{status}'")
        
        # Fire Webhook to Olivia LMS (if configured)
        if self.settings.OLIVIA_WEBHOOK_URL:
            logger.info(f"Firing Webhook to Olivia LMS: {self.settings.OLIVIA_WEBHOOK_URL}")
            payload = {
                "lead_id": "BROWSER_TEST_LEAD",
                "disposition": status,
                "timestamp": time.time(),
                "fsm_state": self._dialogue_state.get("fsm_state", "UNKNOWN")
            }
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(self.settings.OLIVIA_WEBHOOK_URL, json=payload)
                    logger.info(f"Olivia Webhook response: {resp.status_code}")
            except Exception as e:
                logger.error(f"Failed to hit Olivia Webhook: {e}")
        else:
            logger.warning("OLIVIA_WEBHOOK_URL not set in .env. Skipping webhook.")

    async def handle_user_text(self, text: str, play_voice: bool = True):
        import copy
        import time
        logger.info(f"[DEBUG] handle_user_text called with text='{text}' play_voice={play_voice}")
        
        ai_was_interrupted = False
        interruption_delay = time.time() - getattr(self, "_last_ai_start_time", 0)
        
        if hasattr(self, "current_ai_task") and self.current_ai_task and not self.current_ai_task.done():
            logger.info(f"Cancelling previous AI generation task due to new user input. Interruption delay: {interruption_delay:.2f}s")
            self.current_ai_task.cancel()
            ai_was_interrupted = True

        if ai_was_interrupted and interruption_delay < 2.5:
            logger.info("Early barge-in detected. Rolling back dialogue state and merging text.")
            if hasattr(self, "_previous_dialogue_state"):
                self._dialogue_state = copy.deepcopy(self._previous_dialogue_state)
                
            messages = list(self._dialogue_state["messages"])
            if messages and getattr(messages[-1], "type", "") == "human":
                logger.info(f"Merging fragmented user input: '{text}' into previous message.")
                messages[-1] = HumanMessage(content=messages[-1].content + " " + text)
            else:
                messages.append(HumanMessage(content=text))
                
            # Only play backchannel filler for longer conversational inputs, questions, or objections.
            # Simple 1-4 word qualification answers already have natural scripted confirmations in the node.
            words = text.strip().split()
            clean_lower = text.lower()
            is_simple_answer = len(words) <= 4 and not any(q in clean_lower for q in ["?", "what", "who", "why", "how", "scam", "cost", "fee", "explain"])
            play_backchannel = not is_simple_answer
            
        self._dialogue_state["messages"] = messages
        
        logger.info(f"[DEBUG] Launching stream_ai_reply task... (play_backchannel={play_backchannel})")
        self.current_ai_task = asyncio.create_task(self.stream_ai_reply(play_voice=play_voice, play_backchannel=play_backchannel))

    async def stream_ai_reply(self, play_voice: bool = True, play_backchannel: bool = False):
        import copy
        import time
        import random
        import os
        import base64
        self.ai_speaking = True
        self._recent_ai_transcripts = ""
        
        # Save state for potential early barge-in rollbacks
        self._previous_dialogue_state = copy.deepcopy(self._dialogue_state)
        self._last_ai_start_time = time.time()
        
        try:
            print("[DEBUG] stream_ai_reply STARTED", flush=True)
            self.interruption_event.clear()
            
            token_queue = asyncio.Queue()
            streamed_chars = 0
            
            async def _stream_cb(chunk: str):
                nonlocal streamed_chars
                streamed_chars += len(chunk)
                await token_queue.put(chunk)
                
            self.dialogue_manager._current_stream_callback = _stream_cb
            
            async def _generate_task():
                try:
                    new_state = await self.dialogue_manager.generate_reply(self._dialogue_state, session_id=self.session_id)
                    self._dialogue_state = new_state
                    # Fix: If the response was a fast-path static response, it didn't stream.
                    if streamed_chars == 0 and new_state.get("messages"):
                        last_msg = new_state["messages"][-1].content
                        await token_queue.put(last_msg)
                    try:
                        await self.websocket.send_json({
                            "type": "state_update",
                            "script_step": new_state.get("script_step", 1),
                            "fsm_state": new_state.get("fsm_state", "QUALIFICATION")
                        })
                    except:
                        pass
                except Exception as e:
                    logger.error(f"[Orchestrator] AI generation failed (e.g. rate limit): {e}")
                    await async_log_error(e, "AI generation task in browser_test")
                finally:
                    await token_queue.put(None)
                    self.dialogue_manager._current_stream_callback = None
                    
            # 1. Start LLM generation IMMEDIATELY in background (0ms latency start)
            gen_task = asyncio.create_task(_generate_task())
            
            # 2. Concurrently stream contextual filler from RAM if requested
            if play_voice and play_backchannel and not self.interruption_event.is_set():
                try:
                    await self._play_contextual_filler()
                except Exception as e:
                    logger.error(f"Failed to inject filler: {e}")
                    await async_log_error(e, "Filler Injection in browser_test")
            
            buffer = ""
            import re
            sentence_regex_first = re.compile(r'([.!?;:\n,]+)')
            sentence_regex_normal = re.compile(r'([.!?;:\n]+)')
            is_first_chunk = True
            
            disconnect_after = False
            
            while True:
                token = await token_queue.get()
                if token is None:
                    break
                    
                if self.interruption_event.is_set():
                    break
                    
                buffer += token
                
                active_regex = sentence_regex_first if is_first_chunk else sentence_regex_normal
                
                if active_regex.search(buffer):
                    parts = active_regex.split(buffer)
                    complete_sentences = ""
                    new_buffer = ""
                    for i in range(0, len(parts) - 1, 2):
                        sentence = parts[i] + parts[i+1]
                        complete_sentences += sentence
                    if len(parts) % 2 != 0:
                        new_buffer = parts[-1]
                        
                    if complete_sentences.strip():
                        text_to_synth = complete_sentences.strip()
                        self._recent_ai_transcripts += " " + text_to_synth
                        
                        import re
                        end_match = re.search(r"<<END_CALL(?::([^>]+))?>>", text_to_synth)
                        if end_match:
                            disconnect_after = True
                            text_to_synth = re.sub(r"<<END_CALL(?::[^>]+)?>>", "", text_to_synth).strip()
                            
                        xfer_match = re.search(r"<<TRANSFER(?::([^>]+))?>>", text_to_synth)
                        if xfer_match:
                            transfer_after = True
                            disconnect_after = True
                            text_to_synth = re.sub(r"<<TRANSFER(?::[^>]+)?>>", "", text_to_synth).strip()
                        
                        if text_to_synth:
                            if play_voice and not self.interruption_event.is_set():
                                await self._synthesize_and_send_sentence(text_to_synth)
                                is_first_chunk = False
                            elif not play_voice:
                                await self._send_text_sentence(text_to_synth)
                                is_first_chunk = False
                            
                    buffer = new_buffer
                    
            if buffer.strip() and not self.interruption_event.is_set():
                text_to_synth = buffer.strip()
                self._recent_ai_transcripts += " " + text_to_synth
                
                import re
                end_match = re.search(r"<<END_CALL(?::([^>]+))?>>", text_to_synth)
                if end_match:
                    disconnect_after = True
                    text_to_synth = re.sub(r"<<END_CALL(?::[^>]+)?>>", "", text_to_synth).strip()
                    
                xfer_match = re.search(r"<<TRANSFER(?::([^>]+))?>>", text_to_synth)
                if xfer_match:
                    transfer_after = True
                    disconnect_after = True
                    text_to_synth = re.sub(r"<<TRANSFER(?::[^>]+)?>>", "", text_to_synth).strip()
                if text_to_synth:
                    if play_voice:
                        await self._synthesize_and_send_sentence(text_to_synth)
                    else:
                        await self._send_text_sentence(text_to_synth)
                    
            await gen_task
            
            if not play_voice:
                self.ai_speaking = False
            self.last_interaction_time = time.time()
            
            if disconnect_after and not self.interruption_event.is_set():
                logger.info("Call tagged for END_CALL. Waiting for TTS playback to finish...")
                for _ in range(300): # 30 seconds max timeout
                    if not self.ai_speaking or self.interruption_event.is_set():
                        break
                    await asyncio.sleep(0.1)
                    
                logger.info("Disconnecting call due to <<END_CALL>> tag")
                try:
                    await self.websocket.send_json({"type": "end_call", "reason": "script_ended"})
                    await asyncio.sleep(0.5)
                    await self.websocket.close()
                except Exception:
                    pass
                return
                
            print("[DEBUG] stream_ai_reply FINISHED successfully", flush=True)
            
        except Exception as e:
            import traceback
            print(f"\n[CRITICAL ERROR in stream_ai_reply]: {e}\n{traceback.format_exc()}\n", flush=True)
            logger.exception(f"Error in stream_ai_reply: {e}")
            await async_log_error(e, "Critical error in stream_ai_reply (browser_test)")
        finally:
            if not play_voice:
                self.ai_speaking = False

    # ------------------------------------------------------------------
    # CONTEXTUAL FILLER SYSTEM
    # Uses ElevenLabs TTS (same voice) to pre-cache natural fillers.
    # Fillers are categorized by sentiment and selected based on
    # the user's last message tone. They bridge the gap until the
    # LLM response arrives, spoken in the same voice/pitch.
    # ------------------------------------------------------------------
    FILLER_PHRASES = {
        # Neutral — safe for any context, buying time
        "neutral": [
            "Okay, so...",
            "Sure, let me just...",
            "Alright...",
            "Got it...",
            "Mm-hmm...",
        ],
        # Empathetic — for negative/hardship context (layoffs, struggles, stress)
        "empathetic": [
            "Yeah, I hear you...",
            "I understand...",
            "That makes sense...",
            "Of course...",
            "I appreciate you sharing that...",
        ],
        # Positive — for affirmative/good news context
        "positive": [
            "Perfect...",
            "Great...",
            "Awesome, okay...",
            "That's great to hear...",
            "Wonderful...",
        ],
    }

    # Keywords to detect empathetic vs positive context from user's last message
    _EMPATHY_KEYWORDS = {
        "laid off", "lost my job", "unemployed", "struggling", "can't afford",
        "behind on", "difficult", "tough", "hard time", "worried", "stress",
        "divorced", "passed away", "medical", "disability", "sick", "debt",
        "bills", "collection", "garnish", "foreclosure", "evict", "bankrupt",
    }
    _POSITIVE_KEYWORDS = {
        "yes", "yeah", "yep", "sure", "correct", "right", "absolutely",
        "definitely", "of course", "sounds good", "perfect", "great",
        "good", "okay", "working", "employed", "married",
    }

    def _detect_filler_sentiment(self, user_text: str) -> str:
        """Detect whether the user's message warrants an empathetic, positive, or neutral filler."""
        text_lower = user_text.lower()
        
        # Check empathy keywords first (they take priority over positive)
        for phrase in self._EMPATHY_KEYWORDS:
            if phrase in text_lower:
                return "empathetic"
        
        # Check positive keywords
        for phrase in self._POSITIVE_KEYWORDS:
            if phrase in text_lower:
                return "positive"
        
        return "neutral"

    async def _play_contextual_filler(self):
        """
        Selects and plays a sentiment-appropriate filler using the same ElevenLabs
        voice as the main AI. Pre-caches base64 chunks to RAM for 0ms playback.
        """
        import random
        import base64

        # Determine sentiment from the last user message
        messages = self._dialogue_state.get("messages", [])
        last_user_text = ""
        for msg in reversed(messages):
            if getattr(msg, "type", "") == "human":
                last_user_text = msg.content
                break

        sentiment = self._detect_filler_sentiment(last_user_text)
        filler_options = self.FILLER_PHRASES.get(sentiment, self.FILLER_PHRASES["neutral"])
        filler_text = random.choice(filler_options)

        logger.info(f"[Filler] Sentiment={sentiment} → Playing: '{filler_text}'")

        # 1. Check in-memory RAM cache for 0ms streaming
        if filler_text in _RAM_FILLER_CACHE:
            logger.info(f"[Filler RAM Hit] '{filler_text}'")
            for b64_chunk in _RAM_FILLER_CACHE[filler_text]:
                if self.interruption_event.is_set():
                    break
                await self.websocket.send_json({
                    "type": "audio_chunk",
                    "audio_base64": b64_chunk,
                    "sample_rate": 24000
                })
            return

        # 2. Otherwise synthesize with disk caching and populate RAM cache
        cached_chunks = []
        try:
            async for chunk in self.tts_engine._synthesize_sentence_stream(filler_text, use_cache=True):
                if self.interruption_event.is_set():
                    break
                if chunk:
                    if self.ai_record_file:
                        try:
                            self.io_queue.put_nowait(("ai", chunk))
                        except:
                            pass

                    b64_audio = base64.b64encode(chunk).decode("utf-8")
                    cached_chunks.append(b64_audio)
                    await self.websocket.send_json({
                        "type": "audio_chunk",
                        "audio_base64": b64_audio,
                        "sample_rate": 24000
                    })
            if cached_chunks and not self.interruption_event.is_set():
                _RAM_FILLER_CACHE[filler_text] = cached_chunks
        except Exception as e:
            logger.error(f"[Filler] TTS synthesis failed: {e}")

    async def _synthesize_and_send_sentence(self, sentence: str):
        clean_text_for_tts = sentence.replace("**", "").replace("*", "").replace("_", "")
        import re, base64
        ui_text = re.sub(r'<[^>]+>', '', sentence).strip()
        ui_text = re.sub(r'\s+', ' ', ui_text)
        
        if not ui_text: return
        
        # Send the text to the UI immediately so the user can read it
        await self._send_text_sentence(ui_text)
        
        try:
            async for chunk in self.tts_engine._synthesize_sentence_stream(clean_text_for_tts, use_cache=True):
                if self.interruption_event.is_set():
                    break
                if chunk:
                    if self.ai_record_file:
                        try:
                            self.io_queue.put_nowait(("ai", chunk))
                        except Exception as e:
                            logger.error(f"Failed to queue AI audio: {e}")
                            
                    b64_audio = base64.b64encode(chunk).decode("utf-8")
                    try:
                        await self.websocket.send_json({
                            "type": "audio_chunk",
                            "audio_base64": b64_audio,
                            "sample_rate": 24000
                        })
                    except Exception:
                        pass # Ignore if client closed
        except Exception as e:
            logger.error(f"[TTS] Failed to generate/send sentence: {e}", exc_info=True)
            
    async def _send_text_sentence(self, sentence: str):
        import re
        ui_text = re.sub(r'<[^>]+>', '', sentence).strip()
        ui_text = re.sub(r'\s+', ' ', ui_text)
        if not ui_text: return
        
        logger.info(f"AI: {ui_text}")
        try:
            await self.websocket.send_json({
                "type": "sentence",
                "speaker": "ai",
                "text": ui_text,
                "audio_base64": None
            })
        except:
            pass

    def _mux_records(self):
        """Muxes the user.webm and ai.wav into a single stereo combined.wav file using PyAV."""
        try:
            import av
            import numpy as np
            logger.info("Muxing audio recordings into a single file...")
            
            user_audio = None
            if os.path.exists(self.user_record_path):
                try:
                    container = av.open(self.user_record_path)
                    if container.streams.audio:
                        stream = container.streams.audio[0]
                        resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
                        frames = []
                        for frame in container.decode(stream):
                            frame.pts = None
                            for rf in resampler.resample(frame):
                                frames.append(rf.to_ndarray()[0])
                        for rf in resampler.resample(None):
                            frames.append(rf.to_ndarray()[0])
                        if frames:
                            user_audio = np.concatenate(frames)
                except Exception as e:
                    logger.error(f"Failed to read user WebM for muxing: {e}")

            ai_audio = None
            if os.path.exists(self.ai_record_path):
                try:
                    with wave.open(self.ai_record_path, 'rb') as wf:
                        audio_bytes = wf.readframes(wf.getnframes())
                        ai_audio = np.frombuffer(audio_bytes, dtype=np.int16)
                except Exception as e:
                    logger.error(f"Failed to read AI WAV for muxing: {e}")

            if user_audio is None and ai_audio is None:
                return

            if user_audio is None: user_audio = np.array([], dtype=np.int16)
            if ai_audio is None: ai_audio = np.array([], dtype=np.int16)

            max_len = max(len(user_audio), len(ai_audio))
            stereo = np.empty((max_len, 2), dtype=np.int16)
            
            user_padded = np.zeros(max_len, dtype=np.int16)
            user_padded[:len(user_audio)] = user_audio
            
            ai_padded = np.zeros(max_len, dtype=np.int16)
            ai_padded[:len(ai_audio)] = ai_audio

            stereo[:, 0] = user_padded
            stereo[:, 1] = ai_padded

            with wave.open(self.combined_record_path, 'wb') as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(stereo.tobytes())
                
            logger.info(f"Successfully created {self.combined_record_path}")
            
            # Clean up the individual files now that we have a combined one
            try:
                os.remove(self.user_record_path)
                os.remove(self.ai_record_path)
            except:
                pass
                
        except ImportError:
            logger.error("PyAV is not installed. Cannot combine recordings. Install 'av' and 'numpy' to enable this feature.")
        except Exception as e:
            logger.exception(f"Unexpected error during audio muxing: {e}")
