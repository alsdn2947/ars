# LLM Wiki (ars)

한국어 LLM 지식 위키. MkDocs Material로 빌드되어 GitHub Pages(https://alsdn2947.github.io/ars/)에 공개된다.

## 이 리포에서 일할 때의 규칙

- **공개 리포다.** 개인정보·업무정보·회사 데이터는 절대 넣지 않는다. 그런 내용은 비공개 리포(emart-project)로.
- 문서는 전부 **한국어**로, `docs/` 아래 마크다운으로 작성한다.
- **새 문서를 만들면 `mkdocs.yml`의 `nav`에 반드시 등록한다.** 등록하지 않으면 사이트 메뉴에 나타나지 않는다.
- 링크는 일반 마크다운 형식 `[표시](경로.md)`만 사용한다. 옵시디언 위키링크 `[[...]]`는 MkDocs가 렌더링하지 못하므로 금지.
- 문서를 수정하면 `mkdocs build --strict`로 빌드가 깨지지 않는지 확인한다.
- 스타일: 초보자도 이해할 수 있는 설명 위주, 과장 없이, 표는 짧은 항목 나열에만.

## 구조

- `docs/index.md` — 홈(목차)
- `docs/basics/` — LLM 기초 개념
- `docs/guides/` — 실전 활용 (프롬프트, RAG, 파인튜닝, 에이전트)
- `docs/models/` — 모델 개요
- `mkdocs.yml` — 사이트 설정과 메뉴(nav)

## 배포

`main`에 푸시하면 GitHub Actions(`.github/workflows/deploy-wiki.yml`)가 자동으로 빌드·배포한다. 별도 조작 불필요.
