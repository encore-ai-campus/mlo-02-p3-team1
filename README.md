# NODEVERSE — MLO 2기 3차 1팀 통합 저장소

게임·파이프라인·서버를 한 저장소에서 관리하는 모노레포입니다. 각 파트의 원래 커밋 히스토리는 그대로 보존되어 있습니다.

| 폴더 | 내용 | 원본 저장소 |
|---|---|---|
| `game/` | Godot 게임 클라이언트 *(가져오기 대기 중)* | junbum8398-blip/nodeverse-game (`main`) |
| `pipeline/` | 이벤트 수집기 + Kafka + Spark/Delta 파이프라인 v2 | jobless-fish/NVG (`feature/codex-pipeline-v2-20261120`의 `pipeline-v2/`) |
| `server/` | Django 대시보드·계정·게임 연동 서버 | ericsw2727/MLO_3rd_project_dashboard (`main`) |
| `contracts/` | 세 파트가 공유하는 이벤트 스키마·Kafka 토픽 | pipeline의 `contract.py`, `topics.py`에서 시작 |
| `docs/` | 팀 공통 문서 (브랜치 전략 등) | — |

## 시작하기

```bash
git clone <통합 저장소 URL>
cd mlo-02-p3-team1
git lfs install        # game/ 의 Godot 에셋은 LFS로 받습니다
code nodeverse.code-workspace
```

각 파트의 실행 방법은 파트 폴더의 README를 보세요: [`pipeline/README.md`](pipeline/README.md), [`server/README.md`](server/README.md).

## 협업 규칙 요약

- `main`은 보호 브랜치입니다. 직접 push하지 않고 PR로만 합칩니다.
- 작업 브랜치는 `game/…`, `pipeline/…`, `server/…`, `contracts/…`, `docs/…` 접두어를 씁니다.
- `contracts/`를 바꾸는 PR은 세 파트 담당자 모두의 리뷰를 받습니다.
- `.env`와 API 키는 절대 커밋하지 않습니다. `.env.example`만 올립니다.

자세한 내용은 [`docs/BRANCH_STRATEGY.md`](docs/BRANCH_STRATEGY.md)를 보세요.
