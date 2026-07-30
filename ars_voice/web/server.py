"""웹 서버 실행 진입점.

    ars-voice-web                      # http://0.0.0.0:8000, 데이터는 ./data
    ars-voice-web --port 8080 --data /srv/ars
    ars-voice-web --reset-admin       # 관리자 접속 링크 재발급

최초 기동 시 관리자 접속 링크가 콘솔에 한 번 출력된다. 이 링크로
접속하면 관리자로 로그인되며, 프로젝트 생성과 초대 링크 발급을 할 수 있다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ars_voice.web import db


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ars-voice-web", description="ARS 멘트 작성/추출 웹 서버")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--data", default="data", help="DB와 음원이 저장될 디렉터리 (기본: ./data)")
    p.add_argument("--reset-admin", action="store_true", help="관리자 접속 링크 재발급 후 종료")
    args = p.parse_args(argv)

    db_path = str(Path(args.data) / "ars.db")
    db.init_db(db_path)

    if args.reset_admin:
        token = db.reset_admin(db_path)
        print(f"새 관리자 접속 링크:  http://<서버주소>:{args.port}/join/{token}")
        return 0

    token = db.ensure_admin(db_path)
    if token:
        print("=" * 64)
        print("관리자 계정이 생성되었습니다. 아래 링크는 지금 한 번만 표시됩니다.")
        print(f"  관리자 접속 링크:  http://<서버주소>:{args.port}/join/{token}")
        print("분실 시: ars-voice-web --reset-admin")
        print("=" * 64)

    import uvicorn

    from ars_voice.web.app import create_app

    uvicorn.run(create_app(args.data), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
