# docs/ — 팀 공통 문서

- [SETUP_GUIDE.md](SETUP_GUIDE.md) — 통합 저장소 clone 후 파트별 개발환경 다시 구성하기
- [LOCAL_RUN_WINDOWS_ARM.md](LOCAL_RUN_WINDOWS_ARM.md) — 개발 PC 한 대(Windows ARM + WSL2)에서 세 파트 모두 실행하기
- [DATA_FLOW_AND_GAPS.md](DATA_FLOW_AND_GAPS.md) — 합친 코드 기준 데이터 흐름과 보완·추가 구현 목록 (우선순위별)
- [INTEGRATION_REVIEW_2026-11-20.md](INTEGRATION_REVIEW_2026-11-20.md) — 게임·파이프라인·서버 연동 종합 검토
- [압축·사전 확장 설계](../pipeline/docs/COMPRESSION_EXTENSION.md) — 향후 볼륨 증가에 대비한 설계 기록. 현재 운영 추가 적용·최적화는 보류

## architecture/ — 아키텍처 그림

- `pipeline-architecture-2026-11-25.svg·png` — 현재 파이프라인 동작 아키텍처 (1~8차 보완과 후속 반영, 관측소·게스트 포함). 생성: `python docs/architecture/pipeline_architecture.py`
- `pipeline-architecture-2026-11-21.svg·png` — 1~8차 보완 시점 그림 (이전 보고서가 참조)
- `data-flow-2026-11-20.svg·png` — 보완 전 데이터 흐름과 문제 지점

## presentation/ — 발표 자료

- 파이프라인 처음 구조·현재 구조·최적화 비교 PDF와 16:9 그림 6장. 생성: `python docs/presentation/pipeline_comparison.py`

## changes/ — 파트별 변경 구현서 (각 파트 AI 에이전트 학습용)

- [2026-11-20_game.md](changes/2026-11-20_game.md) — UUIDv7 이벤트 ID, 전송 큐·만료, 미등록 미니게임, player-login, 테스트 봇
- [2026-11-20_pipeline.md](changes/2026-11-20_pipeline.md) — 모듈 구조, 원격 적재 병렬화, Silver MERGE 조건, 측정 결과
- [2026-11-20_server.md](changes/2026-11-20_server.md) — 마이그레이션 순서, recovery_key 해시

## reports/ — 보고서

- `2026-11-20_NODEVERSE_변경리포트.md` — 공용 git 정리 시점 → 1차 보완 → 2차 보완(PL-9)까지의 파이프라인 상태와 그 밖의 모든 변경

- `NODEVERSE_중간보고서_v1.0.pdf` (2026-11-10)
- `NODEVERSE_델타레이크_구현과정_오류수정내역_v1.0.pdf` (2026-11-20)
- `NODEVERSE_로그인_클라우드세이브_구현정리.pdf` (2026-11-20)

## 파트별 문서

- 게임: [`game/docs/`](../game/docs/), [`game/README.md`](../game/README.md), `game/MINIGAME_GUIDE.md`, `game/MAP_EDIT_GUIDE.md`
- 파이프라인: [`pipeline/docs/`](../pipeline/docs/) — 개요 그림(`architecture.png`), 설계 결정, 통합 현황, 원격 적재·관측소 운영, 복구 보고, E2E 시험 보고서, 델타레이크 요구사항 검토 보고서, 구현계획서·설명서
- 서버: [`server/docs/`](../server/docs/) — DB 구조, MongoDB 연동, 게임 로그인 연동, 팀 인수인계
- 공유 이벤트 형식: [`contracts/`](../contracts/)

## 저장소 폴더 구조

> 이 절은 저장소 루트 README에서 옮겨 온 요약입니다.

```
mlo-02-p3-team1/
├─ game/        Godot 프로젝트 (바이너리 에셋은 Git LFS)
├─ pipeline/    collector.py · spark/ · remote/ · observatory/ · compose.json · launcher.py
├─ server/      config/ · accounts/ · telemetry/ · templates/ · static/
├─ contracts/   공통 이벤트 규약
├─ docs/        가이드 · 검토 · 보고서 · architecture/
├─ .github/workflows/   폴더별 CI (pipeline·server·game)
└─ nodeverse.code-workspace
```

