"""엔진 레지스트리 테스트 — 키 유무에 따른 활성화와 요청 구성."""

import json

import pytest

from ars_voice import engines
from ars_voice.tts import EdgeTTS


def test_edge_is_default_and_always_available(monkeypatch):
    monkeypatch.delenv("CLOVA_CLIENT_ID", raising=False)
    monkeypatch.delenv("CLOVA_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    engine = engines.create_engine("edge", "female_calm")
    assert isinstance(engine, EdgeTTS)
    # 알 수 없는 voice는 기본 프리셋으로 대체
    assert isinstance(engines.create_engine("", "잘못된값"), EdgeTTS)

    catalog = {e["id"]: e for e in engines.engine_catalog()}
    assert catalog["edge"]["available"] is True
    assert catalog["clova"]["available"] is False
    assert catalog["elevenlabs"]["available"] is False


def test_paid_engines_require_keys(monkeypatch):
    monkeypatch.delenv("CLOVA_CLIENT_ID", raising=False)
    monkeypatch.delenv("CLOVA_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    with pytest.raises(engines.MissingAPIKey):
        engines.create_engine("clova", "nara")
    with pytest.raises(engines.MissingAPIKey):
        engines.create_engine("elevenlabs", "voice123")


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
