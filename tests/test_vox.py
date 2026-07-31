"""VOX(OKI ADPCM) 인코더 검증 — 실제 운영 파일 규격(8kHz 모노 4bit)과 일치."""

import numpy as np
from pydub.generators import Sine

from ars_voice import vox


def test_encode_size_is_half_sample_count():
    # 4bit/샘플 → 바이트 수 = 샘플 수 / 2
    audio = Sine(440).to_audio_segment(duration=1000).set_frame_rate(8000).set_channels(1)
    data = vox.encode(audio.raw_data)
    assert len(data) == len(audio.raw_data) // 2 // 2  # 16bit(2바이트) → 4bit(0.5바이트)


def test_roundtrip_preserves_signal():
    """인코딩→디코딩 후 파형이 원본과 강하게 상관되어야 한다."""
    audio = (
        Sine(300).to_audio_segment(duration=500).apply_gain(-6)
        .set_frame_rate(8000).set_channels(1).set_sample_width(2)
    )
    decoded = vox.decode(vox.encode(audio.raw_data))

    orig = np.frombuffer(audio.raw_data, dtype=np.int16).astype(np.float64)
    rt = np.frombuffer(decoded, dtype=np.int16).astype(np.float64)[: len(orig)]
    orig = orig[: len(rt)]
    corr = np.corrcoef(orig, rt)[0, 1]
    assert corr > 0.95, f"round-trip 상관계수 {corr:.3f}"


def test_audio_to_vox_from_stereo_44k():
    """44.1kHz 스테레오 마스터 → 8kHz VOX 변환: 길이가 비율대로 나와야 한다."""
    audio = Sine(440).to_audio_segment(duration=2000).set_channels(2)  # 44.1kHz 스테레오
    data = vox.audio_to_vox(audio)
    expected_bytes = 8000 * 2 // 2  # 2초 × 8000샘플 ÷ 2샘플/바이트
    assert abs(len(data) - expected_bytes) < 200


def test_silence_encodes_quiet():
    silence = b"\x00\x00" * 8000
    decoded = vox.decode(vox.encode(silence))
    rt = np.frombuffer(decoded, dtype=np.int16)
    assert np.abs(rt).max() < 500  # 무음은 무음에 가깝게
