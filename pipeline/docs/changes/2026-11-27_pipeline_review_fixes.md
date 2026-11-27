# 2026-11-27 파이프라인 리뷰 수정

## 원격 복원 후 거짓 성공 방지

원격 MongoDB만 과거 시점으로 복원하면 로컬 receipt·cursor가 실제 대시보드 자료보다 앞설 수 있다. 이전에는 같은 이벤트를 재처리해도 원본 archive만 복구하고 receipt를 그대로 성공 반환했다.

이제 처리 이력을 재사용하기 전에 원격 이벤트의 hash·run/session/attempt 연결, 회원 연결, 실행의 문제 정의 존재를 확인한다. 격리 이력도 원격 격리 문서의 hash·사유가 일치해야 재사용한다. 다음 순번의 새 이벤트 역시 로컬 context만 남은 경우 자식 기록을 만들기 전에 원격 부모 존재를 검사한다.

자료가 없거나 참조가 다르면 `remote_projection_recovery_required` Conflict로 Outbox를 **blocked** 처리한다. 원격 연결 장애는 일반 예외 재시도 경로를 그대로 사용한다. 정상 재전송은 기존처럼 중복 문서를 만들지 않는다.

이 변경은 **실제 재처리하는 행**의 거짓 성공을 막는다. 과거 stored 행 전체의 주기적 대조·원격 복원 세대 자동 감지·자동 재구축은 구현하지 않았다. DB를 복원해도 자동으로 복구됐다고 해석하면 안 된다.

복구 시 운영 순서:

1. 수집은 Kafka 보관 기간·용량을 확인하며 유지할 수 있지만, 복구에 관계된 remote-writer와 Spark 쓰기는 중지한다.
2. 원격 MySQL·MongoDB, 로컬 MongoDB의 outbox·sequence registry·cursor·receipt·run context, Delta·checkpoint를 먼저 백업한다.
3. 원격 DB와 로컬 투영 상태의 일치 시점을 확인하고, 같은 시점의 백업으로 복구하거나 별도 환경에서 전체 원본을 순서대로 재구축한다. 회원 UUID와 문제 정의 UUID를 유지한다. 로컬 receipt만 임의 삭제하거나 운영 대상에 무작정 재전송하지 않는다.
4. 복구한 자료의 회원·문제·실행·시도·이벤트 참조 및 중복 수를 검증한 후 차단 행을 범위를 제한해 requeue한다. 재처리 성공 후 writer와 Spark를 정상 재개한다.

## 압축 실행 분리

기본값은 `COMPACTION_MODE=maintenance`다. 기존 COMPACT_EVERY_BATCHES=300 설정이 남아 있어도 이 모드에서는 Silver·Gold foreachBatch와 Bronze 주기 타이머가 OPTIMIZE를 실행하지 않는다. VACUUM 보존 기간·주기 및 중복 제거 TTL은 바꾸지 않았다.

압축은 기존 `spark/maintain.py`를 별도 프로세스로 실행한다. Gold 4개 테이블도 계획·실행 대상으로 추가했다. Bronze/Silver는 날짜 조건과 ZORDER를 지원하고, 날짜 파티션이 없는 Gold는 전체 OPTIMIZE만 지원한다. Gold에 --date를 주면 오류로 중단한다.

예시(컨테이너 내부 경로 기준):

```text
python3 /app/maintain.py --table silver.learning_events --date 2026-11-27
python3 /app/maintain.py --table gold.minigame_1m gold.failure_alerts
```

위 명령은 계획만 출력한다. 실제 작업은 **정상 Spark writer 컨테이너를 먼저 중지하고**, 같은 lake 볼륨을 연결한 별도 Spark 유지보수 컨테이너에서 기존 Delta 패키지·설정을 사용해 spark-submit으로 실행한다. `--execute`가 있어야 변경한다. 실행 도구가 다른 writer의 중지를 자동 보장하지는 않는다. 실행 전후 행 수·파일 수를 비교한 뒤 기존 체크포인트로 스트리밍을 재개한다.

기존 동작이 꼭 필요한 경우에만 `COMPACTION_MODE=inline`을 명시한다. 이 모드는 다음 스트리밍 배치를 지연시킬 수 있다. 별도 작업 자동 예약이나 무중단 동시 OPTIMIZE 스케줄러는 이번 범위에 포함하지 않았다. 유지보수를 장기간 생략하면 작은 파일이 쌓일 수 있으므로 운영 일정이 필요하다.

## 적용 및 검증

- 새 코드는 writer 이미지 재빌드·재생성과 Spark 재시작 후 로드된다. bind mount 파일이 바뀌어도 실행 중인 Python 프로세스가 이미 읽은 모듈은 자동 교체되지 않는다.
- 설정 기본값, 잘못된 모드 거절, inline 호환, Gold 유지보수 계획 검증을 추가했다.
- 원격 부모·이벤트의 부분 유실 및 격리 문서 유실, 새 자식 쓰기 방지, worker blocked 상태를 회귀 시험으로 추가했다.
- 운영 원격 DB를 초기화하거나 테스트를 위해 삭제하지 않았다. gzip·오프라인 기능의 활성화 여부는 변경하지 않았다.
- 최종 검증: pytest 157 passed, 2 skipped. 로컬 및 현재 Spark 컨테이너에서 Gold 계획 출력(execute=false)을 확인했다. 이번 작업에서는 운영 OPTIMIZE 실행이나 운영 프로세스 재배포를 하지 않았다.
