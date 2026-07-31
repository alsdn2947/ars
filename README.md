# ars-voice

자연어 텍스트를 입력하면 **ARS 전문 성우가 녹음한 느낌의 안내 음원**(배경음악 포함)을 만들어 주는 파이프라인입니다. CLI와 **팀 공유용 웹 스튜디오**(URL 초대 기반 권한 관리)를 제공합니다.

```bash
# CLI
ars-voice "안녕하십니까. 고객센터입니다. 상담원 연결을 원하시면 0번을 눌러 주세요." -o greeting.mp3

# 웹 스튜디오 (팀 공유)
ars-voice-web --port 8000
```

## 웹 스튜디오 — URL 공유 + 권한 허용자만 접속

프로젝트 단위로 팀원과 함께 ARS 멘트를 작성하고 음원을 추출하는 웹 서비스입니다.

**권한 모델 (링크가 곧 자격 증명)**

1. 서버 최초 기동 시 콘솔에 **관리자 접속 링크**가 한 번 출력됩니다.
2. 관리자는 프로젝트를 만들고, 프로젝트별 **초대 링크**(사용 횟수·유효기간 제한)를 발급해 팀원에게 공유합니다.
3. 초대 링크로 접속한 사람은 이름을 등록하면 해당 프로젝트의 편집자가 되고, **개인 접속 링크**를 받아 어느 기기에서든 재접속할 수 있습니다.
4. 링크가 없는 사람은 어떤 데이터에도 접근할 수 없습니다. 편집자는 초대받은 프로젝트만 볼 수 있습니다.

**기능**

- 멘트 작성/수정/삭제 (프로젝트별 목록 관리, 수정자 기록)
- 끊어읽기 대본 미리보기 (합성 전에 구절·쉼 확인, 네트워크 불필요)
- 성우·끊어읽기 방식·BGM·음량·전화망 음질 옵션 선택 후 **음원 생성**
- 생성 시 **3종 세트가 함께 추출**: MP3(미리듣기) + WAV(44.1kHz/16bit) + **VOX(Dialogic 8kHz ADPCM, 전화설비 납품용)**
- 생성 이력별 브라우저 재생 및 형식별 다운로드

**운영**

```bash
ars-voice-web --host 0.0.0.0 --port 8000 --data /srv/ars   # 데이터: DB + 생성 음원
ars-voice-web --reset-admin                                 # 관리자 링크 분실 시 재발급
```

토큰은 DB에 해시로만 저장됩니다. 외부 공개 시 HTTPS 리버스 프록시(nginx, Caddy 등) 뒤에 두는 것을 권장합니다 — 접속 링크가 자격 증명이므로 평문 HTTP로 노출하지 마세요.

## 특징

**1. 목소리 — 성우 톤 프리셋**

무료 Microsoft Edge 신경망 TTS(한국어 성우급 음성)를 기본 엔진으로 사용하며, 안내 방송에 맞게 속도를 약간 늦추고 피치를 낮춘 프리셋을 제공합니다.

| 프리셋 | 설명 |
|---|---|
| `female_calm` (기본) | 차분한 여성 안내 톤 — 국내 ARS 표준 느낌 |
| `female_bright` | 조금 밝고 경쾌한 여성 톤 |
| `male_calm` | 차분한 남성 안내 톤 |
| `male_deep` | 더 느리고 낮은 남성 톤 |

**2. 끊어읽기 — 두 가지 모드**

- `natural` (기본): 문장 단위로 합성해 문장 안 억양(쉼표 등)은 엔진이 자연스럽게 처리하고, 문장 사이 쉼과 수동 표기만 정밀 제어합니다. 구절별 합성에서 생기는 뚝뚝 끊기는 느낌이 없습니다.
- `precise`: 쉼표·구절 경계까지 모두 분할해 쉼 길이를 밀리초 단위로 제어합니다.
- 공통: 수동 표기 `/`(짧은 쉼), `//`(긴 쉼), 문장 끝 0.68초·문단 0.95초·여운 1.4초 (조절 가능)

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

**4. 배경음악 — 업로드 보관함 + 내장 프리셋**

- **BGM 업로드(권장)**: 저작권 무료 음원(mp3/wav/ogg/flac/m4a, 최대 30MB)을 웹에서 업로드하면 팀 전체가 배경음악 목록에서 선택해 쓸 수 있습니다. 자동 루프·페이드·음성 대비 레벨링이 적용됩니다.
  - 무료 음원 출처 예: [Pixabay Music](https://pixabay.com/music/)(저작권 표시 불필요), [FreePD](https://freepd.com)(퍼블릭 도메인), 공유마당(gongu.copyright.or.kr)
  - 상업적(영리) 이용 시 각 사이트의 라이선스 조건을 확인하세요.
- 내장 프리셋: `calm`, `bright`(절차 생성, 저작권 없음), `none`
- CLI에서는 파일 경로 지정: `--bgm my_bgm.mp3`

**5. 전문 성우급 유료 엔진 (선택)**

무료 기본 엔진의 품질이 부족하면 유료 엔진 API 키를 서버 환경 변수로 설정하세요. 설정된 엔진은 웹 UI의 엔진 목록에 자동 활성화됩니다.

| 엔진 | 환경 변수 | 비용 | 비고 |
|---|---|---|---|
| Google Cloud TTS | `GOOGLE_TTS_API_KEY` | 월 100만 자 무료 | Neural2/WaveNet 한국어 음성. Cloud 콘솔에서 Text-to-Speech API 활성화 후 API 키 발급 |
| OpenAI TTS | `OPENAI_API_KEY` | 구독료 없는 종량제 | gpt-4o-mini-tts, "ARS 성우 톤" 지시 내장 |
| ElevenLabs | `ELEVENLABS_API_KEY` | Starter 월 $5부터 상업 이용 | voice_id 직접 입력 |
| CLOVA Voice Premium | `CLOVA_CLIENT_ID`, `CLOVA_CLIENT_SECRET` | 월 기본료 90,000원 + 종량 | 한국어 특화, 국내 ARS 업계 표준급 |

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

웹 스튜디오 (ars_voice/web)
  FastAPI + SQLite(표준 라이브러리) + 바닐라 JS 단일 페이지
  초대/개인 링크 토큰은 SHA-256 해시로만 저장
  렌더링은 워커 스레드 큐로 처리, 프런트는 상태 폴링
```

다른 TTS 엔진(Naver CLOVA Voice, Google Cloud TTS 등)을 쓰려면 `synthesize(script) -> list[AudioSegment]` 메서드를 가진 클래스를 만들어 `render(..., engine=MyEngine())`으로 주입하면 됩니다.

## 테스트

```bash
pip install -e ".[dev]"
pytest
```

정규화·끊어읽기·BGM 생성·믹싱은 네트워크 없이 전부 테스트됩니다.
