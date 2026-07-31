"""엔드투엔드 파이프라인: 자연어 텍스트 → ARS 음원 파일."""

from __future__ import annotations

from dataclasses import dataclass, field

from ars_voice import bgm as bgm_mod
from ars_voice import mixer
from ars_voice.script import PauseProfile, Script, build_script


@dataclass
class RenderOptions:
    engine: str = "edge"                # "edge" | "clova" | "elevenlabs"
    voice: str = "female_calm"          # 엔진별 음성 식별자
    bgm: str | None = "calm"            # bgm.BGM_PRESETS 키, 파일 경로, 또는 None
    bgm_gain_db: float = -16.0          # 음성 대비 BGM 레벨
    bgm_seed: int = 20260730
    telephone: bool = False             # 전화망 음질 시뮬레이션
    auto_phrase: bool = True            # 자동 구절 분할 (precise 모드에서만)
    normalize_text: bool = True         # 발음 정규화 (숫자/영문 → 한글)
    phrasing: str = "natural"           # "natural"(문장 단위) | "precise"(구절 단위)
    pause_profile: PauseProfile = field(default_factory=PauseProfile)


def make_script(text: str, options: RenderOptions | None = None) -> Script:
    options = options or RenderOptions()
    return build_script(
        text,
        profile=options.pause_profile,
        auto_phrase=options.auto_phrase,
        apply_normalize=options.normalize_text,
        phrasing=options.phrasing,
    )


def render_master(text: str, options: RenderOptions | None = None, engine=None):
    """텍스트를 합성해 마스터 오디오(AudioSegment)를 만든다.

    engine을 넘기지 않으면 edge-tts 기본 엔진을 사용한다(네트워크 필요).
    """
    options = options or RenderOptions()
    script = make_script(text, options)
    if not script.segments:
        raise ValueError("합성할 문장이 없습니다.")

    if engine is None:
        from ars_voice.engines import create_engine

        engine = create_engine(options.engine, options.voice)

    segment_audio = engine.synthesize(script)
    voice_track = mixer.build_voice_track(script, segment_audio)

    bgm_audio = None
    if options.bgm:
        if options.bgm in bgm_mod.BGM_PRESETS:
            bgm_audio = bgm_mod.generate_bgm(options.bgm, len(voice_track), seed=options.bgm_seed)
        else:
            bgm_audio = bgm_mod.load_bgm(options.bgm, len(voice_track))

    mixed = mixer.mix(voice_track, bgm_audio, bgm_gain_db=options.bgm_gain_db)
    if options.telephone:
        mixed = mixer.telephone_filter(mixed)
    return mixed


def render(
    text: str,
    output_path: str,
    options: RenderOptions | None = None,
    engine=None,
) -> str:
    """텍스트를 합성해 output_path에 음원 파일 하나를 만든다."""
    mixed = render_master(text, options, engine)
    return mixer.export(mixed, output_path)


def render_set(
    text: str,
    out_dir: str,
    base_name: str,
    formats: list[str],
    options: RenderOptions | None = None,
    engine=None,
) -> list[str]:
    """한 번의 합성으로 여러 포맷(mp3/wav/vox 등)을 함께 만든다.

    반환값은 생성된 파일 이름 목록 (out_dir 기준 상대 이름).
    """
    from pathlib import Path

    mixed = render_master(text, options, engine)
    names = []
    for fmt in formats:
        name = f"{base_name}.{fmt}"
        mixer.export(mixed, str(Path(out_dir) / name))
        names.append(name)
    return names
