"""ars-voice 명령행 인터페이스.

사용 예:
    ars-voice "안녕하십니까. 고객센터입니다. 상담원 연결은 0번을 눌러 주세요." -o greeting.mp3
    ars-voice -f ment.txt -o greeting.wav --voice male_calm --bgm bright
    ars-voice "..." --dry-run          # 합성 없이 낭독 대본(끊어읽기)만 확인
"""

from __future__ import annotations

import argparse
import sys

from ars_voice.bgm import BGM_PRESETS
from ars_voice.pipeline import RenderOptions, make_script, render
from ars_voice.tts import VOICE_PRESETS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ars-voice",
        description="자연어 텍스트를 ARS 전문 성우 스타일 음원(BGM 포함)으로 변환합니다.",
    )
    p.add_argument("text", nargs="?", help="변환할 안내 문구. 생략 시 -f 또는 표준입력 사용")
    p.add_argument("-f", "--file", help="안내 문구가 담긴 텍스트 파일")
    p.add_argument("-o", "--output", default="ars_output.mp3", help="출력 파일 (기본: ars_output.mp3)")
    p.add_argument(
        "--voice",
        default="female_calm",
        choices=sorted(VOICE_PRESETS),
        help="성우 프리셋 (기본: female_calm)",
    )
    p.add_argument(
        "--bgm",
        default="calm",
        help=f"BGM 프리셋({', '.join(sorted(BGM_PRESETS))}), 오디오 파일 경로, 또는 'none' (기본: calm)",
    )
    p.add_argument("--bgm-gain", type=float, default=-16.0, help="음성 대비 BGM 레벨 dB (기본: -16)")
    p.add_argument("--bgm-seed", type=int, default=20260730, help="절차 생성 BGM 시드")
    p.add_argument("--telephone", action="store_true", help="전화망(300~3400Hz) 음질 시뮬레이션")
    p.add_argument(
        "--phrasing", choices=["natural", "precise"], default="natural",
        help="끊어읽기 방식: natural=문장 단위(자연스러움, 기본), precise=구절 단위 정밀 제어",
    )
    p.add_argument("--no-auto-phrase", action="store_true", help="자동 구절 분할 끄기")
    p.add_argument("--no-normalize", action="store_true", help="발음 정규화(숫자/영문→한글) 끄기")
    p.add_argument("--dry-run", action="store_true", help="합성하지 않고 낭독 대본만 출력")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.file:
        with open(args.file, encoding="utf-8") as fp:
            text = fp.read()
    elif args.text:
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        print("오류: 변환할 텍스트를 인자, -f 파일, 또는 표준입력으로 주세요.", file=sys.stderr)
        return 2

    options = RenderOptions(
        voice=args.voice,
        bgm=None if args.bgm == "none" else args.bgm,
        bgm_gain_db=args.bgm_gain,
        bgm_seed=args.bgm_seed,
        telephone=args.telephone,
        auto_phrase=not args.no_auto_phrase,
        normalize_text=not args.no_normalize,
        phrasing=args.phrasing,
    )

    if args.dry_run:
        script = make_script(text, options)
        print("── 낭독 대본 (구절 ⏸ 뒤따르는 쉼) ──")
        print(script.pretty())
        return 0

    try:
        out = render(text, args.output, options)
    except Exception as e:  # noqa: BLE001 — CLI 최상위에서 사용자 메시지로 변환
        print(f"오류: 합성에 실패했습니다 — {e}", file=sys.stderr)
        print("TTS 엔진(edge-tts)은 인터넷 연결이 필요합니다. 네트워크를 확인해 주세요.", file=sys.stderr)
        return 1

    print(f"완료: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
