"""믹싱 — 음성 트랙 조립, BGM 레벨링, 최종 출력.

- 세그먼트 오디오를 스크립트의 쉼 길이대로 무음과 함께 이어 붙인다.
- 음성은 일정 RMS 레벨로 정규화하고, BGM은 음성 대비 지정 dB만큼
  낮춰 깔아준다 (기본 -16dB: 멘트가 또렷하게 들리는 통상 ARS 밸런스).
- BGM에는 페이드인/아웃을 넣고, 멘트가 끝난 뒤 여운 구간을 남긴다.
- 전화망 품질(--telephone) 옵션은 300~3400Hz 대역통과로 실제 수화기
  음질을 시뮬레이션한다.
"""

from __future__ import annotations

import io
import subprocess

from pydub import AudioSegment

from ars_voice.script import Script

# 음성 RMS 목표 레벨. 실제 ARS 성우 녹음(평균 -14.5dB) 실측에 맞춘 값.
VOICE_TARGET_DBFS = -14.0


def build_voice_track(script: Script, segment_audio: list[AudioSegment]) -> AudioSegment:
    """세그먼트 오디오 + 쉼 무음으로 음성 트랙을 조립한다."""
    if len(script.segments) != len(segment_audio):
        raise ValueError("스크립트 세그먼트 수와 오디오 수가 다릅니다.")

    frame_rate = segment_audio[0].frame_rate if segment_audio else 44100
    track = AudioSegment.silent(duration=script.profile.lead_in_ms, frame_rate=frame_rate)
    for seg, audio in zip(script.segments, segment_audio):
        # 세그먼트 경계의 미세한 클릭(파형 불연속) 제거
        audio = audio.fade_in(10).fade_out(15)
        track += audio + AudioSegment.silent(duration=seg.pause_ms, frame_rate=frame_rate)
    return track


def normalize_rms(audio: AudioSegment, target_dbfs: float = VOICE_TARGET_DBFS) -> AudioSegment:
    if audio.dBFS == float("-inf"):
        return audio
    return audio.apply_gain(target_dbfs - audio.dBFS)


def mix(
    voice: AudioSegment,
    bgm: AudioSegment | None,
    bgm_gain_db: float = -16.0,
    fade_in_ms: int = 1200,
    fade_out_ms: int = 2500,
) -> AudioSegment:
    """음성 트랙과 BGM을 합쳐 최종 음원을 만든다."""
    voice = normalize_rms(voice)

    if bgm is None:
        return voice

    total_ms = len(voice)
    bed = bgm[:total_ms]
    # BGM 레벨을 '음성 대비' bgm_gain_db 로 맞춘다
    if bed.dBFS != float("-inf"):
        bed = bed.apply_gain((VOICE_TARGET_DBFS + bgm_gain_db) - bed.dBFS)
    bed = bed.fade_in(fade_in_ms).fade_out(fade_out_ms)

    mixed = bed.overlay(voice)
    # 클리핑 여유 확보
    if mixed.max_dBFS > -1.0:
        mixed = mixed.apply_gain(-1.0 - mixed.max_dBFS)
    return mixed


def time_stretch(audio: AudioSegment, speed: float) -> AudioSegment:
    """음정을 유지한 채 재생 속도를 바꾼다 (ffmpeg atempo).

    속도 파라미터를 지원하지 않는 TTS 엔진의 속도 조절 폴백으로 쓴다.
    """
    if abs(speed - 1.0) < 0.01:
        return audio
    if not 0.5 <= speed <= 2.0:
        raise ValueError("속도는 0.5~2.0 배 범위만 지원합니다.")
    src = io.BytesIO()
    audio.export(src, format="wav")
    proc = subprocess.run(
        [AudioSegment.converter, "-v", "error", "-i", "pipe:0",
         "-filter:a", f"atempo={speed}", "-f", "wav", "pipe:1"],
        input=src.getvalue(), capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"속도 변환 실패: {proc.stderr[:200].decode('utf-8', 'replace')}")
    return AudioSegment.from_file(io.BytesIO(proc.stdout), format="wav")


def telephone_filter(audio: AudioSegment) -> AudioSegment:
    """전화망(300~3400Hz) 음질 시뮬레이션."""
    return audio.high_pass_filter(300).low_pass_filter(3400).set_frame_rate(8000).set_frame_rate(audio.frame_rate)


def export(audio: AudioSegment, path: str, bitrate: str = "192k") -> str:
    """확장자에 맞는 포맷으로 저장한다 (mp3/wav/ogg/flac/vox).

    .vox는 전화설비용 Dialogic OKI ADPCM(8kHz 모노) raw 포맷으로 저장된다.
    """
    fmt = path.rsplit(".", 1)[-1].lower() if "." in path else "mp3"
    if fmt == "vox":
        from ars_voice.vox import audio_to_vox

        with open(path, "wb") as fp:
            fp.write(audio_to_vox(audio))
        return path
    kwargs = {"bitrate": bitrate} if fmt == "mp3" else {}
    audio.export(path, format=fmt, **kwargs)
    return path
