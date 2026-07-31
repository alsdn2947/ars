"""BGM 생성·믹싱 테스트. TTS 네트워크 없이 합성음(사인파)을 음성으로 대용한다."""

import math

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from ars_voice import mixer
from ars_voice.bgm import BGM_PRESETS, generate_bgm
from ars_voice.pipeline import RenderOptions, render
from ars_voice.script import PauseProfile, Script, Segment


class FakeEngine:
    """세그먼트당 0.8초 사인파를 돌려주는 오프라인 대체 엔진."""

    def synthesize(self, script: Script):
        return [
            Sine(440).to_audio_segment(duration=800).apply_gain(-6)
            for _ in script.segments
        ]


def test_generate_bgm_length_and_presets():
    for name in BGM_PRESETS:
        audio = generate_bgm(name, duration_ms=5000, seed=42)
        assert len(audio) == 5000
        assert audio.channels == 2
        assert audio.dBFS > -60  # 무음이 아니다


def test_generate_bgm_deterministic():
    a = generate_bgm("calm", duration_ms=3000, seed=7)
    b = generate_bgm("calm", duration_ms=3000, seed=7)
    assert a.raw_data == b.raw_data


def test_build_voice_track_duration():
    profile = PauseProfile(sentence_ms=500, comma_ms=200, lead_in_ms=300, tail_ms=1000)
    script = Script(
        segments=[Segment("가", 200), Segment("나", 1000)],
        profile=profile,
    )
    audio = [Sine(440).to_audio_segment(duration=800) for _ in range(2)]
    track = mixer.build_voice_track(script, audio)
    expected = 300 + 800 + 200 + 800 + 1000
    assert math.isclose(len(track), expected, abs_tol=10)


def test_mix_bgm_is_quieter_than_voice():
    voice = Sine(440).to_audio_segment(duration=3000).apply_gain(-6)
    bgm = generate_bgm("calm", duration_ms=3000)
    mixed = mixer.mix(voice, bgm, bgm_gain_db=-16.0)
    assert len(mixed) == 3000
    # 믹스 결과는 클리핑하지 않는다
    assert mixed.max_dBFS <= -0.9


def test_mix_without_bgm():
    voice = Sine(440).to_audio_segment(duration=1000).apply_gain(-6)
    mixed = mixer.mix(voice, None)
    assert abs(mixed.dBFS - mixer.VOICE_TARGET_DBFS) < 1.0


def test_render_end_to_end_with_fake_engine(tmp_path):
    out = tmp_path / "out.mp3"
    result = render(
        "안녕하십니까. 고객센터입니다.",
        str(out),
        RenderOptions(bgm="calm"),
        engine=FakeEngine(),
    )
    assert out.exists()
    assert result == str(out)
    audio = AudioSegment.from_file(out)
    assert len(audio) > 2000


def test_render_wav_and_telephone(tmp_path):
    out = tmp_path / "out.wav"
    render(
        "감사합니다.",
        str(out),
        RenderOptions(bgm=None, telephone=True),
        engine=FakeEngine(),
    )
    assert out.exists()


def test_time_stretch_changes_duration():
    tone = Sine(440).to_audio_segment(duration=2000).apply_gain(-6)
    slow = mixer.time_stretch(tone, 0.8)
    fast = mixer.time_stretch(tone, 1.25)
    assert abs(len(slow) - 2500) < 100  # 0.8배속 → 25% 길어짐
    assert abs(len(fast) - 1600) < 100  # 1.25배속 → 20% 짧아짐
    # 1.0배는 원본 그대로
    assert mixer.time_stretch(tone, 1.0) is tone


def test_render_applies_speed_fallback(tmp_path):
    """native_speed 없는 엔진은 타임스트레치로 속도가 보정된다."""
    out_slow = tmp_path / "slow.wav"
    out_norm = tmp_path / "norm.wav"
    text = "안녕하십니까. 고객센터입니다."
    render(text, str(out_norm), RenderOptions(bgm=None, speed=1.0), engine=FakeEngine())
    render(text, str(out_slow), RenderOptions(bgm=None, speed=0.8), engine=FakeEngine())
    norm = AudioSegment.from_file(out_norm)
    slow = AudioSegment.from_file(out_slow)
    # flow 모드 1세그먼트(0.8초) 기준: 0.8배속이면 음성 구간이 약 200ms 늘어난다
    assert len(slow) > len(norm) + 150  # 쉼 길이는 그대로, 음성만 늘어남


def test_render_empty_text_raises(tmp_path):
    with pytest.raises(ValueError):
        render("   ", str(tmp_path / "x.mp3"), engine=FakeEngine())
