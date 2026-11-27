# -*- coding: utf-8 -*-
"""Pipeline runtime architecture: consolidated current configuration (checked against main 2026-11-27).

    python docs/architecture/pipeline_architecture.py      -> pipeline-architecture-2026-11-25.svg (next to this file)

Standard library only. Edit the boxes / arrows in build() and run again; the PNG is rendered from the SVG with a
headless browser, e.g.
    chrome --headless=new --hide-scrollbars --window-size=2400,1800 --screenshot=out.png file:///.../x.svg
The 2026-11-21 SVG/PNG next to this file is the earlier snapshot that older reports link to; it is kept as is.
"""
from html import escape
from pathlib import Path

W, H = 2400, 1800
OUT = Path(__file__).with_name("pipeline-architecture-2026-11-25.svg")

# palette per layer: (fill, stroke, title color)
C = {
    "game": ("#fdf3e3", "#d08a2c", "#7a4a0c"),
    "ingest": ("#e8f1fb", "#3b78c2", "#1d4d86"),
    "kafka": ("#eef0fb", "#5560b8", "#2d357a"),
    "spark": ("#eaf6ef", "#2f8a57", "#1d5a38"),
    "store": ("#f3eefb", "#7d57b8", "#4c2f7a"),
    "writer": ("#fbeef0", "#b8506a", "#7a2238"),
    "server": ("#e9f6f6", "#2b8a8a", "#145a5a"),
    "ops": ("#f4f5f7", "#7b8494", "#3b4250"),
    "obs": ("#fdf8e8", "#b8941f", "#6b5400"),
    "inner": ("#ffffff", "#b9c3cf", "#2a3442"),
}
# round of fixes that introduced a part; "+" = follow-up changes after the 8th round
TAG = {"3": "#2f8a57", "4": "#3b78c2", "5": "#b8506a", "6": "#c47a12", "7": "#6b4fb8", "8": "#2b8a8a", "+": "#b8941f"}


def tagged(text):
    """'[4] text' or '  [4] text' -> (text, '4') so the round is drawn as a coloured badge."""
    body = text.lstrip(" ")
    if body.startswith("[") and body[2:4] == "] " and body[1] in TAG:
        return text[:len(text) - len(body)] + body[4:], None
    return text, None


def badge(x, y, tag):
    label, w = ("추가", 34) if tag == "+" else (f"{tag}차", 22)
    return (f'<rect x="{x}" y="{y - 12}" width="{w}" height="16" rx="4" fill="{TAG[tag]}"/>'
            f'<text x="{x + w / 2}" y="{y + 1}" font-size="11" font-weight="700" fill="#fff" text-anchor="middle">{label}</text>'), w


def box(x, y, w, h, title, lines=(), kind="inner", size=13.5, title_size=16):
    fill, stroke, tcol = C[kind]
    o = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="{2 if kind != "inner" else 1.2}"/>',
         f'<text x="{x + 12}" y="{y + 24}" font-size="{title_size}" font-weight="700" fill="{tcol}">{escape(title)}</text>']
    ly = y + 24 + title_size + 4
    for raw in lines:
        text, tag = tagged(raw)
        tx = x + 14
        if tag:
            lead = len(text) - len(text.lstrip(" "))
            mark, bw = badge(tx + lead * 4, ly, tag)
            o.append(mark)
            text = text.lstrip(" ")
            tx += lead * 4 + bw + 6
        o.append(f'<text x="{tx}" y="{ly}" font-size="{size}" fill="#2a3442" xml:space="preserve">{escape(text)}</text>')
        ly += size + 6
    return "\n".join(o)


def group(x, y, w, h, title, subtitle, kind):
    fill, stroke, tcol = C[kind]
    o = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2.2"/>',
         f'<text x="{x + 16}" y="{y + 28}" font-size="19" font-weight="700" fill="{tcol}">{escape(title)}</text>']
    if subtitle:
        o.append(f'<text x="{x + 16}" y="{y + 48}" font-size="13" fill="#5b6472">{escape(subtitle)}</text>')
    return "\n".join(o)


ARROW = {"data": "#2f6f4f", "ctrl": "#3b78c2", "fail": "#c0392b", "read": "#2b8a8a"}


