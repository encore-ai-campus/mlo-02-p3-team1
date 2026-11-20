# docs/ — 팀 공통 문서

- [SETUP_GUIDE.md](SETUP_GUIDE.md) — 통합 저장소 clone 후 파트별 개발환경 다시 구성하기
- [BRANCH_STRATEGY.md](BRANCH_STRATEGY.md) — 브랜치·PR 규칙, 비밀값 규칙, 원본 저장소에서 가져오는 방법
- [INTEGRATION_REVIEW_2026-11-20.md](INTEGRATION_REVIEW_2026-11-20.md) — 게임·파이프라인·서버 연동 종합 검토

## instructions/ — 파트별 구현 지시서 (2026-11-16)

세 파트가 지켜야 할 공통 계약(이벤트 형식·토픽)의 원문이 여기 있습니다. `contracts/`를 바꿀 때 함께 고칩니다.

- `NODEVERSE 게임 파트 구현 지시서.pdf`
- `NODEVERSE 서버 파트 구현 지시서.pdf`
- `NODEVERSE 파이프라인 파트 구현 지시서.pdf`
- `NODEVERSE 파이프라인 구현서 (nodeverse-pipeline).pdf`

## reports/ — 보고서

- `NODEVERSE_중간보고서_v1.0.pdf` (2026-11-10)
- `NODEVERSE_델타레이크_구현과정_오류수정내역_v1.0.pdf` (2026-11-20)
- `NODEVERSE_로그인_클라우드세이브_구현정리.pdf` (2026-11-20)

## 파트별 문서

- 게임: [`game/docs/`](../game/docs/), [`game/README.md`](../game/README.md), `game/MINIGAME_GUIDE.md`, `game/MAP_EDIT_GUIDE.md`
- 파이프라인: [`pipeline/docs/`](../pipeline/docs/) — 설계 결정, 통합 현황, E2E 시험 보고서, 델타레이크 요구사항 검토 보고서, 구현 결과서(`TEAM_AI_HANDOFF_2026-11-20.pdf`), 구현계획서 v1.2·v1.3
- 서버: [`server/docs/`](../server/docs/) — DB 구조, MongoDB 연동, 게임 로그인 연동, 팀 인수인계
- 공유 이벤트 형식: [`contracts/`](../contracts/)
