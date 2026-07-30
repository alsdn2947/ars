# ars-voice

자연어 텍스트를 입력하면 **ARS 전문 성우가 녹음한 느낌의 안내 음원**(배경음악 포함)을 만들어 주는 파이프라인입니다.

```bash
ars-voice "안녕하십니까. 고객센터입니다. 상담원 연결을 원하시면 0번을 눌러 주세요." -o greeting.mp3
```

## 특징

**1. 목소리 — 성우 톤 프리셋**

무료 Microsoft Edge 신경망 TTS(한국어 성우급 음성)를 기본 엔진으로 사용하며, 안내 방송에 맞게 속도를 약간 늦추고 피치를 낮춘 프리셋을 제공합니다.

| 프리셋 | 설명 |
|---|---|
| `female_calm` (기본) | 차분한 여성 안내 톤 — 국내 ARS 표준 느낌 |
| `female_bright` | 조금 밝고 경쾌한 여성 톤 |
| `male_calm` | 차분한 남성 안내 톤 |
| `male_deep` | 더 느리고 낮은 남성 톤 |

**2. 끊어읽기 — 세그먼트 단위 합성 + 정밀 무음 삽입**

TTS 엔진의 내장 휴지에 맡기지 않고, 문장·쉼표·구절 단위로 나눠 각각 합성한 뒤 믹싱 단계에서 정확한 길이의 무음을 넣습니다. 엔진이 바뀌어도 낭독 리듬이 동일하게 유지됩니다.

- 문장 끝 0.68초, 쉼표 0.34초, 문단/`//` 0.95초, 마지막 여운 1.4초 (모두 조절 가능)
- 수동 표기 지원: `/` 짧은 쉼, `//` 긴 쉼
- 자동 구절 분할: "~하시면", "~의 경우" 등 ARS 상용 표현 뒤에 자동으로 쉼 삽입

**3. 발음 — 한국어 낭독 정규화**

숫자·기호를 성우가 실제 읽는 발음 그대로 한글로 변환한 뒤 합성합니다.

| 입력 | 읽기 |
|---|---|
| `1588-1234` | 일오팔팔, 일이삼사 (전화번호 자릿수 읽기) |
| `15,000원` | 만 오천원 |
| `09:00` / `18시` | 아홉 시 / 오후 여섯 시 (고유어 시각) |
| `6월 10일` | 유월 십 일 (불규칙 월 이름) |
| `50%` / `3.5` | 오십 퍼센트 / 삼 점 오 |
| `ARS`, `VIP` | 에이알에스, 브이아이피 (철자 읽기) |

**4. 배경음악 — 저작권 걱정 없는 절차 생성 BGM**

외부 음원 없이 잔잔한 BGM(펜타토닉 아르페지오 + 패드)을 직접 합성합니다. 페이드인/아웃과 음성 대비 자동 레벨링(-16dB)이 적용됩니다.

- 프리셋: `calm`(기본, 통화 대기음 스타일), `bright`(밝은 분위기), `none`(BGM 없음)
- 갖고 있는 음원을 쓰려면 파일 경로를 지정: `--bgm my_bgm.mp3` (자동 루프)

## 설치

```bash
# ffmpeg 필요 (오디오 인코딩/믹싱)
sudo apt install ffmpeg        # macOS: brew install ffmpeg

pip install -e .
```

기본 TTS 엔진(edge-tts)은 **인터넷 연결이 필요**합니다. API 키는 필요 없습니다.

## 사용법

```bash
# 기본: 차분한 여성 성우 + calm BGM → mp3
ars-voice "안내 문구" -o out.mp3

# 파일 입력, 남성 성우, 밝은 BGM, WAV 출력
ars-voice -f ment.txt -o out.wav --voice male_calm --bgm bright

# BGM 없이, 전화망(300~3400Hz) 음질 시뮬레이션
ars-voice "안내 문구" -o out.mp3 --bgm none --telephone

# 합성 전에 끊어읽기 대본 미리 확인 (네트워크 불필요)
ars-voice "안내 문구" --dry-run
```

파이썬 API:

```python
from ars_voice import render, RenderOptions

render(
    "안녕하십니까. 고객센터입니다. 상담원 연결은 0번을 눌러 주세요.",
    "greeting.mp3",
    RenderOptions(voice="female_calm", bgm="calm", bgm_gain_db=-16),
)
```

## 아키텍처

```
텍스트
  → normalizer  발음 정규화 (숫자/시각/전화번호/영문 → 한글)
  → script      끊어읽기: 세그먼트(구절 + 쉼 길이) 분할
  → tts         세그먼트별 신경망 합성 (기본 edge-tts, 교체 가능)
  → mixer       무음 삽입 조립 → RMS 정규화 → BGM 레벨링/페이드 → 믹스다운
  → mp3 / wav / ogg / flac
```

다른 TTS 엔진(Naver CLOVA Voice, Google Cloud TTS 등)을 쓰려면 `synthesize(script) -> list[AudioSegment]` 메서드를 가진 클래스를 만들어 `render(..., engine=MyEngine())`으로 주입하면 됩니다.

## 테스트

```bash
pip install -e ".[dev]"
pytest
```

정규화·끊어읽기·BGM 생성·믹싱은 네트워크 없이 전부 테스트됩니다.
