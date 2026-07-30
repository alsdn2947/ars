"""ars_voice — 자연어 텍스트를 ARS 전문 성우 스타일 음원으로 변환하는 파이프라인.

구성 요소
- normalizer: 숫자·전화번호·시각·금액·영문 약어를 한국어 발음으로 정규화
- script:     끊어읽기 규칙에 따라 텍스트를 세그먼트(구절 + 쉼 길이)로 분할
- tts:        세그먼트별 음성 합성 (기본: Microsoft Edge 신경망 TTS, 무료)
- bgm:        배경음악 절차 생성 또는 외부 파일 로드
- mixer:      음성 트랙 조립, BGM 레벨링/페이드, 최종 믹스다운
"""

from ars_voice.pipeline import RenderOptions, render

__version__ = "0.1.0"

__all__ = ["render", "RenderOptions", "__version__"]
