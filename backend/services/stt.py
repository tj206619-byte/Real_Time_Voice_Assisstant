import asyncio
import logging
from typing import Callable, Optional, Dict, Any
from backend.config import settings

logger = logging.getLogger("voicepilot.stt")

class StreamingSTTService:
    def __init__(
        self,
        on_transcript: Callable[[str, bool], Any],
        api_key: Optional[str] = None
    ):
        """
        Streaming Speech-To-Text Handler.
        on_transcript: callback receiving (transcript_text, is_final)
        """
        self.on_transcript = on_transcript
        self.api_key = api_key or settings.DEEPGRAM_API_KEY
        self.is_running = False
        self.dg_connection = None
        self._deepgram_client = None

        if self.api_key and self.api_key.strip() and not self.api_key.startswith("your_"):
            try:
                from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
                self._deepgram_client = DeepgramClient(self.api_key)
                self._LiveTranscriptionEvents = LiveTranscriptionEvents
                self._LiveOptions = LiveOptions
            except Exception as e:
                logger.warning(f"Deepgram client initialization failed: {e}")

    async def start(self):
        """Initialize the STT streaming connection."""
        self.is_running = True
        if self._deepgram_client:
            try:
                self.dg_connection = self._deepgram_client.listen.asyncwebsocket.v("1")

                async def on_message(self_dg, result, **kwargs):
                    sentence = result.channel.alternatives[0].transcript
                    if len(sentence) > 0:
                        is_final = result.is_final
                        if asyncio.iscoroutinefunction(self.on_transcript):
                            await self.on_transcript(sentence, is_final)
                        else:
                            self.on_transcript(sentence, is_final)

                async def on_error(self_dg, error, **kwargs):
                    logger.error(f"Deepgram STT error: {error}")

                self.dg_connection.on(self._LiveTranscriptionEvents.Transcript, on_message)
                self.dg_connection.on(self._LiveTranscriptionEvents.Error, on_error)

                options = self._LiveOptions(
                    model="nova-2",
                    punctuate=True,
                    language="en-US",
                    encoding="linear16",
                    channels=1,
                    sample_rate=16000,
                    endpointing=300
                )
                await self.dg_connection.start(options)
                logger.info("Deepgram streaming STT connection established.")
            except Exception as e:
                logger.warning(f"Could not connect to Deepgram live WebSocket: {e}. Falling back to browser/direct STT.")
                self.dg_connection = None

    async def send_audio_chunk(self, audio_data: bytes):
        """Forward raw PCM audio chunk to STT provider."""
        if not self.is_running:
            return
        if self.dg_connection:
            try:
                await self.dg_connection.send(audio_data)
            except Exception as e:
                logger.error(f"Error sending audio to Deepgram: {e}")

    async def stop(self):
        """Close STT streaming connection."""
        self.is_running = False
        if self.dg_connection:
            try:
                await self.dg_connection.finish()
            except Exception as e:
                logger.error(f"Error closing Deepgram connection: {e}")
            finally:
                self.dg_connection = None
