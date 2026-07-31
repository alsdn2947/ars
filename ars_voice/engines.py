"""TTS 엔진 레지스트리 — 무료 기본 엔진과 전문 성우급 유료 엔진.

무료 edge 엔진은 품질 상한이 있다. 전문 성우 녹음에 가까운 결과가
필요하면 유료 엔진의 API 키를 환경 변수로 설정한다:

  CLOVA Voice (Naver Cloud, 한국어 특화·국내 ARS에서 널리 쓰임)
    CLOVA_CLIENT_ID / CLOVA_CLIENT_SECRET
    (네이버 클라우드 플랫폼 → CLOVA Voice Premium 이용 신청 후 발급)

  ElevenLabs (다국어, 자연스러운 억양)
    ELEVENLABS_API_KEY
    음성은 voice_id를 직접 입력한다 (elevenlabs.io 보이스 라이브러리에서 복사)

키가 설정된 엔진만 웹 UI에 활성화되어 나타난다.
"""

from __future__ import annotations

import io
import json
import os
import urllib.parse
import urllib.request

from pydub import AudioSegment

from ars_voice.script import Script
from ars_voice.tts import DEFAULT_PRESET, VOICE_PRESETS, EdgeTTS, _segment_synth_text

# CLOVA Premium 성우. 국내 안내 방송 톤에 맞는 대표 화자만 추린 목록.
CLOVA_SPEAKERS = {
    "nara": "나라 (차분한 여성)",
    "njiyun": "지윤 (안내 여성)",
    "nsujin": "수진 (밝은 여성)",
    "nsinu": "신우 (차분한 남성)",
    "jinho": "진호 (안내 남성)",
}

EDGE_VOICE_LABELS = {
    "female_calm": "차분한 여성 (기본)",
    "female_bright": "밝은 여성",
    "male_calm": "차분한 남성",
    "male_deep": "저음 남성",
    "multilingual": "다국어",
}


class MissingAPIKey(RuntimeError):
    pass


def _http_bytes(req: urllib.request.Request, engine_name: str) -> bytes:
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return res.read()
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        raise RuntimeError(f"{engine_name} 합성 실패 (HTTP {e.code}): {detail}") from e


class ClovaTTS:
    """Naver Cloud CLOVA Voice Premium. 한국어 전문 성우급 화자."""

    ENDPOINT = "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts"

    def __init__(self, voice: str = "nara", speed: int = 1):
        self.client_id = os.environ.get("CLOVA_CLIENT_ID", "")
        self.client_secret = os.environ.get("CLOVA_CLIENT_SECRET", "")
        if not self.client_id or not self.client_secret:
            raise MissingAPIKey(
                "CLOVA_CLIENT_ID / CLOVA_CLIENT_SECRET 환경 변수가 필요합니다."
            )
        self.voice = voice if voice in CLOVA_SPEAKERS else "nara"
        self.speed = speed  # -5(빠름) ~ 5(느림), 안내 방송은 1 권장

    def _payload(self, text: str) -> bytes:
        return urllib.parse.urlencode(
            {"speaker": self.voice, "text": text, "format": "mp3", "speed": str(self.speed)}
        ).encode()

    def synthesize(self, script: Script) -> list[AudioSegment]:
        out = []
        total = len(script.segments)
        for i, seg in enumerate(script.segments):
            req = urllib.request.Request(
                self.ENDPOINT,
                data=self._payload(_segment_synth_text(seg.text, is_final=(i == total - 1))),
                headers={
                    "X-NCP-APIGW-API-KEY-ID": self.client_id,
                    "X-NCP-APIGW-API-KEY": self.client_secret,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            audio = _http_bytes(req, "CLOVA Voice")
            out.append(AudioSegment.from_file(io.BytesIO(audio), format="mp3"))
        return out


class ElevenLabsTTS:
    """ElevenLabs 다국어 신경망 음성. voice_id는 계정의 보이스 라이브러리에서 선택."""

    ENDPOINT = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"

    def __init__(self, voice: str):
        self.api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        if not self.api_key:
            raise MissingAPIKey("ELEVENLABS_API_KEY 환경 변수가 필요합니다.")
        if not voice:
            raise ValueError("ElevenLabs voice_id를 입력해 주세요.")
        self.voice = voice

    def _payload(self, text: str) -> bytes:
        return json.dumps(
            {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                # 안내 방송: 안정적이고 일관된 톤
                "voice_settings": {"stability": 0.6, "similarity_boost": 0.8, "style": 0.2},
            }
        ).encode()

    def synthesize(self, script: Script) -> list[AudioSegment]:
        out = []
        total = len(script.segments)
        for i, seg in enumerate(script.segments):
            req = urllib.request.Request(
                self.ENDPOINT.format(voice_id=urllib.parse.quote(self.voice)),
                data=self._payload(_segment_synth_text(seg.text, is_final=(i == total - 1))),
                headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
            )
            audio = _http_bytes(req, "ElevenLabs")
            out.append(AudioSegment.from_file(io.BytesIO(audio), format="mp3"))
        return out


# ── 레지스트리 ───────────────────────────────────────────────


def clova_available() -> bool:
    return bool(os.environ.get("CLOVA_CLIENT_ID") and os.environ.get("CLOVA_CLIENT_SECRET"))


def elevenlabs_available() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY"))


def engine_catalog() -> list[dict]:
    """웹 UI에 보여줄 엔진 목록. 키가 없는 유료 엔진은 비활성으로 표시."""
    return [
        {
            "id": "edge",
            "label": "기본 엔진 (무료)",
            "available": True,
            "voices": sorted(VOICE_PRESETS),
            "voice_labels": EDGE_VOICE_LABELS,
            "default_voice": DEFAULT_PRESET,
        },
        {
            "id": "clova",
            "label": "CLOVA Voice — 전문 성우급 (API 키 필요)",
            "available": clova_available(),
            "voices": list(CLOVA_SPEAKERS),
            "voice_labels": CLOVA_SPEAKERS,
            "default_voice": "nara",
            "hint": "서버 환경 변수 CLOVA_CLIENT_ID / CLOVA_CLIENT_SECRET 설정 시 활성화",
        },
        {
            "id": "elevenlabs",
            "label": "ElevenLabs (API 키 필요)",
            "available": elevenlabs_available(),
            "voices": None,  # voice_id 직접 입력
            "default_voice": "",
            "hint": "서버 환경 변수 ELEVENLABS_API_KEY 설정 시 활성화, voice_id 직접 입력",
        },
    ]


def create_engine(engine_id: str, voice: str):
    if engine_id == "edge" or not engine_id:
        return EdgeTTS(voice if voice in VOICE_PRESETS else DEFAULT_PRESET)
    if engine_id == "clova":
        return ClovaTTS(voice)
    if engine_id == "elevenlabs":
        return ElevenLabsTTS(voice)
    raise ValueError(f"알 수 없는 엔진: {engine_id}")
