import asyncio
import base64
import logging
from typing import AsyncGenerator, Optional, Callable
import httpx
import edge_tts
from backend.config import settings

logger = logging.getLogger("voicepilot.tts")

class StreamingTTSService:
    def __init__(
        self,
        elevenlabs_key: Optional[str] = None,
        voice_id: Optional[str] = None
    ):
        self.elevenlabs_key = elevenlabs_key or settings.ELEVENLABS_API_KEY
        self.voice_id = voice_id or settings.ELEVENLABS_VOICE_ID or "21m00Tcm4TlvDq8ikWAM"
        self.default_edge_voice = "en-US-JennyNeural"

    async def stream_speech(
        self,
        text: str,
        is_cancelled: Optional[Callable[[], bool]] = None
    ) -> AsyncGenerator[bytes, None]:
        """
        Convert text into streaming audio chunks.
        Checks `is_cancelled` before yielding each chunk.
        """
        if not text or not text.strip():
            return

        clean_text = text.replace("*", "").replace("#", "").replace("`", "").strip()

        # Try ElevenLabs if configured
        if self.elevenlabs_key and self.elevenlabs_key.strip() and not self.elevenlabs_key.startswith("your_"):
            try:
                async for chunk in self._stream_elevenlabs(clean_text, is_cancelled):
                    yield chunk
                return
            except Exception as e:
                logger.warning(f"ElevenLabs TTS failed: {e}. Falling back to Edge-TTS.")

        # Fallback to high-speed neural Edge-TTS
        try:
            async for chunk in self._stream_edge_tts(clean_text, is_cancelled):
                yield chunk
        except Exception as e:
            logger.error(f"Edge-TTS stream error: {e}")

    async def _stream_elevenlabs(
        self,
        text: str,
        is_cancelled: Optional[Callable[[], bool]] = None
    ) -> AsyncGenerator[bytes, None]:
        """Stream audio from ElevenLabs API."""
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.elevenlabs_key
        }
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"ElevenLabs error code {response.status_code}")

                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if is_cancelled and is_cancelled():
                        logger.info("ElevenLabs streaming cancelled by user barge-in.")
                        return
                    if chunk:
                        yield chunk

    async def _stream_edge_tts(
        self,
        text: str,
        is_cancelled: Optional[Callable[[], bool]] = None
    ) -> AsyncGenerator[bytes, None]:
        """Stream audio using Edge-TTS (Microsoft Neural Voice)."""
        communicate = edge_tts.Communicate(text, self.default_edge_voice)
        
        async for chunk in communicate.stream():
            if is_cancelled and is_cancelled():
                logger.info("Edge-TTS streaming cancelled by user barge-in.")
                return

            if chunk["type"] == "audio":
                yield chunk["data"]
