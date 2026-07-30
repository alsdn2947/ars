"""백그라운드 렌더링 큐.

합성은 네트워크 왕복이 있어 요청 스레드에서 처리하지 않고 워커 스레드
풀에 넘긴다. 진행 상태는 renders 테이블로 추적하고, 프런트엔드는
GET /api/renders/{id} 를 폴링한다.

ENGINE_FACTORY는 테스트에서 오프라인 가짜 엔진으로 교체할 수 있다.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ars_voice.pipeline import RenderOptions, render
from ars_voice.web import db

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ars-render")


def _default_engine_factory(voice: str):
    from ars_voice.tts import EdgeTTS

    return EdgeTTS(voice)


ENGINE_FACTORY = _default_engine_factory

ALLOWED_FORMATS = {"mp3", "wav", "ogg", "flac"}


def options_from_json(raw: str) -> tuple[RenderOptions, str]:
    """멘트에 저장된 옵션 JSON → (RenderOptions, 출력 포맷)."""
    data = json.loads(raw or "{}")
    fmt = str(data.get("format", "mp3")).lower()
    if fmt not in ALLOWED_FORMATS:
        fmt = "mp3"
    bgm = data.get("bgm", "calm")
    options = RenderOptions(
        voice=data.get("voice", "female_calm"),
        bgm=None if bgm in (None, "", "none") else bgm,
        bgm_gain_db=float(data.get("bgm_gain_db", -16.0)),
        telephone=bool(data.get("telephone", False)),
        auto_phrase=bool(data.get("auto_phrase", True)),
        normalize_text=bool(data.get("normalize_text", True)),
    )
    return options, fmt


def submit(db_path: str, renders_dir: str, render_id: int) -> None:
    _EXECUTOR.submit(_run, db_path, renders_dir, render_id)


def _run(db_path: str, renders_dir: str, render_id: int) -> None:
    row = db.get_render(db_path, render_id)
    if row is None:
        return
    db.update_render(db_path, render_id, status="running")
    try:
        ment = db.get_ment(db_path, row["ment_id"])
        if ment is None:
            raise ValueError("멘트가 삭제되었습니다.")
        options, fmt = options_from_json(ment["options"])
        # BGM 프리셋 외 값(파일 경로)은 웹에서는 허용하지 않는다 — 경로 주입 방지
        from ars_voice.bgm import BGM_PRESETS

        if options.bgm is not None and options.bgm not in BGM_PRESETS:
            raise ValueError(f"알 수 없는 BGM 프리셋: {options.bgm}")

        file_name = f"render_{render_id}.{fmt}"
        out_path = Path(renders_dir) / file_name
        out_path.parent.mkdir(parents=True, exist_ok=True)

        engine = ENGINE_FACTORY(options.voice)
        render(ment["body"], str(out_path), options, engine=engine)

        db.update_render(
            db_path, render_id,
            status="done", file_name=file_name, finished_at=db.now_iso(),
        )
    except Exception as e:  # noqa: BLE001 — 상태 테이블로 전달
        db.update_render(
            db_path, render_id,
            status="error", error=str(e)[:500], finished_at=db.now_iso(),
        )
