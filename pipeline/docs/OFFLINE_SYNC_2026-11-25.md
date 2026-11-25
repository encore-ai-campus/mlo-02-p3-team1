# 장기 오프라인 학습 기록 동기화 — 구현·시험 및 배포 검토서

> 후속 결정: 압축·사전 코드화 최적화는 향후 데이터 볼륨이 커졌을 때 검토할 설계로 남기고 추가 적용은 보류합니다. 아래는 구현·격리 시험의 기록이며 운영 활성화 지시가 아닙니다. 현재 우선순위와 적용 범위는 [압축·사전 확장 설계](COMPRESSION_EXTENSION.md)를 참고하세요.

2026-11-25. **구현 및 격리 시험 완료, 운영 활성화 승인 대기.** 자동 승인 검토에서 공개 API 지속 활성화·운영 서비스 재구성을 명시적 배포 승인 부족으로 거절했다. 운영 배포 명령은 실행되지 않았다. 현재 운영 collector의 OFFLINE_ENABLED는 0이며 게임 EXE도 수정하지 않았다.

## 해결하는 문제와 경로

30일 이상 네트워크 없이 누적한 학습 기록을 다시 보낼 수 있다. 기존 실시간 `/v2/events`의 6일 제한과 Kafka·Spark 워터마크를 늘리지 않았다. 과거 기록은 실시간 Gold 및 실패 급증 경보에서 분리했다.

```text
게임에 연결할 SQLite 참조 큐
  → gzip 조각·고정 upload ID·사전 버전
  → 기존 공개 게이트웨이의 고정 /v2/offline 경로 [운영 활성화 대기]
  → collector: 검증 + journal/majority 확인 후 Mongo 조각 보관
  → seal: Mongo queued + Kafka nv.offline.learning.v1 알림
  → 별도 Spark 배치 처리기
      ├─ Delta offline.bronze_learning: 원본 보존
      ├─ 제한된 속도로 공유 Outbox에 offline lane 등록
      │    → 기존 writer: live 우선 처리 → 원격 MySQL/MongoDB
      └─ 원격 stored 확인 후 offline.silver_learning
           → 실제 발생일별 offline_play_daily (로컬 Mongo, offline_only)

기존 실시간 경로 → 기존 Bronze/Silver/Gold (변경된 날짜·과거 이벤트 미유입)
```

Kafka는 준비된 업로드의 **알림**을 전달한다. 조각 본문과 처리 위치의 권위 있는 원장은 MongoDB이며, 알림 손실·Kafka 일시 단절 시에도 queued 원장 조회로 복구한다. Kafka 알림 commit은 최종 DB 적재 완료라는 뜻이 아니다. 과거 이벤트 본문 전체가 실시간 Kafka 토픽을 통과하는 구조가 아니다.

## 규약과 보호 장치

| 항목 | 구현한 규칙 |
|---|---|
| 대상 | schema_version 2 학습 이벤트 전용. runtime/update 장기 동기화는 후속 범위 |
| 접수 기간 | 수신 시각 기준 과거 90일 이내. 원래 occurred_at과 기존 payload_hash 규칙 유지 |
| 업로드 창 | 같은 회원·세션, 연속된 sequence, 최대 2,000 이벤트. 긴 세션은 여러 창으로 분리하고 원래 순서 유지 |
| 조각 | 최대 200 이벤트, 압축 요청 128KiB, 압축 해제 256KiB, 최대 64조각. manifest 본문 16KiB |
| 사전 | offline/codebook-v1.json의 고정 코드. 정수 event_type·operation 또는 기존 문자열 지원. v1의 의미를 바꾸거나 코드를 재사용하지 않음 |
| 저장 확인 | 조각 PUT 응답은 Mongo의 majority+journal 확인 후 반환. 최종 DB 반영과 구분 |
| 재개 | 동일 upload ID·manifest·조각 hash 사용. 서버 수신 목록을 기준으로 누락 조각만 전송 |
| 중복 | 영구 offline_event_registry의 event_id/hash, 공유 Outbox 및 기존 원격 projector의 멱등성 검증. 다른 내용으로 덮어쓰지 않음 |
| 순서 | seal 전에 전체 조각의 개수·고유 ID·연속 sequence 검사. 선행 창 누락은 기존 순서 대기·보관 규칙 적용 |
| 접수 제한 | 전체 진행 중 100개, 설치 ID별 4개. Mongo admission lock으로 동시 등록 직렬화. 한도 초과는 429 + Retry-After |
| 적재 제한 | 기본 전체 처리기 20건/초, offline Outbox 비완료 200건까지. live 대기가 있으면 추가 offline 등록 양보 |
| 우선순위 | 기존 writer는 due 상태에서 live/기존 무표시 행을 먼저 claim하고 남는 자리에 offline을 배정 |
| 복구 | 전용 처리기 단일 lease·heartbeat·stage_cursor. 강제 종료 후 lease 만료를 기다린 뒤 재개 |
| 날짜 | offline Delta event_date는 실제 occurred_at 날짜. 날짜별 파티션과 명시적 MERGE 날짜 조건 사용. 온라인 7일 탐색 규칙을 재사용하지 않음 |
| 완료 | 원격 stored 확인 및 과거 Silver·일별 집계 완료 후 remote_complete=true. 완료 영수증은 Outbox TTL 이후에도 업로드 원장에 보존 |

