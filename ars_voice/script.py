"""끊어읽기(구절 분할) — 텍스트를 낭독 세그먼트로 변환.

전문 성우의 ARS 낭독은 문장 부호와 의미 단위에서 일정한 길이로 쉬는 것이
특징이다. TTS 엔진의 내장 휴지에 맡기지 않고, 텍스트를 세그먼트로 나눠
각각 합성한 뒤 믹싱 단계에서 정확한 길이의 무음을 삽입한다. 이렇게 하면
엔진이 바뀌어도 끊어읽기 리듬이 동일하게 유지된다.

수동 표기:
    /   짧은 쉼 (약 0.3초)
    //  긴 쉼 (약 0.9초)

자동 구절 분할(auto_phrase)은 ARS 안내문에 자주 나오는 연결 어미·표현
("~하시면", "~의 경우" 등) 뒤에 짧은 쉼을 넣는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ars_voice.normalizer import normalize


@dataclass(frozen=True)
class PauseProfile:
    """쉼 길이 프로파일 (밀리초). ARS 표준 낭독 속도 기준."""

    sentence_ms: int = 680      # 문장 끝 (마침표, 물음표, 느낌표)
    comma_ms: int = 340         # 쉼표, 수동 표기 '/'
    long_ms: int = 950          # 수동 표기 '//', 문단 바꿈
    lead_in_ms: int = 450       # 음원 시작 무음 (BGM만 먼저 들리는 구간)
    tail_ms: int = 1400         # 마지막 문장 후 여운


@dataclass
class Segment:
    """합성 단위 구절과 그 뒤에 올 쉼 길이."""

    text: str
    pause_ms: int


@dataclass
class Script:
    segments: list[Segment] = field(default_factory=list)
    profile: PauseProfile = field(default_factory=PauseProfile)

    def pretty(self) -> str:
        """낭독 대본 미리보기 (dry-run 출력용)."""
        lines = []
        for seg in self.segments:
            lines.append(f"{seg.text}  ⏸ {seg.pause_ms / 1000:.2f}s")
        return "\n".join(lines)


# ARS 안내문에서 구절 경계가 되는 연결 표현. 해당 단어 뒤 공백 위치에
# 짧은 쉼을 넣는다. (문장 중간에서만 적용)
_PHRASE_BOUNDARIES = [
    "하시면", "시면", "누르시면", "원하시면", "위해", "위하여",
    "경우", "후에", "이후", "먼저", "또는", "및", "함께", "따라",
]

_SENTENCE_END = re.compile(r"([.!?。])")
_LONG_MARK = ""
_SHORT_MARK = ""


def _apply_auto_phrase(sentence: str) -> str:
    for word in _PHRASE_BOUNDARIES:
        sentence = re.sub(
            rf"(?<![가-힣])({re.escape(word)})\s+",
            rf"\1{_SHORT_MARK}",
            sentence,
        )
    return sentence


def build_script(
    text: str,
    profile: PauseProfile | None = None,
    auto_phrase: bool = True,
    apply_normalize: bool = True,
    phrasing: str = "natural",
) -> Script:
    """자연어 텍스트를 낭독 세그먼트 목록으로 변환한다.

    phrasing:
    - "flow": 멘트 전체를 한 번에 합성한다. 문장 사이 호흡과 흐름까지
      엔진이 처리해 가장 자연스럽다. 수동 표기는 문장 부호로 변환된다
      (`/` → 쉼표, `//` → 마침표). 쉼 길이의 개별 제어는 포기한다.
    - "natural": 문장 단위로 나눠 합성한다. 문장 안 억양은 엔진이
      처리하고, 문장 사이 쉼과 수동 표기(`/`, `//`)를 우리가 제어한다.
    - "precise": 쉼표·구절 경계까지 모두 분할해 쉼 길이를 정밀 제어한다.
      (엔진 억양은 다소 딱딱해질 수 있다)
    """
    profile = profile or PauseProfile()
    if phrasing not in ("flow", "natural", "precise"):
        raise ValueError(f"알 수 없는 phrasing 모드: {phrasing}")

    if phrasing == "flow":
        flow = text.replace("//", ". ").replace("/", ", ")
        flow = re.sub(r"\n\s*\n", ". ", flow).replace("\n", " ")
        if apply_normalize:
            flow = normalize(flow)
        # 마커 변환으로 생긴 중복 문장 부호 정리
        flow = re.sub(r"([.!?。])\s*[.]", r"\1", flow)
        flow = re.sub(r",\s*,", ",", flow)
        flow = re.sub(r"\s+([.,!?])", r"\1", flow)
        flow = re.sub(r"\s{2,}", " ", flow).strip()
        segments = [Segment(flow, profile.tail_ms)] if flow.strip(".,!?。 ") else []
        return Script(segments=segments, profile=profile)

    # 수동 쉼 표기를 마커로 치환 (긴 것 먼저)
    text = text.replace("//", _LONG_MARK).replace("/", _SHORT_MARK)
    # 빈 줄(문단 구분)은 긴 쉼으로
    text = re.sub(r"\n\s*\n", _LONG_MARK, text)
    text = text.replace("\n", " ")

    if apply_normalize:
        text = normalize(text)

    segments: list[Segment] = []

    # 문장 단위로 나누되 종결 부호를 유지
    parts = _SENTENCE_END.split(text)
    sentences: list[str] = []
    for i in range(0, len(parts), 2):
        body = parts[i].strip()
        punct = parts[i + 1] if i + 1 < len(parts) else ""
        if body or punct:
            sentences.append((body + punct).strip())

    for sentence in sentences:
        if phrasing == "precise" and auto_phrase:
            sentence = _apply_auto_phrase(sentence)

        # natural: 수동 마커에서만 분할 (쉼표는 엔진이 처리)
        # precise: 쉼표·마커 모두에서 분할
        if phrasing == "natural":
            tokens = re.split(rf"({_LONG_MARK}|{_SHORT_MARK})", sentence)
        else:
            tokens = re.split(rf"(,|{_LONG_MARK}|{_SHORT_MARK})", sentence)
        pending = ""
        for token in tokens:
            if token in (",", _SHORT_MARK):
                if pending.strip():
                    segments.append(Segment(pending.strip(), profile.comma_ms))
                pending = ""
            elif token == _LONG_MARK:
                if pending.strip():
                    segments.append(Segment(pending.strip(), profile.long_ms))
                elif segments:
                    # 문장 경계에 놓인 '//' — 앞 세그먼트의 쉼을 긴 쉼으로 승격
                    segments[-1].pause_ms = max(segments[-1].pause_ms, profile.long_ms)
                pending = ""
            else:
                pending += token
        last = pending.strip()
        if last.rstrip(".!?。"):
            # 종결 부호는 유지한다 — TTS가 문말 억양(내림조)을 살리는 근거가 된다.
            segments.append(Segment(last, profile.sentence_ms))
        elif segments:
            # 문장이 쉼표로 끝났으면 마지막 세그먼트 쉼을 문장 쉼으로 승격
            segments[-1].pause_ms = max(segments[-1].pause_ms, profile.sentence_ms)

    if segments:
        segments[-1].pause_ms = profile.tail_ms

    return Script(segments=segments, profile=profile)
