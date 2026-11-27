# 원격 복구 감시·예약 압축·부하 시험 운영 지침

## 원격 자료 유실 감시

remote-writer는 새 이벤트가 없어도 로컬 Outbox의 stored 행을 `_id` 순서로 나눠 원격 아카이브·대시보드 참조·MySQL 회원을 검증한다. 기본 `REMOTE_INTEGRITY_INTERVAL_S=30`, `REMOTE_INTEGRITY_BATCH=100`이다. 매 회 최신 stored 10건도 추가 확인해 과거 백업으로 되돌린 상황을 빠르게 잡는다. 원격 조회는 컬렉션별 묶음 조회와 회원 IN 조회를 사용한다. 검증 위치·누적 건수·마지막 순회 완료 시각은 로컬 `pipeline_controls/remote_integrity`에 저장돼 프로세스 재시작 후 이어진다. `(state,_id)`와 `(state,stored_at)` 인덱스를 사용하며 매 30초 전체 스캔하지 않는다.

- 유실·내용/회원 불일치: `recovery_required`를 영속 기록하고 신규 적재·실시간 지표 복사를 보호 중지한다. 수집 API·Kafka·Spark·Outbox 수집은 유지한다. DB 접속 실패는 `unavailable`로 구분하며 복구 후 검사에 다시 성공해야 적재를 재개한다.
- 임의로 오류를 확인 처리하거나 writer를 재시작해도 유실 차단은 풀리지 않는다. 관측소 경고 이력에서 **원격 DB 정합성·복구** 안내와 incident를 확인한다.
- 감시는 Outbox에 남아 있는 stored 이력에 한정한다. TTL로 삭제된 과거 자료·로컬 DB까지 함께 유실된 경우·대상 DB만의 전체 무결성을 증명하지 않는다. 백업을 대신하지 않는다.
- 부분 유실의 발견 시간은 순회 위치에 따라 달라진다. 대략 `ceil(보존 stored 수/배치 크기) × 검사 간격 + 검사 실행 시간`의 순회 시간이 필요하다. 관측소의 cycle 완료 시각을 확인하고, 보존량이 늘면 검사량·간격과 원격 DB 부하를 함께 조정한다. 전 행의 즉시 감지를 보장하지 않는다.

컨테이너 안에서:

```text
python -m remote.integrity status
python -m remote.integrity verify
python -m remote.integrity acknowledge --incident <현재 incident>
```

`verify`는 전체 보존 이력을 검증하지만 차단을 풀지 않는다. `acknowledge`는 현재 incident가 일치하고 전체 검증이 성공한 경우에만 해제한다. 강제 무시 옵션은 없다.

복구 순서: writer를 멈추고 원격 MySQL·MongoDB 및 로컬 투영 상태·Delta·체크포인트를 백업 → 일치 시점의 원격 자료 복원 또는 별도 환경에서 순서 재구축 → writer가 멈춘 동안 verify/acknowledge를 일회성 컨테이너에서 실행 → writer 재개 → 대기 행 해소·회원·게임 참조와 관측소 경고 해제를 확인한다. 원격 DB에 다른 쓰기 작업이 없는 복구 시간에 전체 검증한다. 영구 손실 자료를 무시하기 위해 로컬 stored 이력을 지우지 않는다.

격리된 실제 MongoDB 복구 시험:

```text
python -m tools.integrity_drill
```

`nodeverse_test_integrity_*` 임시 DB에만 쓰고 정리한다. 운영 원격 DB는 변경하지 않는다.

## Windows 예약 압축

```powershell
powershell -File tools/register_maintenance.ps1
python tools/maintenance_job.py
```

예약 이름은 `NODEVERSE-Pipeline-Maintenance`, 매일 **Windows 로컬 시각 03:00**이다. 현재 운영 PC 시간대는 Korea Standard Time이다. 이 PC는 Docker Desktop을 사용하는 로그인 사용자 작업으로 등록한다. PC·Docker가 켜져 있고 해당 사용자가 로그인한 상태여야 실행된다. 로그오프 상태의 상시 서버는 서비스 계정 방식으로 별도 이관해야 한다. 놓친 실행은 실행 가능 시 따라잡도록 설정한다.

기본 대상은 `silver.learning_events`, `gold.minigame_1m`이다. 다른 테이블은 별도 --table 계획을 검토한 뒤 예약 인수를 조정한다. 호스트 전용 작업이므로 Docker 소켓을 웹 서비스에 공개하지 않는다.

1. 실행 계획·중복 작업 잠금을 검사한다.
2. 현재 Spark 컨테이너만 정상 중지하고, 같은 이미지·볼륨·Delta 설정의 별도 컨테이너로 OPTIMIZE를 실행한다. 수집 API·Kafka·DB·writer는 유지한다.
3. 테이블 전체 행 수가 유지됐는지 비교한다. 완료·실패와 관계없이 임시 작업을 정리하고 원래 Spark를 시작한다.
4. 새 실행의 진행 파일과 8개 활성 쿼리를 확인한다. 재개 실패를 성공으로 기록하지 않는다.

실행 예시:

```text
python tools/maintenance_job.py --execute --log results/maintenance/latest.log
```

유지보수 상태는 로컬 `pipeline_controls/maintenance`, 상세 파일은 `results/maintenance/latest.log`, Delta 전후 비교는 lake의 `/data/metrics/maintenance.json`이다. 실패·재개 실패는 관측소에 경고, 다음 예약 시각 30분 초과 미실행은 지연 경고다. 관측소 브라우저가 열린 상태의 알림이며 Slack·메일 발송은 추가하지 않았다.

비정상 호스트 종료로 `results/maintenance.lock`이 남으면 먼저 Spark·임시 maintenance 컨테이너와 실행 작업 유무를 확인한 뒤, 작업이 없을 때만 잠금 파일을 정리한다. 잠금 파일만 무조건 삭제하지 않는다. Kafka 보관 기간 안에 압축·재개가 완료돼야 하며, 평상시 수집 지연이 큰 시간에는 예약을 옮긴다.

## 명시적 실환경 부하·중단 시험

```text
python tools/live_pipeline_check.py --sessions 50 --operations 20 --fault writer-stop --output results/load-writer
python tools/live_pipeline_check.py --sessions 100 --operations 20 --fault spark-restart --output results/load-spark
```

이 도구는 **실제 시험 회원·이벤트를 생성**하고 지정한 writer 또는 Spark를 잠시 멈춘다. 작업 시간에 맞춰 명시적으로 실행한다. 운영 DB·토픽·체크포인트를 삭제하지 않는다. 게이트웨이 키와 원격 Mongo 접속 정보는 기존 컨테이너 설정에서 메모리로 읽으며 출력 파일에 기록하지 않는다. `corpus.json`은 합성 데이터, `result.json`은 요청·중복·최종 저장·지연 증거다.

writer-stop은 적재가 중지된 상태에서 수신과 Outbox 영속 대기를 확인한 뒤 writer를 재개한다. spark-restart는 송신 직후 Spark를 정상 중지·재시작해 기존 체크포인트부터 따라잡는지 본다. 이번 도구는 디스크 손상이나 SIGKILL·브로커/DB 장애를 모사하지 않는다. 같은 이벤트 ID 10%를 다시 보내 최종 저장 건수가 늘지 않는지 확인한다. 요청 재시도도 동일 event_id를 사용한다.

측정값은 이 PC·현재 설정·시험 크기에 대한 결과다. 최대 수용량이나 exactly-once의 모든 장애 상황을 보장하는 시험으로 해석하지 않는다.
