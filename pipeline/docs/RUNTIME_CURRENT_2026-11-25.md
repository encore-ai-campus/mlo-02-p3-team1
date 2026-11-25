# 파이프라인 실행 코드 현행화 완료

2026-11-25. 이 문서는 앞선 TEAM_INTEGRATION_2026-11-25.md의 ‘운영 Spark 미전환’ 상태를 갱신한다.

## 적용 내용

최신 main(c384eed 기준)을 받아 팀원 게임·서버 변경을 보존했다. 게임 소스나 EXE를 수정하지 않았다. 운영 Spark의 구형 단일 파일 실행을 저장소의 모듈형 코드로 전환했다. `--py-files`에 tables, audit_state, sinks, compaction, bronze, silver, gold, periodic을 전달하며 common·remote도 같은 저장소에서 읽는다.

collector·writer는 현재 저장소로 빌드한 `nodeverse-pipeline-current:20261125` 이미지로 함께 재생성했다. 내부·외부 키 구분, DB 계정, 회원 매핑, 게스트 활성 설정은 유지했다. writer의 회원 캐시 유효 TTL은 0이다.

따라서 팀원의 압축 순서 교정, 실제 날짜 collect_set, 실패 급증 경보 비교 기준과 우리의 state 객체 호환·게스트 처리·관측소 수정이 실행 경로에 함께 반영됐다. 압축 자체의 비동기 분리는 수행하지 않았다. 중복 상태 TTL은 기존 168h를 유지했으며 48h로 바꾸지 않았다.

## 데이터·체크포인트 보존

운영 Spark를 잠시 정지해 Delta와 체크포인트를 일관된 상태로 복제한 뒤 구버전을 재시작했다. 복제 볼륨 `nodeverse-modernization-trial-20261125`, 별도 로컬 Mongo DB `nodeverse_modernization_trial`에서 최신 코드를 실행했다. 시험 Spark는 원격 DB에 직접 쓰는 worker를 실행하지 않는다. 이후 8개 쿼리 활성·새 진행 시각·재시작 0·게시 실패 0을 확인했다.

전환 직전 `nodeverse-modernization-predeploy-20261125` 백업 볼륨을 별도로 만들었다. 운영은 기존 `nodeverse-v2-live_lake`와 8개 체크포인트를 그대로 사용한다. Kafka·원격 DB·로컬 DB를 초기화하거나 체크포인트를 새로 만들지 않았다. 시험 컨테이너는 정지했고 시험 자료와 백업은 보존했다.

## 실제 시험 결과

| 항목 | 결과 |
|---|---|
| 기존 Python 회귀 시험 | 134 passed, 2 skipped (로컬 PySpark 미설치) |
| 별도 Spark 환경의 팀원 alert baseline 시험 | 5 passed, 20.87초 |
| 최신 운영 Spark | 8개 활성, query_restarts {}, sink_failures 0 |
| 공개 API 정상 플레이 전송 | 5/5 접수 |
| 원격 원본 / 행동 로그 | 각각 5/5 저장 |
| 회원 연결 | MySQL CHAR(32) 회원 1명과 Mongo UUID(36) 세션 1개 연결 확인 |
| 같은 이벤트 5건 재전송 | 5/5 재접수, 확인 시 원격 원본·행동 로그 각각 5건 유지 |
| 관측소 | stored 97, quarantined 5, pending·processing·retrying·waiting_context·parked·blocked 0 |
| 관측 구간 시간 (시험 5건 배치) | 계획 1,130ms / MERGE 2,403ms / Outbox 328ms / 유지보수 2ms |

구간 시간은 시험 배치 하나의 관측값으로, 전체 전달 지연이나 부하 성능 보장을 의미하지 않는다. 유지보수 2ms는 실제 압축 부하 시험을 했다는 의미가 아니다. 기존 격리 5건은 보존했다. 관리자 대시보드 시각 검증은 이번 범위에 포함하지 않았다.

## 실행 구성을 다시 재현하는 방법

신규 환경은 기본 build_compose.py/compose.json을 사용한다. 기존 운영 프로젝트를 유지하며 코드 경로를 갱신할 때는 `compose.runtime-source.yaml`을 **마지막 override**로 사용한다. 이 파일만 단독 실행하지 않는다.

1. 이 저장소 pipeline 폴더에서 `docker build -t <검증한-이미지-태그> -f Dockerfile .`을 실행한다.
2. 비공개 배포 env 파일에 `PIPELINE_SOURCE_ROOT`를 현재 pipeline 폴더의 절대 경로(Windows도 / 사용)로, `PIPELINE_APP_IMAGE`를 위 이미지 태그로 지정한다. 경로와 태그 외의 키·DB 비밀번호는 Git에 넣지 않는다.
3. 기존 Compose 프로젝트 이름, 기존 env 파일·override를 모두 유지한 명령에 이 env 파일과 `-f <pipeline 절대경로>/compose.runtime-source.yaml`을 추가한다. config를 비공개로 검사하고 /data가 기존 lake 볼륨인지 확인한다. config 전체에는 키가 있을 수 있으므로 공유하지 않는다.
4. 안정된 백업·복제 시험 후 `up -d --no-deps --no-build spark collector remote-writer`로 해당 서비스만 적용한다. Spark 바인드 마운트 소스는 실행 중 수정하지 않는다. pull 후에도 이미 import된 모듈은 자동 갱신되지 않으므로 재검증·재시작이 필요하다.
5. 다음 읽기 전용 명령으로 소스 일치를 확인한다.

```text
python tools/check_runtime_source.py --container nodeverse-v2-live-spark-1 --role spark
python tools/check_runtime_source.py --container nodeverse-v2-live-collector-1 --role collector
python tools/check_runtime_source.py --container nodeverse-v2-live-remote-writer-1 --role writer
```

spark는 23개 Python 모듈, collector는 collector.py·contract.py, writer는 settings·projection·worker의 해시를 비교한다. 이는 전체 이미지 공급망이나 의존 패키지 전체 일치 검사는 아니다. 관측소 실행 메타데이터는 `tools/capture_observatory_runtime.py`로 갱신한다.

## 다음 단계와 복구

압축 별도 실행 및 테이블별 충돌 제어, 대량 부하 시험, 48h 중복 상태 비교는 후속 과제다. 우선 새 운영 코드로 신규 플레이 지연·MERGE 범위·작업자 대기를 관측한다.

시작 실패가 발견되면 Spark만 정지하고 이전 Compose override 구성으로 되돌린다. 체크포인트 스키마나 Delta 로그를 무작정 삭제하지 않는다. 전환 뒤 데이터가 유입됐다면 백업 볼륨으로 덮어쓸 경우 유입분을 잃을 수 있으므로 먼저 보존·대조해야 한다. 이번 전환에서는 기존 체크포인트 복구가 성공했으며 백업 복원은 수행하지 않았다.
