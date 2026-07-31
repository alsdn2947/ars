"""TTS 엔진 레지스트리 — 무료 기본 엔진과 전문 성우급 유료 엔진.

무료 edge 엔진은 품질 상한이 있다. 전문 성우 녹음에 가까운 결과가
필요하면 유료 엔진의 API 키를 환경 변수로 설정한다:

  CLOVA Voice (Naver Cloud, 한국어 특화·국내 ARS에서 널리 쓰임)
    CLOVA_CLIENT_ID / CLOVA_CLIENT_SECRET
    (네이버 클라우드 플랫폼 → CLOVA Voice Premium 이용 신청 후 발급)

  ElevenLabs (다국어, 자연스러운 억양)
    ELEVENLABS_API_KEY
    음성은 voice_id를 직접 입력한다 (elevenlabs.io 보이스 라이브러리에서 복사)

  Google Cloud TTS (월 100만 자 무료 티어)
    GOOGLE_TTS_API_KEY
    (Google Cloud 콘솔 → Cloud Text-to-Speech API 활성화 → API 키 발급)

  OpenAI TTS (구독료 없는 종량제, 톤 지시 지원)
    OPENAI_API_KEY

키가 설정된 엔진만 웹 UI에 활성화되어 나타난다.
"""

from __future__ import annotations

import base64
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


GOOGLE_VOICES = {
    # Chirp3 HD: 최신 생성형 음성 — Neural2보다 훨씬 자연스럽다. 우선 추천.
    "ko-KR-Chirp3-HD-Aoede": "Chirp3 HD Aoede (여성, 최신·가장 자연스러움)",
    "ko-KR-Chirp3-HD-Kore": "Chirp3 HD Kore (여성, 최신)",
    "ko-KR-Chirp3-HD-Charon": "Chirp3 HD Charon (남성, 최신)",
    "ko-KR-Chirp3-HD-Orus": "Chirp3 HD Orus (남성, 최신)",
    "ko-KR-Neural2-A": "Neural2 A (여성)",
    "ko-KR-Neural2-B": "Neural2 B (여성)",
    "ko-KR-Neural2-C": "Neural2 C (남성)",
    "ko-KR-Wavenet-A": "WaveNet A (여성)",
    "ko-KR-Wavenet-D": "WaveNet D (남성)",
}


class GoogleTTS:
    """Google Cloud Text-to-Speech. WaveNet/Neural2는 월 100만 자까지 무료."""

    ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"

    def __init__(self, voice: str = "ko-KR-Chirp3-HD-Aoede"):
        self.api_key = os.environ.get("GOOGLE_TTS_API_KEY", "")
        if not self.api_key:
            raise MissingAPIKey("GOOGLE_TTS_API_KEY 환경 변수가 필요합니다.")
        self.voice = voice if voice in GOOGLE_VOICES else "ko-KR-Chirp3-HD-Aoede"

    def _payload(self, text: str) -> bytes:
        audio_config: dict = {"audioEncoding": "MP3"}
        # Chirp3 HD는 speakingRate 등 세부 파라미터를 지원하지 않는다
        if "Chirp3" not in self.voice:
            audio_config["speakingRate"] = 0.93  # 안내 방송 톤: 살짝 느리게
        return json.dumps(
            {
                "input": {"text": text},
                "voice": {"languageCode": "ko-KR", "name": self.voice},
                "audioConfig": audio_config,
            }
        ).encode()

    def synthesize(self, script: Script) -> list[AudioSegment]:
        out = []
        total = len(script.segments)
        for i, seg in enumerate(script.segments):
            req = urllib.request.Request(
                f"{self.ENDPOINT}?key={urllib.parse.quote(self.api_key)}",
                data=self._payload(_segment_synth_text(seg.text, is_final=(i == total - 1))),
                headers={"Content-Type": "application/json"},
            )
            body = _http_bytes(req, "Google Cloud TTS")
            audio = base64.b64decode(json.loads(body)["audioContent"])
            out.append(AudioSegment.from_file(io.BytesIO(audio), format="mp3"))
        return out


