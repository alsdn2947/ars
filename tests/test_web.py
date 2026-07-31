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
    monkeypatch.setattr(renderer, "ENGINE_FACTORY", lambda engine, voice, speed=1.0: FakeEngine())
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

    # 3종 세트(mp3/wav/vox)가 모두 생성된다
    assert sorted(f.split(".")[-1] for f in status["files"]) == ["mp3", "vox", "wav"]

    # 형식별 다운로드
    for fmt in ("mp3", "wav", "vox"):
        res = client.get(f"/api/renders/{render_id}/download?fmt={fmt}")
        assert res.status_code == 200, fmt
        assert len(res.content) > 500, fmt
    assert client.get(f"/api/renders/{render_id}/download?fmt=ogg").status_code == 404

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


def _wait_render(client, render_id):
    for _ in range(100):
        status = client.get(f"/api/renders/{render_id}").json()
        if status["status"] in ("done", "error"):
            return status
        time.sleep(0.1)
    return status


def test_bgm_upload_and_use(env, tmp_path):
    app, _, admin_token = env
    client = login(app, admin_token)
    p = client.post("/api/projects", json={"name": "P"}).json()

    # 업로드 (저작권 무료 음원 대용으로 합성 wav 사용)
    wav_path = tmp_path / "무료음원.wav"
    Sine(220).to_audio_segment(duration=2000).apply_gain(-12).export(wav_path, format="wav")
    res = client.post("/api/bgm/upload?name=무료음원.wav", content=wav_path.read_bytes())
    assert res.status_code == 200
    assert res.json()["name"] == "무료음원.wav"

    # 목록/메타에 나타난다
    assert any(f["name"] == "무료음원.wav" for f in client.get("/api/bgm").json())
    meta = client.get("/api/meta").json()
    assert any(f["name"] == "무료음원.wav" for f in meta["bgm_files"])
    assert any(e["id"] == "edge" and e["available"] for e in meta["engines"])

    # 업로드한 BGM으로 렌더링
    ment = client.post(f"/api/projects/{p['id']}/ments", json={
        "title": "업로드 BGM", "body": "안녕하세요.",
        "options": {"bgm": "file:무료음원.wav"}}).json()
    r = client.post(f"/api/ments/{ment['id']}/render").json()
    status = _wait_render(client, r["render_id"])
    assert status["status"] == "done", status.get("error")


def test_bgm_upload_rejects_bad_files(env):
    app, _, admin_token = env
    client = login(app, admin_token)
    assert client.post("/api/bgm/upload?name=evil.exe", content=b"x").status_code == 400
    assert client.post("/api/bgm/upload?name=..%2F..%2Fx.mp3", content=b"x").status_code in (200, 400)
    # 경로 탈출 시도는 basename으로 잘려 저장된다 — 상위 디렉터리에 파일이 생기지 않아야 함
    files = [f["name"] for f in client.get("/api/bgm").json()]
    assert all("/" not in f and ".." not in f for f in files)


def test_unknown_uploaded_bgm_fails_gracefully(env):
    app, _, admin_token = env
    client = login(app, admin_token)
    p = client.post("/api/projects", json={"name": "P"}).json()
    ment = client.post(f"/api/projects/{p['id']}/ments", json={
        "title": "없는 BGM", "body": "안녕하세요.",
        "options": {"bgm": "file:없는파일.mp3"}}).json()
    r = client.post(f"/api/ments/{ment['id']}/render").json()
    status = _wait_render(client, r["render_id"])
    assert status["status"] == "error"
    assert "찾을 수 없습니다" in status["error"]


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
