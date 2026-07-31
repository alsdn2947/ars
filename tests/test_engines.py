"""엔진 레지스트리 테스트 — 키 유무에 따른 활성화와 요청 구성."""

import json

import pytest

from ars_voice import engines
from ars_voice.tts import EdgeTTS


_KEY_ENVS = [
    "CLOVA_CLIENT_ID", "CLOVA_CLIENT_SECRET", "ELEVENLABS_API_KEY",
    "GOOGLE_TTS_API_KEY", "OPENAI_API_KEY",
]


def _clear_keys(monkeypatch):
    for env in _KEY_ENVS:
        monkeypatch.delenv(env, raising=False)


def test_edge_is_default_and_always_available(monkeypatch):
    _clear_keys(monkeypatch)

    engine = engines.create_engine("edge", "female_calm")
    assert isinstance(engine, EdgeTTS)
    # 알 수 없는 voice는 기본 프리셋으로 대체
    assert isinstance(engines.create_engine("", "잘못된값"), EdgeTTS)

    catalog = {e["id"]: e for e in engines.engine_catalog()}
    assert catalog["edge"]["available"] is True
    for paid in ("clova", "elevenlabs", "google", "openai"):
        assert catalog[paid]["available"] is False


def test_paid_engines_require_keys(monkeypatch):
    _clear_keys(monkeypatch)

    for engine_id, voice in [
        ("clova", "nara"), ("elevenlabs", "voice123"),
        ("google", "ko-KR-Neural2-A"), ("openai", "shimmer"),
    ]:
        with pytest.raises(engines.MissingAPIKey):
            engines.create_engine(engine_id, voice)


def test_google_payload(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "gkey")
    engine = engines.create_engine("google", "ko-KR-Wavenet-D")
    data = json.loads(engine._payload("안내입니다."))
    assert data["voice"]["name"] == "ko-KR-Wavenet-D"
    assert data["voice"]["languageCode"] == "ko-KR"
    assert data["audioConfig"]["audioEncoding"] == "MP3"
    # 알 수 없는 화자는 기본 화자로 대체
    assert engines.create_engine("google", "이상한값").voice == "ko-KR-Neural2-A"
    assert {e["id"]: e for e in engines.engine_catalog()}["google"]["available"] is True


def test_openai_payload(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "okey")
    engine = engines.create_engine("openai", "onyx")
    data = json.loads(engine._payload("안내입니다."))
    assert data["model"] == "gpt-4o-mini-tts"
    assert data["voice"] == "onyx"
    assert "성우" in data["instructions"]
    assert engines.create_engine("openai", "이상한값").voice == "shimmer"
    assert {e["id"]: e for e in engines.engine_catalog()}["openai"]["available"] is True


def test_clova_payload(monkeypatch):
    monkeypatch.setenv("CLOVA_CLIENT_ID", "id")
    monkeypatch.setenv("CLOVA_CLIENT_SECRET", "secret")
    engine = engines.create_engine("clova", "nara")
    payload = engine._payload("안녕하세요.").decode()
    assert "speaker=nara" in payload
    assert "format=mp3" in payload

    catalog = {e["id"]: e for e in engines.engine_catalog()}
    assert catalog["clova"]["available"] is True

    # 알 수 없는 화자는 기본 화자로 대체
    assert engines.create_engine("clova", "unknown").voice == "nara"


def test_elevenlabs_payload(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "key")
    engine = engines.create_engine("elevenlabs", "voiceX")
    data = json.loads(engine._payload("안내입니다."))
    assert data["text"] == "안내입니다."
    assert data["model_id"] == "eleven_multilingual_v2"

    with pytest.raises(ValueError):
        engines.create_engine("elevenlabs", "")


def test_unknown_engine():
    with pytest.raises(ValueError):
        engines.create_engine("papago", "x")
