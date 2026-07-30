"""FastAPI 앱 — 초대 링크 기반 ARS 멘트 작성/추출 서비스."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from ars_voice.bgm import BGM_PRESETS
from ars_voice.pipeline import RenderOptions, make_script
from ars_voice.tts import VOICE_PRESETS
from ars_voice.web import db, renderer

_STATIC = Path(__file__).parent / "static"
COOKIE_NAME = "ars_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30일


# ── 요청 본문 모델 ───────────────────────────────────────────


class JoinBody(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class ProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class InviteBody(BaseModel):
    max_uses: int = Field(default=10, ge=1, le=100)
    expires_days: int = Field(default=14, ge=1, le=365)


class MentBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(default="", max_length=20000)
    options: dict = Field(default_factory=dict)


class PreviewBody(BaseModel):
    body: str = Field(max_length=20000)
    auto_phrase: bool = True
    normalize_text: bool = True


def create_app(data_dir: str | Path = "data") -> FastAPI:
    data_dir = Path(data_dir)
    db_path = str(data_dir / "ars.db")
    renders_dir = str(data_dir / "renders")
    db.init_db(db_path)

    app = FastAPI(title="ars-voice web", docs_url=None, redoc_url=None)
    app.state.db_path = db_path
    app.state.renders_dir = renders_dir

    # ── 인증 ────────────────────────────────────────────────

    def current_user(ars_session: str | None = Cookie(default=None, alias=COOKIE_NAME)):
        if not ars_session:
            raise HTTPException(401, "접속 권한이 없습니다. 초대 링크로 접속해 주세요.")
        user = db.get_user_by_token(db_path, ars_session)
        if user is None:
            raise HTTPException(401, "세션이 만료되었거나 잘못된 접근입니다.")
        return user

    def require_admin(user=Depends(current_user)):
        if user["role"] != "admin":
            raise HTTPException(403, "관리자 권한이 필요합니다.")
        return user

    def require_project(project_id: int, user=Depends(current_user)):
        if not db.user_can_access(db_path, user, project_id):
            raise HTTPException(403, "이 프로젝트에 접근할 수 없습니다.")
        return user

    def require_ment(ment_id: int, user=Depends(current_user)):
        ment = db.get_ment(db_path, ment_id)
        if ment is None:
            raise HTTPException(404, "멘트를 찾을 수 없습니다.")
        if not db.user_can_access(db_path, user, ment["project_id"]):
            raise HTTPException(403, "이 프로젝트에 접근할 수 없습니다.")
        return ment, user

    def set_session(response: Response, token: str) -> None:
        response.set_cookie(
            COOKIE_NAME, token,
            max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax",
        )

    # ── 페이지 ──────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (_STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/join/{token}", response_class=HTMLResponse)
    def join_page(token: str):
        # 1) 개인 접속 링크: 바로 로그인
        user = db.get_user_by_token(db_path, token)
        if user is not None:
            response = RedirectResponse("/", status_code=303)
            set_session(response, token)
            return response
        # 2) 초대 링크: 이름 등록 페이지
        invite = db.get_valid_invite(db_path, token)
        if invite is None:
            return HTMLResponse((_STATIC / "join_invalid.html").read_text(encoding="utf-8"), status_code=410)
        return HTMLResponse((_STATIC / "join.html").read_text(encoding="utf-8"))

    @app.post("/join/{token}")
    def join_submit(token: str, body: JoinBody):
        invite = db.get_valid_invite(db_path, token)
        if invite is None:
            raise HTTPException(410, "초대 링크가 만료되었거나 사용 한도를 초과했습니다.")
        _, personal_token = db.redeem_invite(db_path, invite["id"], body.name.strip())
        response = JSONResponse({"ok": True, "personal_link": f"/join/{personal_token}"})
        set_session(response, personal_token)
        return response

    @app.post("/api/logout")
    def logout():
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE_NAME)
        return response

    # ── 메타/세션 ───────────────────────────────────────────

    @app.get("/api/me")
    def me(request: Request, user=Depends(current_user)):
        token = request.cookies.get(COOKIE_NAME, "")
        return {
            "id": user["id"], "name": user["name"], "role": user["role"],
            "personal_link": f"/join/{token}",
        }

    @app.get("/api/meta")
    def meta(user=Depends(current_user)):
        return {
            "voices": sorted(VOICE_PRESETS),
            "bgms": sorted(BGM_PRESETS) + ["none"],
            "formats": sorted(renderer.ALLOWED_FORMATS),
        }

    # ── 프로젝트 ────────────────────────────────────────────

    @app.get("/api/projects")
    def projects(user=Depends(current_user)):
        return [dict(p) for p in db.list_projects_for(db_path, user)]

    @app.post("/api/projects")
    def create_project(body: ProjectBody, user=Depends(require_admin)):
        pid = db.create_project(db_path, body.name.strip())
        return {"id": pid, "name": body.name.strip()}

    @app.post("/api/projects/{project_id}/invites")
    def create_invite(project_id: int, body: InviteBody, user=Depends(require_admin)):
        if not db.user_can_access(db_path, user, project_id):
            raise HTTPException(404, "프로젝트가 없습니다.")
        token = db.create_invite(db_path, project_id, body.max_uses, body.expires_days)
        return {"invite_link": f"/join/{token}", "max_uses": body.max_uses, "expires_days": body.expires_days}

    @app.get("/api/projects/{project_id}/members")
    def members(project_id: int, user=Depends(require_project)):
        return [dict(m) for m in db.list_members(db_path, project_id)]

    # ── 멘트 ────────────────────────────────────────────────

    @app.get("/api/projects/{project_id}/ments")
    def ments(project_id: int, user=Depends(require_project)):
        return [dict(m) for m in db.list_ments(db_path, project_id)]

    @app.post("/api/projects/{project_id}/ments")
    def create_ment(project_id: int, body: MentBody, user=Depends(require_project)):
        mid = db.create_ment(
            db_path, project_id, body.title.strip(), body.body,
            json.dumps(body.options, ensure_ascii=False), user["name"],
        )
        return {"id": mid}

    @app.get("/api/ments/{ment_id}")
    def get_ment(ctx=Depends(require_ment)):
        ment, _ = ctx
        out = dict(ment)
        out["options"] = json.loads(out["options"] or "{}")
        return out

    @app.put("/api/ments/{ment_id}")
    def put_ment(body: MentBody, ctx=Depends(require_ment)):
        ment, user = ctx
        db.update_ment(
            db_path, ment["id"], body.title.strip(), body.body,
            json.dumps(body.options, ensure_ascii=False), user["name"],
        )
        return {"ok": True}

    @app.delete("/api/ments/{ment_id}")
    def remove_ment(ctx=Depends(require_ment)):
        ment, _ = ctx
        db.delete_ment(db_path, ment["id"])
        return {"ok": True}

    # ── 대본 미리보기 (합성 없음, 네트워크 불필요) ──────────

    @app.post("/api/preview")
    def preview(body: PreviewBody, user=Depends(current_user)):
        script = make_script(
            body.body,
            RenderOptions(auto_phrase=body.auto_phrase, normalize_text=body.normalize_text),
        )
        return {
            "segments": [{"text": s.text, "pause_ms": s.pause_ms} for s in script.segments]
        }

    # ── 렌더링 ──────────────────────────────────────────────

    @app.post("/api/ments/{ment_id}/render")
    def start_render(ctx=Depends(require_ment)):
        ment, user = ctx
        if not ment["body"].strip():
            raise HTTPException(400, "멘트 내용이 비어 있습니다.")
        render_id = db.create_render(db_path, ment["id"], user["name"])
        renderer.submit(db_path, renders_dir, render_id)
        return {"render_id": render_id}

    @app.get("/api/ments/{ment_id}/renders")
    def ment_renders(ctx=Depends(require_ment)):
        ment, _ = ctx
        return [dict(r) for r in db.list_renders(db_path, ment["id"])]

    def _authorized_render(render_id: int, user):
        row = db.get_render(db_path, render_id)
        if row is None:
            raise HTTPException(404, "렌더링 기록이 없습니다.")
        ment = db.get_ment(db_path, row["ment_id"])
        if ment is None or not db.user_can_access(db_path, user, ment["project_id"]):
            raise HTTPException(403, "접근할 수 없습니다.")
        return row

    @app.get("/api/renders/{render_id}")
    def render_status(render_id: int, user=Depends(current_user)):
        return dict(_authorized_render(render_id, user))

    @app.get("/api/renders/{render_id}/download")
    def render_download(render_id: int, user=Depends(current_user)):
        row = _authorized_render(render_id, user)
        if row["status"] != "done" or not row["file_name"]:
            raise HTTPException(409, "아직 완료되지 않은 렌더링입니다.")
        path = Path(renders_dir) / row["file_name"]
        if not path.exists():
            raise HTTPException(410, "음원 파일이 삭제되었습니다.")
        return FileResponse(path, filename=row["file_name"])

    return app