OPENAI_VOICES = {
    "nova": "Nova (밝은 여성)",
    "shimmer": "Shimmer (차분한 여성)",
    "coral": "Coral (또렷한 여성)",
    "sage": "Sage (부드러운 여성)",
    "onyx": "Onyx (저음 남성)",
    "echo": "Echo (안내 남성)",
}

# gpt-4o-mini-tts는 자연어 톤 지시를 지원한다 — ARS 성우 톤을 명시한다.
_OPENAI_STYLE = (
    "당신은 한국어 ARS 전화 안내 방송을 녹음하는 전문 성우입니다. "
    "밝지만 차분하고 신뢰감 있는 목소리로, 안내 방송 특유의 정중한 존댓말 억양을 쓰세요. "
    "속도는 약간 느리게, 발음은 또박또박, 문장 사이에는 여유 있는 호흡을 두고, "
    "쉼표에서는 짧게 끊어 읽으세요. 절대 로봇처럼 단조롭게 읽지 말고, "
    "실제 사람이 스튜디오 마이크 앞에서 녹음하듯 자연스러운 높낮이와 호흡으로 읽어 주세요."
)


class OpenAITTS:
    """OpenAI TTS (gpt-4o-mini-tts). 구독료 없는 종량제, 톤 지시 지원."""

    ENDPOINT = "https://api.openai.com/v1/audio/speech"

    def __init__(self, voice: str = "shimmer"):
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise MissingAPIKey("OPENAI_API_KEY 환경 변수가 필요합니다.")
        self.voice = voice if voice in OPENAI_VOICES else "shimmer"

    def _payload(self, text: str) -> bytes:
        return json.dumps(
            {
                "model": "gpt-4o-mini-tts",
                "voice": self.voice,
                "input": text,
                "instructions": _OPENAI_STYLE,
                "response_format": "mp3",
            }
        ).encode()

    def synthesize(self, script: Script) -> list[AudioSegment]:
        out = []
        total = len(script.segments)
        for i, seg in enumerate(script.segments):
            req = urllib.request.Request(
                self.ENDPOINT,
                data=self._payload(_segment_synth_text(seg.text, is_final=(i == total - 1))),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            audio = _http_bytes(req, "OpenAI TTS")
            out.append(AudioSegment.from_file(io.BytesIO(audio), format="mp3"))
        return out


# ── 레지스트리 ───────────────────────────────────────────────


def clova_available() -> bool:
    return bool(os.environ.get("CLOVA_CLIENT_ID") and os.environ.get("CLOVA_CLIENT_SECRET"))


def elevenlabs_available() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY"))


def google_available() -> bool:
    return bool(os.environ.get("GOOGLE_TTS_API_KEY"))


def openai_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


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
            "id": "google",
            "label": "Google Cloud TTS — 월 100만 자 무료 (API 키 필요)",
            "available": google_available(),
            "voices": list(GOOGLE_VOICES),
            "voice_labels": GOOGLE_VOICES,
            "default_voice": "ko-KR-Chirp3-HD-Aoede",
            "hint": "서버 환경 변수 GOOGLE_TTS_API_KEY 설정 시 활성화",
        },
        {
            "id": "openai",
            "label": "OpenAI TTS — 종량제·톤 지시 (API 키 필요)",
            "available": openai_available(),
            "voices": list(OPENAI_VOICES),
            "voice_labels": OPENAI_VOICES,
            "default_voice": "shimmer",
            "hint": "서버 환경 변수 OPENAI_API_KEY 설정 시 활성화",
        },
        {
            "id": "clova",
            "label": "CLOVA Voice — 전문 성우급 (월 기본료 있음, API 키 필요)",
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
    if engine_id == "google":
        return GoogleTTS(voice)
    if engine_id == "openai":
        return OpenAITTS(voice)
    if engine_id == "clova":
        return ClovaTTS(voice)
    if engine_id == "elevenlabs":
        return ElevenLabsTTS(voice)
    raise ValueError(f"알 수 없는 엔진: {engine_id}")
