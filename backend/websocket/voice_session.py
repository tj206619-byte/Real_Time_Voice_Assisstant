import asyncio
import base64
import json
import logging
import time
from typing import Optional, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect

from backend.agent.agent import VoicePilotAgent
from backend.services.stt import StreamingSTTService
from backend.services.tts import StreamingTTSService
from backend.tools.reminder_tool import get_all_reminders
from backend.tools.task_tool import get_all_tasks

logger = logging.getLogger("voicepilot.session")

class VoiceSession:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.state: str = "IDLE"  # IDLE, LISTENING, THINKING, TOOL_CALLING, SPEAKING, INTERRUPTED, ERROR
        self.agent = VoicePilotAgent()
        self.tts_service = StreamingTTSService()
        self.current_response_id: int = 0
        self.active_turn_task: Optional[asyncio.Task] = None
        self.is_interrupted: bool = False
        
        # Latency tracking timestamps
        self.timestamps: Dict[str, float] = {}

        # STT Service instance
        self.stt_service = StreamingSTTService(on_transcript=self.handle_stt_transcript)

    async def send_json(self, message: Dict[str, Any]):
        """Safe WebSocket JSON transmission."""
        try:
            await self.websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.debug(f"Failed to send JSON message: {e}")

    async def set_state(self, new_state: str):
        """Update session state and notify client."""
        self.state = new_state
        await self.send_json({
            "type": "state",
            "value": new_state.lower(),
            "response_id": self.current_response_id
        })

    async def handle_stt_transcript(self, transcript: str, is_final: bool):
        """Callback from STT engine when speech is transcribed."""
        if not transcript.strip():
            return

        if is_final:
            self.timestamps["transcript_final"] = time.time()
            await self.send_json({
                "type": "transcript_final",
                "text": transcript
            })
            # Trigger assistant turn
            await self.on_user_utterance(transcript)
        else:
            await self.send_json({
                "type": "transcript_partial",
                "text": transcript
            })

    async def interrupt_current_response(self):
        """
        Barge-in: Immediately cancels active assistant response and TTS streaming.
        """
        if self.state in ["SPEAKING", "THINKING", "TOOL_CALLING"]:
            logger.info(f"Barge-In detected! Cancelling response_id {self.current_response_id}")
            self.is_interrupted = True
            
            # Cancel background task
            if self.active_turn_task and not self.active_turn_task.done():
                self.active_turn_task.cancel()
                self.active_turn_task = None

            await self.set_state("INTERRUPTED")
            
            # Notify client to immediately flush audio playback
            await self.send_json({
                "type": "interrupt",
                "cancelled_response_id": self.current_response_id
            })

    async def on_user_utterance(self, user_text: str):
        """Process a completed user speech turn."""
        if not user_text or not user_text.strip():
            return

        # Increment response generation ID
        self.current_response_id += 1
        response_id = self.current_response_id
        self.is_interrupted = False

        # Cancel any previous running turn task
        if self.active_turn_task and not self.active_turn_task.done():
            self.active_turn_task.cancel()

        # Reset latency timers
        self.timestamps = {
            "speech_end": self.timestamps.get("speech_end", time.time()),
            "transcript_final": self.timestamps.get("transcript_final", time.time()),
            "llm_start": time.time(),
            "tool_start": 0.0,
            "tool_end": 0.0,
            "first_token": 0.0,
            "first_audio": 0.0
        }

        # Spawn turn execution task
        self.active_turn_task = asyncio.create_task(
            self._execute_turn(user_text, response_id)
        )

    async def _execute_turn(self, user_text: str, response_id: int):
        """Core execution pipeline for a turn."""
        try:
            await self.set_state("THINKING")

            def check_cancelled() -> bool:
                return self.is_interrupted or (self.current_response_id != response_id)

            async def on_tool_start(name: str, args: Dict[str, Any]):
                if check_cancelled():
                    return
                self.timestamps["tool_start"] = time.time()
                await self.set_state("TOOL_CALLING")
                await self.send_json({
                    "type": "tool_start",
                    "tool": name,
                    "args": args,
                    "response_id": response_id
                })

            async def on_tool_finish(name: str, result: Dict[str, Any]):
                if check_cancelled():
                    return
                self.timestamps["tool_end"] = time.time()
                await self.send_json({
                    "type": "tool_result",
                    "tool": name,
                    "result": result,
                    "response_id": response_id
                })
                # Broadcast updated data for tasks / reminders
                if name in ["create_reminder", "create_task"]:
                    await self.broadcast_data_update()

            accumulated_text = ""
            sentence_buffer = ""
            first_token_received = False
            first_audio_sent = False

            async for token in self.agent.process_turn(
                user_text,
                on_tool_start=on_tool_start,
                on_tool_finish=on_tool_finish,
                is_cancelled=check_cancelled
            ):
                if check_cancelled():
                    return

                if not first_token_received:
                    first_token_received = True
                    self.timestamps["first_token"] = time.time()

                accumulated_text += token
                sentence_buffer += token

                await self.send_json({
                    "type": "llm_chunk",
                    "text": token,
                    "response_id": response_id
                })

                # Stream TTS on sentence or natural pause boundary for low perceived latency
                if any(punct in sentence_buffer for punct in [". ", "? ", "! ", "\n"]):
                    speech_clause = sentence_buffer
                    sentence_buffer = ""
                    
                    if not check_cancelled():
                        await self.set_state("SPEAKING")
                        async for audio_bytes in self.tts_service.stream_speech(speech_clause, check_cancelled):
                            if check_cancelled():
                                return
                            if not first_audio_sent:
                                first_audio_sent = True
                                self.timestamps["first_audio"] = time.time()
                                await self._send_latency_metrics(response_id)

                            # Send audio chunk
                            await self.send_json({
                                "type": "audio_chunk",
                                "data": base64.b64encode(audio_bytes).decode("utf-8"),
                                "response_id": response_id
                            })

            # Stream any remaining text in sentence buffer
            if sentence_buffer.strip() and not check_cancelled():
                await self.set_state("SPEAKING")
                async for audio_bytes in self.tts_service.stream_speech(sentence_buffer, check_cancelled):
                    if check_cancelled():
                        return
                    if not first_audio_sent:
                        first_audio_sent = True
                        self.timestamps["first_audio"] = time.time()
                        await self._send_latency_metrics(response_id)

                    await self.send_json({
                        "type": "audio_chunk",
                        "data": base64.b64encode(audio_bytes).decode("utf-8"),
                        "response_id": response_id
                    })

            if not check_cancelled():
                await self.send_json({
                    "type": "audio_end",
                    "response_id": response_id
                })
                # After speaking finishes, return to IDLE / LISTENING
                await self.set_state("LISTENING")

        except asyncio.CancelledError:
            logger.info(f"Turn task {response_id} cancelled.")
        except Exception as e:
            logger.error(f"Error in turn task {response_id}: {e}", exc_info=True)
            await self.set_state("ERROR")
            await self.send_json({
                "type": "error",
                "message": "An error occurred while processing your request.",
                "response_id": response_id
            })

    async def _send_latency_metrics(self, response_id: int):
        """Calculate and dispatch latency metrics to client."""
        t_speech_end = self.timestamps.get("speech_end", 0)
        t_final = self.timestamps.get("transcript_final", 0)
        t_llm_start = self.timestamps.get("llm_start", 0)
        t_tool_start = self.timestamps.get("tool_start", 0)
        t_tool_end = self.timestamps.get("tool_end", 0)
        t_first_token = self.timestamps.get("first_token", 0)
        t_first_audio = self.timestamps.get("first_audio", 0)

        tool_latency = (t_tool_end - t_tool_start) if (t_tool_start and t_tool_end) else 0.0
        llm_first_token_latency = (t_first_token - t_llm_start) if (t_llm_start and t_first_token) else 0.0
        tts_first_audio_latency = (t_first_audio - t_first_token) if (t_first_token and t_first_audio) else 0.0
        total_roundtrip = (t_first_audio - t_llm_start) if (t_llm_start and t_first_audio) else 0.0

        metrics = {
            "tool_latency_s": round(tool_latency, 3),
            "llm_first_token_s": round(llm_first_token_latency, 3),
            "tts_first_audio_s": round(tts_first_audio_latency, 3),
            "total_roundtrip_s": round(total_roundtrip, 3)
        }

        await self.send_json({
            "type": "metrics",
            "metrics": metrics,
            "response_id": response_id
        })

    async def broadcast_data_update(self):
        """Send refreshed tasks and reminders to UI."""
        try:
            reminders = await get_all_reminders()
            tasks = await get_all_tasks()
            await self.send_json({
                "type": "data_update",
                "reminders": reminders,
                "tasks": tasks
            })
        except Exception as e:
            logger.error(f"Failed to fetch data update: {e}")

    async def handle_client_message(self, message_text: str):
        """Route incoming WebSocket messages from client."""
        try:
            data = json.loads(message_text)
            msg_type = data.get("type")

            if msg_type == "session_start":
                await self.stt_service.start()
                self.agent.reset()
                await self.set_state("LISTENING")
                await self.broadcast_data_update()

            elif msg_type == "interrupt":
                await self.interrupt_current_response()

            elif msg_type == "audio_chunk":
                # Raw audio chunk from browser mic
                raw_b64 = data.get("data", "")
                if raw_b64:
                    raw_bytes = base64.b64decode(raw_b64)
                    await self.stt_service.send_audio_chunk(raw_bytes)

            elif msg_type == "user_transcript":
                # Direct transcript from client (Browser STT / Web Speech API fallback)
                text = data.get("text", "")
                is_final = data.get("is_final", True)
                
                # If assistant is currently speaking and user speaks, trigger barge-in first
                if self.state == "SPEAKING":
                    await self.interrupt_current_response()

                self.timestamps["speech_end"] = time.time()
                await self.handle_stt_transcript(text, is_final)

            elif msg_type == "config_update":
                # Update runtime API keys or models from UI settings
                cfg = data.get("config", {})
                gemini_key = cfg.get("gemini_key")
                gemini_model = cfg.get("gemini_model")
                openai_key = cfg.get("openai_key")
                openai_model = cfg.get("model")

                if gemini_key:
                    self.agent = VoicePilotAgent(api_key=gemini_key, model=gemini_model)
                elif openai_key:
                    self.agent = VoicePilotAgent(api_key=openai_key, model=openai_model)
                elif gemini_model:
                    self.agent = VoicePilotAgent(model=gemini_model)

                if "elevenlabs_key" in cfg:
                    self.tts_service = StreamingTTSService(
                        elevenlabs_key=cfg["elevenlabs_key"],
                        voice_id=cfg.get("voice_id")
                    )

            elif msg_type == "get_data":
                await self.broadcast_data_update()

        except Exception as e:
            logger.error(f"Error processing client message: {e}", exc_info=True)

    async def close(self):
        """Clean up resources on disconnect."""
        await self.stt_service.stop()
        if self.active_turn_task and not self.active_turn_task.done():
            self.active_turn_task.cancel()