제한은 최초 안전 기본값이다. 여러 기기의 월간 대용량을 감당하는 용량 보장 수치가 아니다. live 우선 정책상 부하가 계속 높으면 offline은 오래 기다릴 수 있다. 보관 중 조각과 ID 원장에는 자동 TTL을 두지 않았으며, 취소·장기 방치 업로드 정리 및 서버 저장량 알림·백업/보관 정책은 후속 운영 과제다.

설치 UUID는 라우팅·전송량 제어용이며 사용자 인증 수단이나 기기 지문이 아니다. 공유 ingest key가 있는 신뢰된 내부 클라이언트 범위의 첫 구현이다. 불특정 외부 사용자 대상 배포 전에는 회원별 업로드 소유권·토큰·키 분리·지속 데이터 용량 제한을 추가해야 한다.

## 실제 시험 결과

운영과 분리된 `nv-baseline-offline-20261125` 프로젝트에서 Kafka RF3, 별도 Mongo/MySQL, 실시간 Spark와 오프라인 Spark를 사용했다. 시험 종료 후 해당 스택은 정지했고 볼륨·SQLite·로그는 보존했다.

| 시험 | 결과 |
|---|---|
| 30일 전 225건·45일 전 5건 | 두 클라이언트 동시 재개·seal, 원격 저장 및 과거 날짜 집계 성공 |
| 첫 조각 응답 유실 + collector 실제 재시작 | 서버 수신 목록으로 누락 조각부터 이어 전송, 중복 없음 |
| 완료 업로드 재전송 | 원격 원본·행동 로그 건수 유지 |
| 외부/내부 키가 다른 게이트웨이 | 별도 키를 보존한 전달 및 gzip 지원 확인 |
| 60일 전 5건 추가 | 게이트웨이를 거쳐 원격 저장 완료 |
| 75일 전 500건, cursor 140에서 SIGKILL | 실제 처리기 강제 종료·재시작 후 cursor 복구 및 최종 완료. 시험 lease는 15초, 운영 기본은 120초 |
| 최종 원격 원본 / 행동 로그 | 각각 740건 = offline 735 + live 5 |
| offline Bronze / Silver / Silver 고유 ID | 각각 735건 |
| live Bronze | 재전송 원본 10건, 고유 이벤트 5건. append 원본 보존으로 정상 |
| live Silver / 고유 ID | 각각 5건 |
| live Gold | 시도 1 / 성공 1. 과거 735건은 오늘 집계에 미반영 |
| 과거 발생일 | 2026-09-11, 09-26, 10-11, 10-26 유지 |
| Python 회귀 시험 | 최종 145 passed, 2 skipped. PySpark 환경 의존 시험 skip과 별도 실제 Spark/Delta 검증을 구분 |

최초 Delta 검증식은 재전송 원본 Bronze도 5건이어야 한다고 잘못 가정해 실패했다. 원본 건수와 고유 건수를 구분하도록 수정한 뒤 읽기 전용 검증을 다시 실행했고 verification_passed=true를 확인했다. 실제 데이터 누락·Silver 중복으로 인한 실패가 아니었다.

증거 파일: [evidence/offline-2026-11-25](evidence/offline-2026-11-25). 합성 데이터의 단계별 결과이며 서로 다른 시점의 누계다. 최종 740건은 crash-result.json, 경로 분리는 offline-delta-result.json을 기준으로 한다. 후속 보완인 접수 직렬화·manifest 크기 제한·상태 필드·전송 backoff는 단위 시험과 추가 게이트웨이 접수로 검증했으며 동일 735건 전체 부하를 모든 코드 변경마다 재실행한 것은 아니다.

## 게임 담당자 연결 지침

게임 최신 소스·배포 EXE 버전과 로그인 회원 ID 규칙을 먼저 확인한다. 이번에는 게임 파일을 수정하거나 EXE에 SQLite를 포함해 재빌드하지 않았다. offline/client.py는 Python 참조 구현이며 Godot가 그대로 실행할 수 있는 플러그인이 아니다. 게임 측에서 동일 규약을 구현하거나 검증된 보조 프로세스를 연결해야 한다.

