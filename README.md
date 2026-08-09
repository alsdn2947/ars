# LLM Wiki

LLM(대규모 언어 모델)에 관한 지식을 정리하는 위키입니다. [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) 기반으로 만들어졌습니다.

## 구조

```
mkdocs.yml          # 사이트 설정 및 메뉴(nav)
docs/
├── index.md        # 홈
├── basics/         # LLM 기초 개념
├── guides/         # 실전 활용 가이드 (프롬프트, RAG, 파인튜닝, 에이전트)
└── models/         # 주요 모델 개요
```

## 로컬에서 미리보기

```bash
pip install "mkdocs-material==9.*"
mkdocs serve
```

브라우저에서 <http://127.0.0.1:8000> 을 열면 위키를 볼 수 있습니다. 파일을 저장하면 자동으로 새로고침됩니다.

## 문서 추가하는 법

1. `docs/` 아래 적절한 폴더에 마크다운 파일을 만듭니다.
2. `mkdocs.yml`의 `nav` 섹션에 새 문서를 등록합니다.
3. 커밋 후 푸시합니다.

## 배포

`main` 브랜치에 푸시하면 GitHub Actions(`.github/workflows/deploy-wiki.yml`)가 자동으로 GitHub Pages에 배포합니다.

최초 1회 설정: 저장소 **Settings → Pages → Source**를 **GitHub Actions**로 변경해야 합니다.
