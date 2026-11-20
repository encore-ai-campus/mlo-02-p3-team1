# 브랜치 전략과 저장소 운영 규칙

## 1. 구조

하나의 저장소(모노레포)에 파트별 폴더를 둡니다. 원래 저장소들의 커밋 히스토리는 각 폴더 아래로 옮겨져 보존되었습니다
(`git log -- server/` 처럼 폴더 단위로 히스토리를 볼 수 있습니다).

```
mlo-02-p3-team1/
├─ game/       Godot 클라이언트 (Git LFS로 바이너리 에셋 관리)
├─ pipeline/   수집기·Kafka·Spark/Delta
├─ server/     Django 대시보드
├─ contracts/  공유 이벤트 스키마·토픽 (세 파트의 약속)
├─ docs/       공통 문서
└─ .github/workflows/  폴더별로 나뉜 CI
```

## 2. 브랜치

| 브랜치 | 용도 | 규칙 |
|---|---|---|
| `main` | 항상 실행 가능한 통합본 | 보호 브랜치. PR + 리뷰 1명 이상 + CI 통과 후에만 병합. 직접 push·force push 금지 |
| `game/<작업명>` | 게임 파트 작업 | `main`에서 따서 PR로 `main`에 합침 |
| `pipeline/<작업명>` | 파이프라인 파트 작업 | 〃 |
| `server/<작업명>` | 서버 파트 작업 | 〃 |
| `contracts/<작업명>` | 공유 스키마 변경 | 세 파트 담당자 모두 승인 필요 |
| `docs/<작업명>` | 문서 | 〃 (리뷰 1명) |

- 작업 브랜치는 짧게 유지하고(1~3일), 자주 `main`을 받아옵니다: `git pull --rebase origin main`.
- 한 PR은 되도록 한 폴더만 건드립니다. 여러 폴더를 함께 바꿔야 하면(예: 스키마 변경과 그에 맞춘 수집기 수정) PR 설명에 이유를 적습니다.
- 병합 방식은 **Squash merge**를 기본으로 합니다.
- 발표·시연 시점에는 `main`에 태그를 붙입니다: `v0.1-demo` 등.

## 3. GitHub 설정 (통합 저장소를 만든 뒤 할 일)

1. Settings → Branches → `main`에 Branch protection(또는 Ruleset) 추가
   - Require a pull request before merging (승인 1명)
   - Require status checks to pass (`.github/workflows`의 잡)
   - Block force pushes, Restrict deletions
2. `CODEOWNERS` 추가 (예시, 실제 GitHub 아이디로 바꿔서):
   ```
   /game/       @게임담당
   /pipeline/   @파이프라인담당
   /server/     @서버담당
   /contracts/  @게임담당 @파이프라인담당 @서버담당
   ```
3. Settings → Secrets에 필요한 키만 등록 (코드에는 절대 넣지 않음).

## 4. 비밀값 규칙

- `.env`, `*.pem`, `*.key`, 키스토어는 루트 `.gitignore`로 막혀 있습니다. `.env.example`에 키 이름만 적습니다.
- 브라우저·게임 클라이언트 코드(`config.js` 등)에 API 키를 넣지 않습니다. 필요한 호출은 서버를 거칩니다.
- 실수로 커밋했다면: **먼저 키를 폐기·재발급**하고, 그다음 히스토리에서 지웁니다(아래 5-3 참고). 지우는 것만으로는 안전하지 않습니다.

## 5. 원본 저장소에서 다시 가져오기 / 추가하기

이 저장소는 `git filter-repo`로 원본 히스토리를 폴더 아래로 옮긴 뒤 병합하는 방식으로 만들었습니다.
준비: `pip install git-filter-repo`

### 5-1. game/ 가져오기 (2026-11-20 완료, 다시 가져올 때 참고)

```bash
# 임시 폴더에서
git clone --single-branch -b main https://github.com/junbum8398-blip/nodeverse-game.git game-import
cd game-import
git lfs fetch --all                       # 원본에 LFS 객체가 있다면
# (1) API 키를 히스토리에서 지움: replace.txt 에 "<키 문자열>==>REDACTED" 한 줄씩
#     원본은 키를 뒤집어서 저장했으므로 정방향·역방향 두 줄을 모두 적는다
python -m git_filter_repo --replace-text ../replace.txt --force
# (2) game/ 폴더 아래로 이동
python -m git_filter_repo --to-subdirectory-filter game --force

# 통합 저장소에서
git checkout -b game/import
git rm -r game/README.md && git commit -m "game/ 자리표시 README 제거"
git pull --allow-unrelated-histories --no-rebase ../game-import main
```

원본 게임 저장소는 에셋을 일반 git 파일로 저장하고 있습니다. 가져온 뒤 바이너리를 LFS로 옮기려면
통합 저장소를 **처음 push하기 전에** 한 번만 실행합니다(히스토리를 다시 쓰므로):

```bash
git lfs migrate import --include-ref=refs/heads/game/import \
  --include="game/**/*.glb,game/**/*.gltf,game/**/*.fbx,game/**/*.blend,game/**/*.png,game/**/*.jpg,game/**/*.webp,game/**/*.ttf,game/**/*.otf,game/**/*.wav,game/**/*.ogg,game/**/*.mp3"
```

가져온 뒤 `game/website/config.js`에 키가 없는지 다시 확인합니다:
`git log -p -- game/website/config.js | grep -i apikey`

### 5-2. 원본 저장소가 계속 업데이트될 때

통합 저장소가 GitHub에 올라간 뒤에는 **여기가 유일한 원본**이 되어야 합니다. 원본 저장소에서 계속 작업하면 두 곳이 갈라집니다.
전환 기간에 원본 쪽 새 커밋을 받아야 한다면 5-1과 같은 방식(filter-repo → 병합)으로 다시 가져오면 같은 커밋 ID가 나오므로 새 커밋만 추가됩니다.

### 5-3. 히스토리에서 비밀값 지우기

```bash
python -m git_filter_repo --replace-text replace.txt --force
```
이미 push한 저장소라면 모든 팀원이 다시 clone해야 합니다. 키 폐기가 먼저입니다.

## 6. 가져온 출처 기록

| 폴더 | 원본 | 브랜치 | 가져온 날짜 |
|---|---|---|---|
| `pipeline/` | jobless-fish/NVG, `pipeline-v2/` 하위만 (`32b0248`까지) | `feature/codex-v2-remote-sink` (처음엔 `feature/codex-pipeline-v2-20261120`) | 2026-11-20 15:22 |
| `server/` | ericsw2727/MLO_3rd_project_dashboard (`3dfece8`까지) | `main` | 2026-11-20 15:52 |
| `game/` | junbum8398-blip/nodeverse-game (`88394b1`까지, Groq 키 제거·바이너리 LFS 전환) | `main` | 2026-11-20 15:24 |

NVG 저장소에 함께 있는 옛 게임 코드와 `pipeline/`(v1)은 가져오지 않았습니다.
서버 원본의 `server/live-members-releases` 브랜치도 가져오지 않았습니다(필요하면 같은 방식으로 추가).
