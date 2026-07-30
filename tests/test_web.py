"""웹 앱 통합 테스트 — 권한 흐름과 멘트 작성/렌더링 전체 시나리오.

TTS는 네트워크가 필요하므로 렌더러의 엔진 팩토리를 오프라인 가짜
엔진으로 바꿔 전체 경로(작성 → 미리보기 → 렌더 → 다운로드)를 검증한다.
"""

import time

import pytest
from fastapi.testclient import TestClient
from pydub.generators import Sine

from ars_voice.web import db, renderer
from ars_voice.web.app import create_app


class FakeEngine:
    def synthesize(self, script):
        return [Sine(440).to_audio_segment(duration=300).apply_gain(-6) for _ in script.segments]


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(renderer, "ENGINE_FACTORY", lambda voice: FakeEngine())
    app = create_app(tmp_path)
    db_path = str(tmp_path / "ars.db")
    admin_token = db.ensure_admin(db_path)
    return app, db_path, admin_token


def login(app, token) -> TestClient:
    client = TestClient(app)
    res = client.get(f"/join/{token}", follow_redirects=False)
    assert res.status_code == 303
    return client


def test_anonymous_is_locked_out(env):
    app, _, _ = env
    client = TestClient(app)
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/me").status_code == 401
    # 메인 페이지 자체는 열리지만(로그인 안내) 데이터는 없다
    assert client.get("/").status_code == 200


def test_invalid_join_token(env):
    app, _, _ = env
    client = TestClient(app)
    res = client.get("/join/nonexistent-token")
    assert res.status_code == 410


def test_admin_project_and_invite_flow(env):
    app, _, admin_token = env
    admin = login(app, admin_token)

    me = admin.get("/api/me").json()
    assert me["role"] == "admin"

    # 프로젝트 생성
    p = admin.post("/api/projects", json={"name": "콜센터 리뉴얼"}).json()
    invite = admin.post(f"/api/projects/{p['id']}/invites", json={"max_uses": 2, "expires_days": 7}).json()
    invite_token = invite["invite_link"].split("/join/")[1]

    # 편집자: 초대 링크로 참여
    editor = TestClient(app)
    assert editor.get(f"/join/{invite_token}").status_code == 200  # 이름 등록 페이지
    res = editor.post(f"/join/{invite_token}", json={"name": "김성우"})
    assert res.status_code == 200
    assert editor.get("/api/me").json()["name"] == "김성우"

    # 편집자는 초대받은 프로젝트만 보인다
    projects = editor.get("/api/projects").json()
    assert [pr["name"] for pr in projects] == ["콜센터 리뉴얼"]

    # 편집자는 관리자 기능 불가
    assert editor.post("/api/projects", json={"name": "x"}).status_code == 403
    assert editor.post(f"/api/projects/{p['id']}/invites", json={}).status_code == 403


def test_invite_use_limit(env):
    app, _, admin_token = env
    admin = login(app, admin_token)
    p = admin.post("/api/projects", json={"name": "P"}).json()
    invite = admin.post(f"/api/projects/{p['id']}/invites", json={"max_uses": 1}).json()
    token = invite["invite_link"].split("/join/")[1]

    c1 = TestClient(app)
    assert c1.post(f"/join/{token}", json={"name": "A"}).status_code == 200
    c2 = TestClient(app)
    assert c2.post(f"/join/{token}", json={"name": "B"}).status_code == 410


def test_project_isolation(env):
    """다른 프로젝트 멤버는 멘트에 접근할 수 없다."""
    app, _, admin_token = env
    admin = login(app, admin_token)
    p1 = admin.post("/api/projects", json={"name": "P1"}).json()
    p2 = admin.post("/api/projects", json={"name": "P2"}).json()

    inv2 = admin.post(f"/api/projects/{p2['id']}/invites", json={}).json()
    outsider = TestClient(app)
    outsider.post("/join/" + inv2["invite_link"].split("/join/")[1], json={"name": "외부인"})

    ment = admin.post(f"/api/projects/{p1['id']}/ments",
                      json={"title": "비밀 멘트", "body": "안녕하세요.", "options": {}}).json()

    assert outsider.get(f"/api/projects/{p1['id']}/ments").status_code == 403
    assert outsider.get(f"/api/ments/{ment['id']}").status_code == 403
    assert outsider.post(f"/api/ments/{ment['id']}/render").status_code == 403


def test_ment_crud_preview_render_download(env):
    app, _, admin_token = env
    client = login(app, admin_token)
    p = client.post("/api/projects", json={"name": "은행"}).json()

    # 작성
    ment = client.post(
        f"/api/projects/{p['id']}/ments",
        json={"title": "인사말", "body": "안녕하십니까. 고객센터입니다.",
              "options": {"voice": "female_calm", "bgm": "calm", "format": "mp3"}},
    ).json()

    # 수정
    res = client.put(f"/api/ments/{ment['id']}", json={
        "title": "인사말(수정)", "body": "안녕하십니까. 1588-1234입니다.",
        "options": {"voice": "female_calm", "bgm": "calm", "format": "mp3"}})
    assert res.status_code == 200

    # 대본 미리보기 (발음 정규화 확인)
    prev = client.post("/api/preview", json={"body": "안녕하십니까. 1588-1234입니다."}).json()
    joined = " ".join(s["text"] for s in prev["segments"])
    assert "일오팔팔" in joined

    # 렌더링
    r = client.post(f"/api/ments/{ment['id']}/render").json()
    render_id = r["render_id"]
    for _ in range(100):
        status = client.get(f"/api/renders/{render_id}").json()
        if status["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert status["status"] == "done", status.get("error")

    # 다운로드
    audio = client.get(f"/api/renders/{render_id}/download")
    assert audio.status_code == 200
    assert len(audio.content) > 1000

    # 이력
    renders = client.get(f"/api/ments/{ment['id']}/renders").json()
    assert renders[0]["status"] == "done"

    # 삭제
    assert client.delete(f"/api/ments/{ment['id']}").status_code == 200
    assert client.get(f"/api/ments/{ment['id']}").status_code == 404


def test_empty_ment_render_rejected(env):
    app, _, admin_token = env
    client = login(app, admin_token)
    p = client.post("/api/projects", json={"name": "P"}).json()
    ment = client.post(f"/api/projects/{p['id']}/ments",
                       json={"title": "빈 멘트", "body": "", "options": {}}).json()
    assert client.post(f"/api/ments/{ment['id']}/render").status_code == 400


def test_personal_link_relogin(env):
    app, _, admin_token = env
    admin = login(app, admin_token)
    p = admin.post("/api/projects", json={"name": "P"}).json()
    inv = admin.post(f"/api/projects/{p['id']}/invites", json={}).json()

    editor = TestClient(app)
    joined = editor.post("/join/" + inv["invite_link"].split("/join/")[1], json={"name": "재접속"}).json()
    personal = joined["personal_link"].split("/join/")[1]

    # 새 기기(새 클라이언트)에서 개인 링크로 재로그인
    other = login(app, personal)
    assert other.get("/api/me").json()["name"] == "재접속"
