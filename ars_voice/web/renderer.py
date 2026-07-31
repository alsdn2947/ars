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

from ars_voice.pipeline import RenderOptions
from ars_voice.web import db

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ars-render")


def _default_engine_factory(engine_id: str, voice: str, speed: float = 1.0):
    from ars_voice.engines import create_engine

    return create_engine(engine_id, voice, speed)


ENGINE_FACTORY = _default_engine_factory

ALLOWED_FORMATS = {"mp3", "wav", "ogg", "flac", "vox"}

# 납품 세트: 미리듣기용 MP3 + 원본 규격 WAV(44.1kHz/16bit) + 전화설비용 VOX(8kHz ADPCM)
OUTPUT_SET = ["mp3", "wav", "vox"]


def options_from_json(raw: str) -> RenderOptions:
    """멘트에 저장된 옵션 JSON → RenderOptions."""
    data = json.loads(raw or "{}")
    bgm = data.get("bgm", "calm")
    phrasing = data.get("phrasing", "flow")
    if phrasing not in ("flow", "natural", "precise"):
        phrasing = "flow"
    try:
        speed = float(data.get("speed", 1.0))
    except (TypeError, ValueError):
        speed = 1.0
    return RenderOptions(
        engine=data.get("engine", "edge"),
        voice=data.get("voice", "female_calm"),
        speed=min(1.3, max(0.7, speed)),
        bgm=None if bgm in (None, "", "none") else bgm,
        bgm_gain_db=float(data.get("bgm_gain_db", -16.0)),
        telephone=bool(data.get("telephone", False)),
        auto_phrase=bool(data.get("auto_phrase", True)),
        normalize_text=bool(data.get("normalize_text", True)),
        phrasing=phrasing,
    )


def resolve_bgm(bgm: str | None, bgm_dir: str) -> str | None:
    """옵션의 BGM 값을 검증한다. 'file:이름'은 업로드 보관함 경로로 변환.

    경로 주입을 막기 위해 프리셋 이름 또는 보관함 안의 파일명만 허용한다.
    """
    if bgm is None:
        return None
    from ars_voice.bgm import BGM_PRESETS

    if bgm in BGM_PRESETS:
        return bgm
    if bgm.startswith("file:"):
        name = Path(bgm[len("file:"):]).name  # 디렉터리 탈출 차단
        path = Path(bgm_dir) / name
        if not path.is_file():
            raise ValueError(f"업로드된 BGM을 찾을 수 없습니다: {name}")
        return str(path)
    raise ValueError(f"알 수 없는 BGM: {bgm}")


def submit(db_path: str, renders_dir: str, render_id: int, bgm_dir: str) -> None:
    _EXECUTOR.submit(_run, db_path, renders_dir, render_id, bgm_dir)


def _run(db_path: str, renders_dir: str, render_id: int, bgm_dir: str) -> None:
    row = db.get_render(db_path, render_id)
    if row is None:
        return
    db.update_render(db_path, render_id, status="running")
    try:
        ment = db.get_ment(db_path, row["ment_id"])
        if ment is None:
            raise ValueError("멘트가 삭제되었습니다.")
        options = options_from_json(ment["options"])
        options.bgm = resolve_bgm(options.bgm, bgm_dir)

        Path(renders_dir).mkdir(parents=True, exist_ok=True)
        from ars_voice.pipeline import render_set

        engine = ENGINE_FACTORY(options.engine, options.voice, options.speed)
        names = render_set(
            ment["body"], renders_dir, f"render_{render_id}",
            OUTPUT_SET, options, engine=engine,
        )

        db.update_render(
            db_path, render_id,
            status="done", file_name=json.dumps(names), finished_at=db.now_iso(),
        )
    except Exception as e:  # noqa: BLE001 — 상태 테이블로 전달
        db.update_render(
            db_path, render_id,
            status="error", error=str(e)[:500], finished_at=db.now_iso(),
        )