1. 게임은 이벤트 생성 시 Queue.append(event)를 호출해 SQLite pending에 즉시 기록한다. 재접속하면 Queue.prepare(session_id)가 최대 2,000건의 연속 창을 조각 큐로 원자적으로 이동한다. 중간 재시작·설치 UUID 유지·중복 append·용량 한도 시 기존 기록 보존을 시험했다. 참조 구현은 준비됐으나 실제 게임 이벤트 콜백과의 연결은 남아 있다. 디스크 I/O는 렌더 스레드 밖에서 처리한다.
2. 설치 ID는 로컬 설정에 한 번 생성해 유지한다. 플레이어 ID·세션 ID·시도 ID·event_id·sequence는 재전송 때 변경하지 않는다. 선행 창부터 seal하고 서버에서 접수했다고 확인하기 전 새 식별자로 바꾸지 않는다.
3. Queue(path).enqueue(installation_id, events)로 창을 저장하고, 동일 upload ID로 sync_with_retry를 호출한다. 키는 런타임 비밀 설정에서 주입하며 SQLite나 코드에 저장하지 않는다. 429/503/네트워크 오류는 Retry-After와 지수 backoff+jitter로 재시도하고 한도 이후 로컬 데이터를 유지한다.
4. remote_complete 확인 전에는 prune_completed가 거부된다. 완료 후에도 원래 hash·upload ID 영수증은 남긴다. 참조 큐는 압축 payload 64MiB 제한이며 DB 인덱스·WAL까지 포함한 총 디스크 상한은 아니다. 디스크 부족 시 오류를 표시하고 기존 기록을 임의 삭제하지 않는 게임 UX가 필요하다.
5. 입력은 원래 상세값을 유지한 JSON 학습 이벤트다. event_type/operation의 정수 코드를 선택적으로 사용할 수 있으나 참조 큐가 모든 문자열을 자동 단축하는 기능은 아니다. 미지원 코드·사전 버전은 422로 거부하고 로컬 원본을 유지한다.

서버 API (아직 운영 활성화 전):

```text
PUT  /v2/offline/uploads/{upload_id}                 manifest 등록
PUT  /v2/offline/uploads/{upload_id}/chunks/{index}  조각 저장, gzip 가능
POST /v2/offline/uploads/{upload_id}/seal            개수·순서 검증 후 대기열 등록
GET  /v2/offline/uploads/{upload_id}                 수신 조각·적재 상태·최종 완료 조회
```

모든 요청에 X-API-Key가 필요하다. 기존 공개 주소 기준 base URL은 http://192.168.0.81:8000이며, 활성화 전에는 이 경로로 업로드할 수 없다. 사전 버전 1은 고정·보존하고 새 의미는 새 코드/새 버전의 명시적 계약으로 추가한다.

## 운영 배포 승인 시 적용할 구체적 변경

- 현재 코드에서 Dockerfile로 app 이미지를 빌드하고, Dockerfile.spark 기반 런타임을 준비한 뒤 Dockerfile.offline으로 별도 Spark 이미지를 빌드한다. 현재 Spark 이미지의 Python 3.8 호환 wheel 때문에 Kafka 알림 consumer는 confluent-kafka 2.4.0, API producer는 기존 2.8.0을 사용한다. Python/클라이언트 런타임 업그레이드는 후속 검토 대상이다.
- offline bootstrap으로 알림 토픽 RF3/ISR2와 Mongo 인덱스를 먼저 만든다. 실시간 기본 TOPICS를 변경하지 않는다.
- 기존 운영 Compose와 runtime-source override 뒤에 compose.offline.yaml을 추가하고 OFFLINE_ENABLED=1, OFFLINE_APP_IMAGE, OFFLINE_SPARK_IMAGE, PIPELINE_APP_IMAGE, PIPELINE_SOURCE_ROOT를 지정한다. collector·writer를 새 이미지로 바꾸고 Spark는 체크포인트를 유지한 재시작, offline-processor를 별도 실행한다.
- 기존 v1 게이트웨이를 사용할 경우 Dockerfile.gateway-offline로 원본 기능을 유지한 어댑터 이미지를 만들고 기존 base/LAN/v2-bridge 파일 뒤에 compose.offline-gateway.yaml을 추가한다. OFFLINE_GATEWAY_IMAGE와 OFFLINE_ENABLED=1을 지정하며 외부·내부 키와 기존 포트 바인딩을 보존한다.
- 승인 후 먼저 정상 실시간 5건과 30일 전 시험 5건을 공개 주소로 보내 원격 DB·과거 날짜·상태 API를 재검증한다. 아직 실제 운영 DB로 이 오프라인 시험을 수행한 상태는 아니다.
- 운영 전환을 되돌리려면 오프라인 기능 플래그를 0으로 내리고 전용 처리기를 정지한다. 이미 접수한 원장·조각·registry·Delta를 삭제하지 않는다. 진행 중 업로드의 처리·보관 방침을 확인하고 이미지/Compose를 이전 설정으로 돌린다.

## 남은 고도화

월간 대규모 데이터·여러 기기 수십~수백 개 동시 접속 부하, 저장 공간 경보·장기 보관 정책, 회원별 소유권 인증, 게임 내 즉시 영구 큐 연결, UI 진행률, 다기기 동일 회원/동일 세션 충돌, 기기 시계 검증은 남아 있다. offline_play_daily는 로컬 Mongo의 offline_only 집계이며 기존 관리자 대시보드에 자동 병합한 총합이 아니다. 팀원 서버에 일별 지표를 제공하려면 별도 계약이 필요하다.

실행은 적어도 한 번 재개될 수 있고 이벤트 ID·내용 해시·MERGE·projector를 통해 효과를 멱등하게 만드는 방식이다. MySQL·MongoDB·Delta 전체를 묶는 분산 트랜잭션이나 모든 전원 장애에 대한 end-to-end exactly-once를 보장한다고 표현하지 않는다.
