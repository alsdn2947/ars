"""배경음악 — 절차 생성 또는 외부 파일 로드.

외부 음원 없이도 저작권 걱정 없는 잔잔한 BGM을 numpy로 직접 합성한다.
펜타토닉 아르페지오(감쇠하는 배음 합성 톤) 위에 부드러운 패드 코드를
깔아 통화 대기음에서 익숙한 차분한 질감을 만든다. 시드가 같으면 항상
같은 음원이 나온다(재현 가능).

프리셋
- calm:   60 BPM, 낮은 음역, 통화 연결음 스타일 (기본값)
- bright: 84 BPM, 한 옥타브 위, 조금 밝은 분위기
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from pydub import AudioSegment

SAMPLE_RATE = 44100


@dataclass(frozen=True)
class BGMPreset:
    bpm: int
    base_midi: int          # 아르페지오 기준음 (MIDI 노트 번호)
    lowpass_hz: int
    arp_gain: float
    pad_gain: float


BGM_PRESETS: dict[str, BGMPreset] = {
    "calm": BGMPreset(bpm=60, base_midi=60, lowpass_hz=3200, arp_gain=0.55, pad_gain=0.30),
    "bright": BGMPreset(bpm=84, base_midi=72, lowpass_hz=5200, arp_gain=0.50, pad_gain=0.25),
}

DEFAULT_BGM = "calm"

# C 메이저 펜타토닉 오프셋과 4코드 진행 (C - Am - F - G)
_PENTATONIC = [0, 2, 4, 7, 9]
_PROGRESSION = [(0, 4, 7), (-3, 0, 4), (-7, -3, 0), (-5, -1, 2)]


def _midi_to_hz(note: float) -> float:
    return 440.0 * 2.0 ** ((note - 69) / 12.0)


def _pluck(freq: float, dur_s: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    """감쇠 배음 톤 — 부드러운 전자피아노 느낌."""
    t = np.linspace(0.0, dur_s, int(sr * dur_s), endpoint=False)
    env = np.exp(-2.6 * t) * np.minimum(1.0, t / 0.01)
    wave = (
        1.00 * np.sin(2 * np.pi * freq * t)
        + 0.35 * np.sin(2 * np.pi * freq * 2 * t)
        + 0.12 * np.sin(2 * np.pi * freq * 3 * t)
    )
    return wave * env


def _pad(freqs: list[float], dur_s: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    """느린 어택의 지속 코드 패드."""
    t = np.linspace(0.0, dur_s, int(sr * dur_s), endpoint=False)
    attack = np.minimum(1.0, t / 0.8)
    release = np.minimum(1.0, (dur_s - t) / 0.8)
    env = attack * release
    wave = np.zeros_like(t)
    for f in freqs:
        wave += np.sin(2 * np.pi * f * t) + 0.2 * np.sin(2 * np.pi * f * 2 * t)
    return wave * env / max(len(freqs), 1)


def _one_pole_lowpass(x: np.ndarray, cutoff_hz: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    dt = 1.0 / sr
    rc = 1.0 / (2 * np.pi * cutoff_hz)
    alpha = dt / (rc + dt)
    acc = 0.0
    # scipy 없이도 빠르도록 IIR 점화식을 청크 단위 컨볼루션으로 계산
    b = 1.0 - alpha
    powers = b ** np.arange(4096)
    y = np.copy(x)
    for chunk_start in range(0, len(x), 4096):
        chunk = x[chunk_start : chunk_start + 4096]
        n = len(chunk)
        conv = alpha * np.convolve(chunk, powers[:n])[:n]
        conv += acc * powers[:n] * b
        acc = conv[-1] if n else acc
        y[chunk_start : chunk_start + n] = conv
    return y


def _loop_body(preset: BGMPreset, seed: int) -> np.ndarray:
    """4마디(코드 진행 1회) 분량의 루프 본체를 만든다."""
    rng = np.random.default_rng(seed)
    sr = SAMPLE_RATE
    beat_s = 60.0 / preset.bpm
    bar_s = beat_s * 4
    total_s = bar_s * len(_PROGRESSION)
    total_n = int(sr * total_s)
    left = np.zeros(total_n)
    right = np.zeros(total_n)

    for bar_idx, chord in enumerate(_PROGRESSION):
        bar_start = int(bar_idx * bar_s * sr)

        # 패드: 마디 전체를 지속하는 코드
        pad_freqs = [_midi_to_hz(preset.base_midi - 12 + o) for o in chord]
        pad_wave = _pad(pad_freqs, bar_s) * preset.pad_gain
        end = min(bar_start + len(pad_wave), total_n)
        left[bar_start:end] += pad_wave[: end - bar_start]
        right[bar_start:end] += pad_wave[: end - bar_start]

        # 아르페지오: 8분음표 그리드에 펜타토닉 음을 드문드문 배치
        for eighth in range(8):
            if rng.random() < 0.35:  # 여백을 남겨 잔잔하게
                continue
            offset = _PENTATONIC[int(rng.integers(len(_PENTATONIC)))]
            octave = 12 * int(rng.integers(0, 2))
            freq = _midi_to_hz(preset.base_midi + offset + octave)
            note = _pluck(freq, beat_s * 1.6) * preset.arp_gain
            start = bar_start + int(eighth * beat_s / 2 * sr)
            end = min(start + len(note), total_n)
            if end <= start:
                continue
            pan = float(rng.uniform(-0.4, 0.4))
            left[start:end] += note[: end - start] * (1.0 - max(pan, 0.0))
            right[start:end] += note[: end - start] * (1.0 + min(pan, 0.0))

    # 루프 이음새 크로스페이드: 끝 0.5초를 시작에 겹친다
    xfade = int(0.5 * sr)
    ramp = np.linspace(0.0, 1.0, xfade)
    for ch in (left, right):
        ch[:xfade] = ch[:xfade] * ramp + ch[-xfade:] * (1.0 - ramp)
    left, right = left[: total_n - xfade], right[: total_n - xfade]

    left = _one_pole_lowpass(left, preset.lowpass_hz)
    right = _one_pole_lowpass(right, preset.lowpass_hz)

    stereo = np.stack([left, right], axis=1)
    peak = np.max(np.abs(stereo))
    if peak > 0:
        stereo = stereo / peak * 0.7
    return stereo


def _to_audio_segment(stereo: np.ndarray) -> AudioSegment:
    pcm = (np.clip(stereo, -1.0, 1.0) * 32767).astype(np.int16)
    return AudioSegment(
        pcm.tobytes(),
        frame_rate=SAMPLE_RATE,
        sample_width=2,
        channels=2,
    )


def generate_bgm(preset_name: str = DEFAULT_BGM, duration_ms: int = 30000, seed: int = 20260730) -> AudioSegment:
    """프리셋 BGM을 duration_ms 이상 길이로 생성한다."""
    preset = BGM_PRESETS[preset_name]
    body = _to_audio_segment(_loop_body(preset, seed))
    out = body
    while len(out) < duration_ms:
        out += body
    return out[:duration_ms]


def load_bgm(path: str, duration_ms: int) -> AudioSegment:
    """외부 BGM 파일을 로드해 필요한 길이만큼 루프한다."""
    audio = AudioSegment.from_file(path)
    out = audio
    while len(out) < duration_ms:
        out += audio
    return out[:duration_ms]