def arrow(points, kind="data", label="", lx=None, ly=None):
    col = ARROW[kind]
    dash = {"data": "", "ctrl": ' stroke-dasharray="7 5"', "fail": ' stroke-dasharray="4 4"', "read": ' stroke-dasharray="2 4"'}[kind]
    d = "M" + " L".join(f"{px},{py}" for px, py in points)
    o = [f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2.4"{dash} marker-end="url(#m-{kind})"/>']
    if label:
        if lx is None:
            (x1, y1), (x2, y2) = points[0], points[1]
            lx, ly = (x1 + x2) / 2, (y1 + y2) / 2 - 7
        o.append(f'<text x="{lx}" y="{ly}" font-size="12.5" font-weight="700" fill="{col}" text-anchor="middle" '
                 f'paint-order="stroke" stroke="#ffffff" stroke-width="4">{escape(label)}</text>')
    return "\n".join(o)


def build():
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="\'Malgun Gothic\',\'Apple SD Gothic Neo\',sans-serif">', "<defs>"]
    for k, col in ARROW.items():
        o.append(f'<marker id="m-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
                 f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{col}"/></marker>')
    o.append("</defs>")
    o.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    o.append('<text x="30" y="42" font-size="28" font-weight="800" fill="#1f2430">아키텍처 상세: 코딱지 파이프라인 구성 요소별 설정</text>')
    o.append('<text x="30" y="70" font-size="15" fill="#5b6472">2026-11-27 main 코드 기준 현재 구성 · '
             '실선 = 데이터, 파선 = 기동·상태 확인, 점선 = 화면 조회, 빨간 점선 = 실패 경로</text>')

    # ------------------------------------------------------------------ row 1: game -> collector -> kafka, gates, server
    o.append(box(30, 100, 340, 330, "게임 클라이언트 (Godot)", [
        "학습 이벤트 v2 · UUIDv7 event_id",
        "세션 안 sequence 1, 2, 3 …",
        "[5] 플레이어가 바뀌면 새 세션·run·attempt",
        "디스크 큐 user://telemetry/",
        "  pending/ → 전송 성공 시 삭제",
        "  rejected/ (4xx, 6일 만료)",
        "[5]   corrupt/ (깨진 파일, 사유 보관)",
        "[5] 임시 파일 → 확인 → 교체",
        "401 보관 후 60초 재시도",
        "408·429·5xx·연결 실패 → 재시도",
        "모르는 미니게임 ID는 전송 안 함",
        "[+] config.ini: 수집기·서버 주소, debug_enabled",
    ], kind="game"))
    o.append(box(400, 100, 350, 330, "수집기 collector (FastAPI :8000)", [
        "POST /v2/events (X-API-Key)",
        "  계약 검증 contract.py",
        "[+]   state_before/after 객체 → 정렬 JSON 문자열",
        "  Kafka acks=all 확인 후 202",
        "  검증 실패 → 422 + DLQ 1건",
        "  Kafka 실패(5초) → 503, 재전송",
        "GET /v2/events/{id} 원격 적재 상태",
        "[4] /health/ready = Kafka 수집 준비",
        "      (리더·ISR ≥ 2, Mongo와 무관)",
        "[4] /health/deps = 브로커별·수집·Mongo",
        "uvicorn 2 workers · 멱등 프로듀서",
    ], kind="ingest"))
    o.append(box(830, 100, 400, 330, "Kafka KRaft 3대 (kafka-1·2·3)", [
        "복제 3 · 최소 ISR 2 · 보관 7일",
        "nv.learning.v2  6파티션 (key session_id)",
        "nv.update.v1    3파티션",
        "nv.runtime.v1   3파티션",
        "nv.dlq.v1       3파티션 (422 원문 4KB)",
        "nv.bundle.v2    3파티션 (예약)",
        "브로커 헬스체크: nc -z (생존만)",
        "[4] 준비 판단은 Python 검사가 담당",
        "    브로커 1대 정지: 해당 브로커만 이상,",
        "    수집 준비는 유지 (ISR 2)",
    ], kind="kafka"))
    o.append(box(1270, 100, 470, 330, "기동 순서·상태 확인 common/health.py", [
        "[4] topic-init (Python 이미지)",
        "    AdminClient.create_topics()",
        "    있는 토픽 유지, 5초×36회 재시도,",
        "    리더·ISR 확인까지 통과해야 종료 0",
        "[4] deps-ready (일회성)",
        "    MongoDB ping ok:1 (3초 제한)",
        "    + Kafka 수집 준비 → 종료 0",
        "    → 그 뒤 Spark·원격 작업자 기동",
        "[4] 브로커별 메타데이터 요청,",
        "    응답한 브로커 이름까지 확인",
        "Mongo 헬스체크: /dev/tcp (연결 진단)",
    ], kind="ops"))
    o.append(box(1780, 100, 590, 330, "관리자 서버 Django (/staff/)", [
        "/staff/live 실시간 현황 (3초마다 조회)",
        "  최근 1분 이벤트·5분 세션 + 1분 전 대비 ▲▼",
        "  미니게임 성공률 30분 · 실패 급증 경고",
        "  분석 화면 적재 상태 카드 (outbox 상태)",
        "[3]   거절·격리 이벤트 카드 (PL-8)",
        "[7]   도착 시각 기준 + 늦게 도착 N건 표시",
        "  업데이트 탭: 팩 다운로드·버전 보급률",
        "[+] /staff/pipeline-alerts 파이프라인 알림 현황",
        "/staff/ 전체 현황 · 게임 분석 · 플레이어 · 행동 로그 (플레이 시각 기준)",
        "  원격 대시보드 DB의 세션·시도·이벤트, 참조 없으면 건너뜀",
        "[+]   분석 화면 회원/게스트 필터",
        "회원 MySQL: 계정·클라우드 저장 (게임 로그인 API)",
    ], kind="server"))

    o.append(arrow([(370, 230), (400, 230)], "data", "HTTP", 385, 222))
    o.append(arrow([(750, 200), (830, 200)], "data", "202 전에", 790, 192))
    o.append(arrow([(750, 300), (830, 300)], "fail", "422 → DLQ", 790, 292))
    o.append(arrow([(1270, 210), (1230, 210)], "ctrl", "토픽 생성", 1250, 202))
    o.append(arrow([(1505, 430), (1505, 470)], "ctrl", "기동 허용", 1560, 456))

    # ------------------------------------------------------------------ row 2: spark, delta, local mongo
    o.append(group(30, 470, 1200, 560, "Spark 3.5 + Delta 3.2 (단일 앱, local[4])",
                   "spark/delta_stream.py = 진입점·감독, 처리는 bronze·silver·gold·periodic·sinks·compaction 모듈 · "
                   "실패한 쿼리만 재시작, 10분에 5회 넘으면 컨테이너 재시작", "spark"))
    o.append(box(50, 530, 250, 185, "bronze (5초)", [
        "Kafka 3토픽 → Delta append",
        "원문 그대로 (재전송도 보존)",
        "maxOffsetsPerTrigger 10,000",
        "체크포인트 bronze-v1",
    ]))
    o.append(box(320, 530, 400, 185, "silver_learning / silver_update (1초)", [
        "명시 스키마 · 불완전 행 제외",
        "중복 제거: 상태 저장소 7일 (kafka_ts)",
        "insert-only MERGE: event_id",
        "  + event_date [lo−7일, hi+1일] + v7 ID 범위",
        "[7] ID 생성일별 묶음마다 MERGE (늦은 ID 분리)",
        "→ 원격 outbox 적재 (500건 bulk)",
        "[+] 순서: MERGE → outbox 적재 → 압축",
        "[+] 압축 후보 = 배치가 쓴 모든 날짜",
    ]))
    o.append(box(320, 728, 400, 112, "silver_audit (30초)", [
        "topic:event_id → payload_hash 상태 7일",
        "같은 ID·다른 본문 → id_conflict",
        "JSON·스키마 오류 → invalid_*",
        "→ silver.quarantine (원문 보존)",
    ]))
    o.append(box(740, 530, 470, 185, "gold 쿼리 (1초, 워터마크 2·10분)", [
        "gold_1m: 1분 텀블링 미니게임 시도·성공·실패",
        "[7] gold_alert: 5분 창 1분 이동, 정시 이벤트만",
        "  실패 급증 (시도 20↑·실패율 0.4↑·1.5배↑)",
        "[+]   기준선 = gold.failure_alerts 직전 30분 6개 창",
        "       (현재 창과 같은 정시 규칙·같은 공식)",
        "gold_update: 5분 창 업데이트·팩 다운로드",
        "Delta MERGE (window_start 하한) → rt_* 게시",
        "[+] 순서: MERGE → Mongo 게시 → 압축",
    ]))
    o.append(box(740, 728, 470, 112, "MongoDB 게시 sinks.py", [
        "rt_* _id 교체 upsert, 5회 재시도",
        "[4] 최종 실패 창 → metrics/gold-republish.json",
        "[4] Mongo 복구 후 Gold Delta에서 다시 게시",
        "outbox 실패는 예외 → 배치 재실행",
    ]))
    o.append(box(50, 728, 250, 112, "remote_runtime", [
        "bronze runtime 이벤트",
        "→ 원격 outbox",
        "(REMOTE_EXPORT_ENABLED=1)",
    ]))
    o.append(box(50, 855, 1160, 160, "드라이버 주기 작업 spark/periodic.py (10초 루프)", [
        "[3] rt_summary 10초: 최근 5분만 먼저 걸러 집계 · 늦게 도착 건수 함께 (총계 포함)",
        "[3] 버전 보급률 60초: 같으면 MERGE·재쓰기 생략 · 최신 판단은 플레이 시각 순",
        "[3] rt_rejects 60초 (PL-8): Kafka nv.dlq.v1 24시간 + silver.quarantine → 60분·24시간 건수, 사유, 최근 5건",
        "[4] Gold 재게시 대기분 처리 · 진행 파일 metrics/streaming-progress.json (sink 실패, 재시작, 단계별 시간 → 관측소가 읽음)",
        "[6] Bronze 압축 10분 · VACUUM 6시간 · 로그: 주기 작업마다 소요 시간",
    ]))

    o.append(arrow([(1030, 430), (1030, 452), (16, 452), (16, 600), (50, 600)], "data", "구독 (learning·update·runtime)", 600, 446))
    o.append(arrow([(300, 600), (320, 600)], "data"))
    o.append(arrow([(300, 660), (310, 660), (310, 784), (320, 784)], "data"))
    o.append(arrow([(720, 600), (740, 600)], "data"))
    o.append(arrow([(1190, 715), (1190, 728)], "data"))

    o.append(group(1270, 470, 470, 560, "Delta Lake (볼륨 lake:/data)", "", "store"))
    o.append(box(1290, 510, 430, 330, "테이블", [
        "bronze.game_events (ingest_date)",
        "silver.learning_events (event_date)",
        "silver.update_events (event_date)",
        "silver.quarantine",
        "gold.minigame_1m",
        "gold.failure_alerts (경고 기준선도 여기서)",
        "gold.update_progress_5m",
        "gold.version_adoption",
        "checkpoints/ (쿼리별)",
        "metrics/streaming-progress.json",
        "[4] metrics/gold-republish.json",
    ]))
    o.append(box(1290, 855, 430, 155, "압축·정리 spark/compaction.py", [
        "Delta 자동 압축 끔 (압축은 아래 주기로만)",
        "[6] 쓰기 스레드가 300배치마다 작은 파일만",
        "[+] Silver는 outbox 적재 뒤, Gold는 Mongo 게시 뒤",
        "[6] Bronze 10분 · VACUUM 6시간 (보존 7일)",
        "ZORDER(maintain.py): 스트림 정지 후 수동",
        "같은 배치 안 동기 실행 (별도 작업 분리는 추후 예정)",
    ]))
    o.append(arrow([(1210, 560), (1290, 560)], "data", "MERGE·append", 1250, 552))

    o.append(group(1780, 470, 590, 560, "로컬 MongoDB nodeverse_logs (mongo:7.0)", "", "store"))
    o.append(box(1800, 510, 550, 225, "실시간 집계 rt_*", [
        "rt_summary (10초) · rt_minigame_1m · rt_alerts",
        "rt_updates · rt_versions (60초, 바뀔 때만)",
        "[3] rt_rejects (60초, PL-8)",
        "pipeline_sink_status (원격 작업자 상태)",
        "  [3] 상태별 개수 10초 = 인덱스만 (문서 0건 읽기)",
        "  [3] 사유 상위 10 = 60초",
        "[+] observatory_samples (관측소 표본, 48시간 TTL)",
    ]))
    o.append(box(1800, 750, 550, 260, "원격 적재 대기열·상태", [
        "remote_event_outbox (_id = event_id)",
        "  pending → processing → stored / quarantined",
        "  waiting_context · retrying · parked · blocked",
        "  완료 행 30일 TTL",
        "[+] 인덱스 state, queued_at (관측소 최대 대기)",
        "remote_projection_receipts · remote_session_cursors",
        "remote_sequence_registry · remote_run_contexts",
        "remote_worker_lease (작업자 1개 보장)",
    ]))
    o.append(arrow([(1210, 784), (1252, 784), (1252, 1078), (1758, 1078), (1758, 600), (1800, 600)], "data", "rt_* 게시", 1500, 1094))
    o.append(arrow([(720, 640), (730, 640), (730, 845), (1240, 845), (1240, 1050), (1772, 1050), (1772, 820), (1800, 820)], "data", "outbox 적재", 1500, 1045))
    o.append(arrow([(2075, 470), (2075, 430)], "read", "rt_* · 상태 카드", 2150, 456))

    # ------------------------------------------------------------------ row 3: remote writer, targets, observatory
    o.append(group(30, 1130, 1200, 600, "원격 작업자 remote-writer (remote/worker.py, --profile remote)",
                   "lease 1개 · 200건 묶음 선점 · 세션별 그룹 8스레드 · MySQL 풀 8 · GET_LOCK 1회 · 이벤트당 DB 왕복 약 10회", "writer"))
    o.append(box(50, 1200, 370, 250, "선점 claim_batch", [
        "기한 된 행 200개 후보 조회",
        "[4] claim_id 토큰을 붙여 processing",
        "[4] 토큰이 붙은 행만 다시 읽어 처리",
        "[4] 결과 기록도 토큰이 맞을 때만",
        "   (운영자 park·재선점이 이김)",
        "멈춘 processing → 5분 뒤 pending",
        "   (토큰 제거)",
    ]))
    o.append(box(440, 1200, 390, 250, "처리 process_job", [
        "[4] 원격 원본 archive: 시도마다 확인",
        "[8] 삽입 우선 ensure, 회원 캐시, 세션 묶음 캐시",
        "[+]   회원 캐시 상한 5만 (유지 시간은 설정값)",
        "투영 project(archived=True)",
        "  회원 확인 (MySQL, 확인된 매핑만 생성)",
        "[+]   게스트: REMOTE_ALLOW_GUESTS=1일 때만",
        "        guest:<UUID>·원시 UUID → 게스트 회원",
        "  순번 커서 = 앞 순번까지 처리됐는지",
        "  문제·세션·run·attempt·gameplay_events",
        "[4] 영수증 → 다음 순번 깨우기",
    ]))
    o.append(box(850, 1200, 360, 250, "상태 결정", [
        "stored / quarantined (격리 원본 보존)",
        "[4] 연속 순번인데 고칠 수 없는 누락",
        "    (attempt_id 없음 등) → 격리",
        "waiting_context: 앞 순번 10분,",
        "  회원 매핑 24시간 → parked",
        "retrying: 2~60초, 20회 → parked",
        "[4] requeue 때 retry_base로 새 예산",
        "blocked: 데이터 충돌 (즉시 정지)",
        "[+] 잘못된 guest UUID·영 UUID → 격리",
    ]))
    o.append(box(50, 1465, 560, 245, "보조 스레드", [
        "heartbeat 10초: lease 연장",
        "metrics 5초: 바뀐 rt_* 만 대시보드 DB로 복사",
        "[3] status 10초: 상태 개수(인덱스) → pipeline_sink_status",
        "     (로컬·대시보드 DB 둘 다), 사유는 60초",
        "revive 60초: 회원 추가·매핑 파일 변경 시",
        "     member_mapping_required 보관 행 재개",
        "parked 순번 빈칸은 앞 순번 저장 즉시 재개",
    ]))
    o.append(box(630, 1465, 580, 245, "운영 도구", [
        "python -m remote.requeue status | requeue | park",
        "[3] python -m tools.dlq_peek --minutes 60 [--raw]",
        "[4] python -m common.health report | wait | topics",
        "[+] tools/recover_state_dlq.py: 계획 → --execute",
        "python spark/maintain.py --execute (ZORDER)",
        "[5] tools/dummy_data.py --reverse-sessions N",
        "probe_latency.py: 수집→화면 지연 (15초 기준)",
        "[+] python -m observatory.setup_indexes --execute",
        "[+] tools/check_runtime_source.py: 실행 코드 = 저장소 확인",
    ], kind="ops"))
    o.append(arrow([(420, 1310), (440, 1310)], "data"))
    o.append(arrow([(830, 1310), (850, 1310)], "data"))
    o.append(arrow([(2075, 1010), (2075, 1110), (18, 1110), (18, 1300), (50, 1300)], "data", "기한 된 행 선점", 900, 1104))

    o.append(box(1270, 1130, 470, 200, "원격 MySQL (회원)", [
        "game_members (member_id, external_member_key)",
        "확인된 매핑(verified)만 회원 생성",
        "[+] 게스트 키 game:member:guest:<UUID>",
        "data_source = live 만 적재",
        "GET_LOCK: 다른 적재 도구와 동시 쓰기 방지",
        "DBUtils PooledDB 8 연결",
    ], kind="store"))
    o.append(box(1270, 1350, 470, 380, "대시보드 MongoDB (원격)", [
        "원본 보관 pipeline_learning_events",
        "  pipeline_update_events · pipeline_runtime_events",
        "분석 관계 game_problems · game_sessions",
        "  problem_runs · solution_attempts",
        "  gameplay_events (event_id 기준 1건)",
        "격리 pipeline_quarantined_events (원본+사유)",
        "rt_* 사본 (metrics 스레드)",
        "pipeline_sink_status (적재 상태)",
        "모든 쓰기 ensure(): 있으면 같은 내용인지만",
        "  확인, 다르면 충돌 (덮어쓰기 없음)",
    ], kind="store"))
    o.append(arrow([(635, 1200), (635, 1190), (1250, 1190), (1250, 1230), (1270, 1230)], "data", "회원 확인 (MySQL 풀)", 1000, 1184))
    o.append(arrow([(1210, 1400), (1270, 1400)], "data", "기록", 1240, 1393))
    o.append(arrow([(1505, 1730), (1505, 1758), (2388, 1758), (2388, 265), (2370, 265)], "read", "분석 화면 조회 (세션·시도·이벤트)", 1950, 1752))

    o.append(box(1800, 1130, 570, 580, "관측소 observatory (FastAPI :8011, --profile observatory)", [
        "[+] 읽기 전용 · 업무 데이터를 바꾸는 API 없음",
        "10초마다 표본 → 메모리 스냅샷 → HTTP API → 브라우저",
        "  Spark 진행 파일 (lake 볼륨 읽기 전용 마운트)",
        "  로컬 Mongo: pipeline_sink_status, 상태별 최고 대기",
        "  수집기 /health/ready (30초) · Kafka 소비 지연",
        "  원격 Mongo ping (연결 확인, 저장 증명 아님)",
        "화면",
        "  쿼리별 입력·처리 속도, 최근 배치 시간, 상태 키",
        "  적재 상태별 건수 (pending … stored)",
        "[+]   최대 대기(queued_at) · 예정 시각 초과 ·",
        "        다음 예약 재시도를 따로, 확인 실패는 미확인",
        "  15분 · 1시간 · 6시간 추이, 일시 정지",
        "알림 센터",
        "  경고·복구 이력, 팝업·소리·브라우저 알림",
        "  확인·숨김 상태는 이 브라우저 localStorage",
        "  /api/attention: 조건 대기·parked·blocked·격리",
        "     표본 20건 (참조값은 SHA-256 지문)",
        "  /api/recent: 최근 원격 적재",
        "표본 이력 observatory_samples 48시간 TTL",
        "LAN 바인딩은 OBSERVATORY_KEY 필수 (없으면 시작 안 함)",
    ], kind="obs"))
    o.append(arrow([(2300, 1030), (2300, 1130)], "read", "지표 조회", 2340, 1122))

    o.append("</svg>")
    return "\n".join(o)


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print("wrote", OUT)
