"""
Text-to-Speech engine using gTTS and pygame.
Supports bilingual announcements (Thai/English) with proper timing.
"""

import asyncio
import time
from pathlib import Path
from typing import Optional
from tempfile import NamedTemporaryFile

from gtts import gTTS
import pygame

from ...config import get_settings, STATUS_EN
from ...shared.logging_config import get_logger

logger = get_logger("surgibot.tts")


class TTSEngine:
    """Text-to-Speech engine for announcements."""

    def __init__(self):
        self.settings = get_settings()
        self.enabled = self.settings.enable_tts
        self._lock = asyncio.Lock()
        self._initialized = False

    def _ensure_pygame(self):
        """Ensure pygame mixer is initialized."""
        if not self._initialized:
            try:
                pygame.mixer.init()
                self._initialized = True
            except Exception as e:
                logger.error(f"Failed to initialize pygame mixer: {e}")

    async def speak_text(
        self, text: str, lang: str = "th", max_wait_s: int = 120
    ) -> bool:
        """
        Speak text using gTTS and pygame.

        Args:
            text: Text to speak
            lang: Language code ('th' or 'en')
            max_wait_s: Maximum wait time in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            logger.debug("TTS disabled, skipping speech")
            return False

        async with self._lock:
            try:
                # Generate speech file
                with NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp_path = tmp.name

                await asyncio.to_thread(gTTS(text=text, lang=lang).save, tmp_path)

                # Play audio
                self._ensure_pygame()
                try:
                    pygame.mixer.music.stop()
                except Exception:
                    pass

                await asyncio.to_thread(pygame.mixer.music.load, tmp_path)
                await asyncio.to_thread(pygame.mixer.music.play)

                # Wait for playback to finish
                start = time.time()
                while pygame.mixer.music.get_busy():
                    if time.time() - start > max_wait_s:
                        logger.warning("TTS playback timeout")
                        break
                    await asyncio.sleep(0.1)

                # Cleanup
                try:
                    pygame.mixer.music.stop()
                except Exception:
                    pass

                try:
                    Path(tmp_path).unlink()
                except Exception:
                    pass

                logger.debug(f"Spoke: {text[:50]}... (lang={lang})")
                return True

            except Exception as e:
                logger.error(f"TTS error: {e}", exc_info=True)
                return False

    async def speak_bilingual(
        self, thai_text: str, english_text: str, pause_ms: int = 600
    ) -> bool:
        """
        Speak bilingual announcement (Thai first, then English).

        Args:
            thai_text: Thai text
            english_text: English text
            pause_ms: Pause duration between languages (milliseconds)

        Returns:
            True if successful, False otherwise
        """
        success_th = await self.speak_text(thai_text, lang="th")
        await asyncio.sleep(pause_ms / 1000.0)
        success_en = await self.speak_text(english_text, lang="en")
        return success_th and success_en

    async def announce_status(self, patient_id: str, status_th: str) -> bool:
        """
        Announce patient status change.

        Args:
            patient_id: Patient identifier
            status_th: Status in Thai

        Returns:
            True if successful
        """
        # Format patient ID for speech
        pid_th = self._format_patient_id_th(patient_id)
        pid_en = self._format_patient_id_en(patient_id)

        # Get status in English
        status_en = STATUS_EN.get(status_th, "updated")

        # Build messages
        thai_msg = f"สถานะของผู้ป่วยรหัส {pid_th} ขณะนี้อยู่ที่ {status_th}"
        english_msg = f"The status of patient ID {pid_en} is now {status_en}."

        logger.info(f"Announcing status: {patient_id} -> {status_th}")
        return await self.speak_bilingual(thai_msg, english_msg)

    async def announce_postponed(
        self, patient_id: str, repeat: int = 2, gap_sec: int = 8
    ) -> bool:
        """
        Announce surgery postponement (repeated).

        Args:
            patient_id: Patient identifier
            repeat: Number of times to repeat
            gap_sec: Gap between repeats (seconds)

        Returns:
            True if successful
        """
        pid_th = self._format_patient_id_th(patient_id)
        pid_en = self._format_patient_id_en(patient_id)

        thai_msg = (
            f"เรียนญาติผู้ป่วยรหัส {pid_th} "
            f"วันนี้มีความจำเป็นต้องปรับเวลาเข้าห้องผ่าตัด "
            f"กรุณามาพบเจ้าหน้าที่ที่หน้าห้องผ่าตัดเพื่อชี้แจงรายละเอียดและเวลานัดหมายใหม่ ขอบคุณค่ะ"
        )
        english_msg = (
            f"Attention, family of patient ID {pid_en}. "
            f"Please come to the operating room front desk to discuss a schedule change. Thank you."
        )

        logger.info(f"Announcing postponement: {patient_id} (repeat={repeat})")

        for i in range(repeat):
            success = await self.speak_bilingual(thai_msg, english_msg)
            if not success:
                return False
            if i + 1 < repeat:
                await asyncio.sleep(gap_sec)

        return True

    async def announce_public(self) -> bool:
        """
        Announce public service message about QR code tracking.

        Returns:
            True if successful
        """
        from ...config.constants import PUBLIC_ANNOUNCEMENT_TH, PUBLIC_ANNOUNCEMENT_EN

        logger.info("Announcing public message")
        return await self.speak_bilingual(
            PUBLIC_ANNOUNCEMENT_TH, PUBLIC_ANNOUNCEMENT_EN
        )

    def _format_patient_id_th(self, patient_id: str) -> str:
        """Format patient ID for Thai speech (remove dashes)."""
        # Simple version: just say the ID
        cleaned = "".join(ch for ch in patient_id if ch not in "-–—_ ")
        return cleaned

    def _format_patient_id_en(self, patient_id: str) -> str:
        """Format patient ID for English speech."""
        cleaned = "".join(ch for ch in patient_id if ch not in "-–—_ ")
        # Separate letters and numbers with spaces
        result = []
        for ch in cleaned:
            if ch.isalpha():
                result.append(ch.upper())
            elif ch.isdigit():
                result.append(ch)
            result.append(" ")
        return "".join(result).strip()


# Global TTS engine instance
_tts_engine: Optional[TTSEngine] = None


def get_tts_engine() -> TTSEngine:
    """Get or create global TTS engine instance."""
    global _tts_engine
    if _tts_engine is None:
        _tts_engine = TTSEngine()
    return _tts_engine
