"""Dialogic VOX (OKI ADPCM) 인코더/디코더.

국내 ARS/교환기 설비가 사용하는 .vox 포맷은 헤더 없는 raw OKI ADPCM
(8kHz, 모노, 4bit)이다. 표준 라이브러리 audioop의 ADPCM은 IMA 방식이라
호환되지 않으므로 OKI 방식을 직접 구현한다.

인코딩 파이프라인: 44.1kHz 스테레오 → 3.4kHz 로우패스(앨리어싱 방지)
→ 8kHz 모노 다운샘플 → 12bit OKI ADPCM 4bit 코드.
"""

from __future__ import annotations

from pydub import AudioSegment

VOX_SAMPLE_RATE = 8000

# OKI ADPCM 스텝 테이블 (49단계)과 인덱스 조정 테이블
_STEPS = [
    16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66,
    73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253,
    279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876,
    963, 1060, 1166, 1282, 1411, 1552,
]
_INDEX_ADJUST = [-1, -1, -1, -1, 2, 4, 6, 8]


def _clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


def encode(pcm16: bytes) -> bytes:
    """16bit little-endian mono PCM → OKI ADPCM 4bit 코드 (2샘플/바이트)."""
    predicted = 0  # 12bit 신호 기준
    index = 0
    out = bytearray()
    nibble_pending = None

    n_samples = len(pcm16) // 2
    for i in range(n_samples):
        sample = int.from_bytes(pcm16[2 * i : 2 * i + 2], "little", signed=True) >> 4
        step = _STEPS[index]
        diff = sample - predicted

        code = 0
        if diff < 0:
            code = 8
            diff = -diff
        if diff >= step:
            code |= 4
            diff -= step
        if diff >= step >> 1:
            code |= 2
            diff -= step >> 1
        if diff >= step >> 2:
            code |= 1

        # 디코더와 동일한 방식으로 예측값 갱신
        delta = (step >> 3) + ((code & 4) and step) + ((code & 2) and (step >> 1)) + ((code & 1) and (step >> 2))
        predicted += -delta if code & 8 else delta
        predicted = _clamp(predicted, -2048, 2047)
        index = _clamp(index + _INDEX_ADJUST[code & 7], 0, len(_STEPS) - 1)

        if nibble_pending is None:
            nibble_pending = code
        else:
            out.append((nibble_pending << 4) | code)
            nibble_pending = None

    if nibble_pending is not None:
        out.append(nibble_pending << 4)
    return bytes(out)


def decode(vox_data: bytes) -> bytes:
    """OKI ADPCM → 16bit little-endian mono PCM (검증/미리듣기용)."""
    predicted = 0
    index = 0
    out = bytearray()

    def one(code: int) -> None:
        nonlocal predicted, index
        step = _STEPS[index]
        delta = (step >> 3) + ((code & 4) and step) + ((code & 2) and (step >> 1)) + ((code & 1) and (step >> 2))
        predicted += -delta if code & 8 else delta
        predicted = _clamp(predicted, -2048, 2047)
        index = _clamp(index + _INDEX_ADJUST[code & 7], 0, len(_STEPS) - 1)
        out.extend(int(predicted << 4).to_bytes(2, "little", signed=True))

    for byte in vox_data:
        one(byte >> 4)
        one(byte & 0x0F)
    return bytes(out)


def audio_to_vox(audio: AudioSegment) -> bytes:
    """임의 규격의 AudioSegment를 VOX 규격(8kHz 모노 OKI ADPCM)으로 변환."""
    prepared = (
        audio.low_pass_filter(3400)
        .set_channels(1)
        .set_frame_rate(VOX_SAMPLE_RATE)
        .set_sample_width(2)
    )
    return encode(prepared.raw_data)


def vox_to_audio(vox_data: bytes) -> AudioSegment:
    return AudioSegment(
        decode(vox_data), frame_rate=VOX_SAMPLE_RATE, sample_width=2, channels=1
    )
