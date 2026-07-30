"""음성 합성 엔진.

기본 엔진은 Microsoft Edge 신경망 TTS(edge-tts)다. API 키 없이 무료로
한국어 성우급 음성을 제공하며, 안내 방송 톤에 맞도록 속도·피치를 살짝
낮춘 프리셋을 둔다. 다른 엔진(Google Cloud TTS, Naver CLOVA Voice 등)을
쓰려면 TTSEngine 프로토콜에 맞는 클래스를 구현해 파이프라인에 주입하면
된다.

세그먼트는 개별 합성된다. 문장 중간 구절은 쉼표를 붙여 비종결(이어지는)
억양을, 문장 끝 구절은 마침표로 종결(내림) 억양을 유도한다.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from typing import Protocol

from pydub import AudioSegment

from ars_voice.script import Script


class TTSEngine(Protocol):
    def synthesize(self, script: Script) -> list[AudioSegment]:
        """스크립트의 각 세그먼트를 합성해 같은 순서의 오디오 목록을 돌려준다."""
        ...


@dataclass(frozen=True)
class VoicePreset:
    """ARS 성우 톤 프리셋."""

    voice: str
    rate: str = "-8%"    # 안내 방송은 대화체보다 약간 느리게
    pitch: str = "-2Hz"  # 살짝 낮춰 차분한 톤
    volume: str = "+0%"


# 한국어 신경망 음성 프리셋. 기본값은 국내 ARS에서 가장 익숙한
# 차분한 여성 안내 톤이다.
VOICE_PRESETS: dict[str, VoicePreset] = {
    "female_calm": VoicePreset("ko-KR-SunHiNeural"),
    "female_bright": VoicePreset("ko-KR-SunHiNeural", rate="-4%", pitch="+2Hz"),
    "male_calm": VoicePreset("ko-KR-InJoonNeural"),
    "male_deep": VoicePreset("ko-KR-InJoonNeural", rate="-10%", pitch="-4Hz"),
    "multilingual": VoicePreset("ko-KR-HyunsuMultilingualNeural"),
}

DEFAULT_PRESET = "female_calm"

_CONCURRENCY = 4


def _segment_synth_text(text: str, is_final: bool) -> str:
    """억양 유도를 위해 합성용 텍스트에 문장 부호를 보정한다."""
    if text[-1] in ".!?。,":
        return text
    return text + ("." if is_final else ",")


class EdgeTTS:
    """edge-tts 기반 합성기. 네트워크 연결이 필요하다."""

    def __init__(self, preset: VoicePreset | str = DEFAULT_PRESET):
        if isinstance(preset, str):
            preset = VOICE_PRESETS[preset]
        self.preset = preset

    def synthesize(self, script: Script) -> list[AudioSegment]:
        return asyncio.run(self._synthesize_async(script))

    async def _synthesize_async(self, script: Script) -> list[AudioSegment]:
        import edge_tts

        sem = asyncio.Semaphore(_CONCURRENCY)
        total = len(script.segments)

        async def synth_one(index: int, text: str) -> AudioSegment:
            async with sem:
                communicate = edge_tts.Communicate(
                    text,
                    voice=self.preset.voice,
                    rate=self.preset.rate,
                    pitch=self.preset.pitch,
                    volume=self.preset.volume,
                )
                buf = io.BytesIO()
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        buf.write(chunk["data"])
                buf.seek(0)
                return AudioSegment.from_file(buf, format="mp3")

        tasks = [
            synth_one(i, _segment_synth_text(seg.text, is_final=(i == total - 1)))
            for i, seg in enumerate(script.segments)
        ]
        return list(await asyncio.gather(*tasks))
