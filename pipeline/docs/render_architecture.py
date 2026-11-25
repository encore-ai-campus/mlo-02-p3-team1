# -*- coding: utf-8 -*-
"""Pipeline overview figure (3200x1800) in the style of the implementation-report PDFs.

    python docs/render_architecture.py        -> docs/architecture.svg (run from pipeline/)

Standard library only. Render the PNG with a headless browser, e.g.
    chrome --headless=new --hide-scrollbars --window-size=3200,1800 --screenshot=docs/architecture.png file:///.../architecture.svg
The detailed runtime figure (every query, state and round of fixes) is docs/architecture/pipeline_architecture.py
at the repository root.
"""
from html import escape
from pathlib import Path

W, H = 3200, 1800
OUT = Path(__file__).with_name("architecture.svg")
SANS = "'Noto Sans KR','Malgun Gothic',sans-serif"
MONO = "'Consolas','D2Coding','Noto Sans KR',monospace"
BG, PANEL, INK, MUTED = "#f7f5f0", "#efebe3", "#2b2b2b", "#6b665e"
ORANGE, ORANGE_FILL = "#c8643c", "#f6e3db"
TEAL, TEAL_FILL = "#3a8a6a", "#e3f0ea"
TAN = "#b8892e"
KIND = {  # fill, stroke, dash
    "plain": ("#ffffff", INK, ""),
    "built": (ORANGE_FILL, ORANGE, ""),
    "gold": (TEAL_FILL, TEAL, ""),
    "tool": ("#fbf8f1", TAN, ' stroke-dasharray="12 8"'),
}


def t(x, y, s, size=24, color=INK, weight=400, mono=False, anchor="start"):
    fam = MONO if mono else SANS
    return (f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" font-weight="{weight}" fill="{color}" '
            f'text-anchor="{anchor}" xml:space="preserve">{escape(s)}</text>')


def panel(x, w, title):
    return (f'<rect x="{x}" y="40" width="{w}" height="1720" rx="26" fill="{PANEL}"/>'
            + t(x + 30, 100, title, 32, MUTED, 700))


def box(x, y, w, h, title="", lines=(), kind="plain", title_size=30, size=23, title_color=None, mono_title=False):
    """lines: plain text; '`text' = monospace; '#text' = bold; '-' = divider; '' = half gap."""
    fill, stroke, dash = KIND[kind]
    o = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{fill}" stroke="{stroke}" stroke-width="3"{dash}/>']
    ly = y + 22
    if title:
        ly += title_size + 6
        o.append(t(x + 26, ly, title, title_size, title_color or INK, 700, mono_title))
        ly += 12
    for line in lines:
        if line == "":
            ly += size // 2
            continue
        if line == "-":
            ly += 14
            o.append(f'<line x1="{x + 26}" y1="{ly}" x2="{x + w - 26}" y2="{ly}" stroke="#d9c9bd" stroke-width="2"/>')
            ly += 8
            continue
        ly += size + 9
        if line.startswith("`"):
            o.append(t(x + 26, ly, line[1:], size - 1, INK, 400, True))
        elif line.startswith("#"):
            o.append(t(x + 26, ly, line[1:], size, INK, 700))
        else:
            o.append(t(x + 26, ly, line, size))
    return "".join(o)


def sub(x, y, w, h, name, lines, kind="plain", size=22):
    """Small table / topic box: monospace name + description lines."""
    fill, stroke, dash = KIND[kind]
    o = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2.5"{dash}/>',
         t(x + 22, y + 38, name, size, INK, 700, True)]
    for i, line in enumerate(lines):
        o.append(t(x + 22, y + 72 + i * 30, line, size - 1))
    return "".join(o)


def arrow(points, color=INK, dash=False, label="", lx=None, ly=None, curve=False):
    mid = {INK: "k", ORANGE: "o", TAN: "t", TEAL: "g"}[color]
    if curve and len(points) == 2:
        (x1, y1), (x2, y2) = points
        cx = (x1 + x2) / 2
        d = f"M{x1},{y1} C{cx},{y1} {cx},{y2} {x2},{y2}"
    else:
        d = "M" + " L".join(f"{px},{py}" for px, py in points)
    da = ' stroke-dasharray="12 8"' if dash else ""
    o = f'<path d="{d}" fill="none" stroke="{color}" stroke-width="3"{da} marker-end="url(#a{mid})"/>'
    if label:
        o += (f'<text x="{lx}" y="{ly}" font-family="{SANS}" font-size="21" font-weight="700" fill="{color}" '
              f'text-anchor="middle" paint-order="stroke" stroke="{BG}" stroke-width="6">{escape(label)}</text>')
    return o


def build():
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><defs>']
    for k, c in (("k", INK), ("o", ORANGE), ("t", TAN), ("g", TEAL)):
        o.append(f'<marker id="a{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
                 f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>')
    o.append(f'</defs><rect width="{W}" height="{H}" fill="{BG}"/>')

    o.append(panel(40, 470, "① 이벤트 발생"))
    o.append(panel(540, 470, "② 수집 API"))
    o.append(panel(1040, 470, "③ Kafka 브로커 3대"))
    o.append(panel(1540, 1100, "④ Spark → Delta Lake (/data/delta)"))
    o.append(panel(2670, 490, "⑤ 저장 · 서빙"))

    # ① sources
    o.append(box(70, 150, 410, 230, "Godot 게임 EXE", [
        "학습 8종 · 업데이트 9종", "schema_version 2 · UUIDv7", "디스크 큐 → 응답별 재시도",
        "config.ini로 수집기 주소"]))
    o.append(box(70, 410, 410, 200, "launcher.exe", [
        "run_* / exit_* 이벤트", "SQLite 큐 → /v1/events", "NODEVERSE_PLAYER_ID 전달"]))
    o.append(box(70, 640, 410, 170, "simulator.py", [
        "점검 · 스모크 · 부하", "tools/dummy_data.py"], kind="tool"))

    # ② collector
    o.append(box(570, 150, 410, 700, "collector.py", [
        "FastAPI · X-API-Key", "",
        "`POST /v2/events", "단일 이벤트, 토픽으로 분류",
        "`POST /v1/events", "런처 실행 이벤트", "-",
        "extra=forbid · details 허용 키", "state 객체 → JSON 문자열",
        "UTC 밀리초 · 6일 초과 거절", "received_at · 본문 해시 부착", "",
        "#202 = Kafka acks=all 접수", "#422 = 거부 + DLQ 1건", "#503 = 같은 ID·본문 재전송", "",
        "/health/ready · /health/deps",
    ], kind="built"))

    # ③ topics
    topics = [("nv.learning.v2", "학습 · 키 session_id · 6P"), ("nv.update.v1", "업데이트 · 키 player_id · 3P"),
              ("nv.runtime.v1", "실행·종료 · 키 run_id · 3P"), ("nv.dlq.v1", "거부 원문·사유 · 3P")]
    for i, (name, desc) in enumerate(topics):
        o.append(sub(1070, 150 + i * 150, 410, 120, name, [desc]))
    o.append(sub(1070, 750, 410, 100, "nv.bundle.v2", ["예약 (생산·소비 없음)"], kind="tool"))
    o.append(t(1075, 905, "KRaft 3대 · 복제 3 · min ISR 2", 23, INK))
    o.append(t(1075, 940, "보관 7일 · 자동 생성 끔 (topic-init)", 23, INK))
    o.append(t(1075, 975, "기동 관문: health.py (deps-ready)", 23, INK))

    # ④ spark
    o.append(box(1570, 150, 520, 200, "", [], kind="built"))
    o.append(t(1596, 192, "BRONZE · append · 5초", 24, ORANGE, 700))
    o.append(t(1596, 232, "bronze.game_events", 23, INK, 700, True))
    o.append(t(1596, 268, "value · topic · partition · offset", 22))
    o.append(t(1596, 300, "kafka_ts · ingest_date(파티션)", 22))
    o.append(t(1596, 332, "체크포인트 /data/checkpoints", 22))

    o.append(box(1570, 410, 520, 440, "", [], kind="built"))
    o.append(t(1596, 452, "SILVER · 중복 제거 + MERGE · 1초", 24, ORANGE, 700))
    for i, line in enumerate(["event_id 상태 저장소 7일 → insert-only MERGE",
                              "날짜 7일 + v7 ID 범위, ID 생성일별 묶음",
                              "MERGE → outbox 적재 → 작은 파일 압축",
                              "감사 스트림 30초: 해시 충돌 격리"]):
        o.append(t(1596, 492 + i * 32, line, 22))
    for i, (name, desc) in enumerate([("silver.learning_events", ""), ("silver.update_events", ""),
                                      ("silver.quarantine", "invalid_json · invalid_schema · id_conflict")]):
        h = 62 if not desc else 92
        y = 630 + i * 72
        o.append(sub(1596, y, 470, h, name, [desc] if desc else [], size=21))

    o.append(box(2120, 150, 490, 700, "", [], kind="gold"))
    o.append(t(2146, 192, "GOLD · 워터마크 · update 모드", 24, TEAL, 700))
    golds = [("gold.minigame_1m", ["1분 창 · 게임별 시도·성공·실패", "힌트·플레이어 · 워터마크 2분"]),
             ("gold.failure_alerts", ["5분 창 1분 간격 · 정시 이벤트만", "≥20회·≥0.4·직전30분×1.5 (같은 규칙)"]),
             ("gold.update_progress_5m", ["5분 창 · 팩 성공/실패 · p50", "최다 실패 사유 · 워터마크 10분"]),
             ("gold.version_adoption", ["최근 24시간 설치별 마지막 버전", "60초마다 배치 · 바뀔 때만 쓰기"])]
    for i, (name, lines) in enumerate(golds):
        o.append(sub(2146, 215 + i * 132, 440, 118, name, lines, size=21))
    o.append(t(2146, 790, "MERGE → Mongo 게시 → 압축", 22))
    o.append(t(2146, 822, "게시 실패 창은 Gold에서 다시 게시", 22))

    o.append(box(1570, 880, 1040, 190, "", [], kind="built"))
    o.append(t(1596, 922, "DRIVER · 감독 · 주기 작업", 24, ORANGE, 700))
    for i, line in enumerate(["delta_stream.py 진입점 → bronze·silver·gold·periodic·sinks·compaction 모듈",
                              "실패한 쿼리만 체크포인트부터 재시작 (10분 5회 넘으면 컨테이너 재시작)",
                              "rt_summary 10초 · rt_versions·rt_rejects 60초 · Bronze 압축 10분 · VACUUM 6시간"]):
        o.append(t(1596, 962 + i * 32, line, 22))

    # ⑤ serving
    o.append(box(2700, 150, 430, 500, "MongoDB", [
        "nodeverse_logs (로컬)", "",
        "`rt_minigame_1m", "`rt_alerts · rt_updates", "`rt_versions · rt_summary", "`rt_rejects", "",
        "`remote_event_outbox", "`pipeline_sink_status", "",
        "_id upsert · 쓰는 쪽 = Spark"], kind="built"))
    o.append(box(2700, 690, 430, 190, "서버 (Django)", [
        "실시간 현황 · 알림 현황", "분석 화면 (회원/게스트)", "읽기 전용"]))
    o.append(box(2700, 1110, 430, 610, "원격 DB", [
        "#MySQL", "`game_members", "회원 · 게스트 키", "", "#대시보드 MongoDB",
        "`pipeline_*_events", "`game_sessions", "`problem_runs", "`solution_attempts", "`gameplay_events",
        "`rt_* 사본"], kind="built"))

    # bottom row
    o.append(box(70, 1110, 410, 610, "범례", [], kind="plain"))
    o.append(arrow([(100, 1210), (180, 1210)]) + t(200, 1218, "이벤트 흐름", 23))
    o.append(arrow([(100, 1265), (180, 1265)], ORANGE) + t(200, 1273, "Spark 스트림", 23))
    o.append(arrow([(100, 1320), (180, 1320)], TEAL) + t(200, 1328, "원격 적재", 23))
    o.append(arrow([(100, 1375), (180, 1375)], TAN, dash=True) + t(200, 1383, "시험·검증용", 23))
    o.append(f'<rect x="100" y="1410" width="70" height="40" rx="8" fill="{ORANGE_FILL}" stroke="{ORANGE}" stroke-width="3"/>'
             + t(190, 1440, "구현된 처리 단계", 23))
    o.append(f'<rect x="100" y="1470" width="70" height="40" rx="8" fill="#fbf8f1" stroke="{TAN}" stroke-width="3" stroke-dasharray="10 7"/>'
             + t(190, 1500, "예약 · 도구", 23))
    o.append(t(100, 1570, "P = 파티션 수", 23))
    o.append(t(100, 1610, "기준: 현재 저장소 코드", 23))
    o.append(t(100, 1645, "(2026-11-25)", 23))

    o.append(box(570, 1110, 910, 300, "재처리 안전성 (정확히 한 번처럼 보이게)", [
        "1. 202는 Kafka 3대 중 2대 이상 기록된 뒤에만 응답",
        "2. Bronze: Kafka 오프셋을 Delta 체크포인트와 함께 커밋",
        "3. Silver: 상태 저장소 중복 제거 + insert-only MERGE",
        "4. Gold: 창 단위 키 MERGE · MongoDB: _id 교체 upsert",
        "5. 원격 적재: ensure() — 같은 내용만 통과, 다르면 충돌",
    ], size=22, title_size=27))
    o.append(box(570, 1440, 910, 280, "원격 적재 remote-writer (--profile remote)", [
        "outbox 200건 묶음 선점 · 세션별 8스레드 · MySQL 풀 8",
        "세션 안 sequence 순서대로 → 세션·문제·시도·행동 로그",
        "회원 확인 · 게스트(REMOTE_ALLOW_GUESTS=1) · 앞 순번 대기",
        "waiting_context → parked · retrying · blocked · quarantined",
    ], size=22, title_size=27))
    o.append(box(1570, 1110, 1040, 280, "관측소 observatory (:8011, --profile observatory)", [
        "읽기 전용: Spark 진행 파일 · 로컬 Mongo 상태 · 수집기 준비 · Kafka 지연 · 원격 ping",
        "쿼리별 처리 속도·배치 시간 · 적재 상태별 건수 · 최대 대기 · 15분~6시간 추이",
        "알림 센터: 경고·복구 이력, 팝업·소리·브라우저 알림, 점검 대상 표본",
        "LAN에서 열 때는 OBSERVATORY_KEY 필수",
    ], size=22, title_size=27))
    o.append(box(1570, 1420, 1040, 245, "검증 도구 (spark 컨테이너·로컬에서 실행)", [], kind="tool", title_size=27))
    tools = [("verify.py counts · lag", "Bronze=Kafka · Silver 중복 0 · Gold=Silver"),
             ("verify.py history · timetravel", "DESCRIBE HISTORY · VERSION AS OF"),
             ("probe_latency.py", "이벤트 → rt_minigame_1m 초 단위"),
             ("simulator.py checks · load", "202 · 422+DLQ · 중복 · 충돌 · p95")]
    for i, (cmd, desc) in enumerate(tools):
        o.append(t(1596, 1515 + i * 36, cmd, 21, INK, 400, True))
        o.append(t(2050, 1515 + i * 36, desc, 21))

    # arrows: sources -> collector -> topics
    o.append(arrow([(480, 265), (570, 265)]))
    o.append(arrow([(480, 510), (570, 510)]))
    o.append(arrow([(480, 725), (570, 725)], TAN, dash=True))
    o.append(arrow([(980, 330), (1070, 210)], curve=True))
    o.append(arrow([(980, 380), (1070, 360)], curve=True))
    o.append(arrow([(980, 470), (1070, 510)], curve=True))
    o.append(arrow([(980, 690), (1070, 660)], curve=True))
    # topics -> bronze
    for y in (210, 360, 510):
        o.append(f'<path d="M1480,{y} L1520,{y}" stroke="{ORANGE}" stroke-width="3" fill="none"/>')
    o.append(f'<path d="M1520,210 L1520,510" stroke="{ORANGE}" stroke-width="3" fill="none"/>')
    o.append(arrow([(1520, 250), (1570, 250)], ORANGE))
    # bronze -> silver -> gold -> mongo
    o.append(arrow([(1830, 350), (1830, 410)], ORANGE))
    o.append(arrow([(2066, 661), (2100, 661), (2100, 274), (2146, 274)], ORANGE))
    o.append(arrow([(2100, 406), (2146, 406)], ORANGE))
    o.append(arrow([(2066, 733), (2110, 733), (2110, 538), (2146, 538)], ORANGE))
    o.append(arrow([(2110, 670), (2146, 670)], ORANGE))
    o.append(arrow([(2610, 300), (2700, 300)], ORANGE, label="rt_*", lx=2655, ly=288))
    o.append(arrow([(2078, 850), (2078, 866), (2645, 866), (2645, 560), (2700, 560)], ORANGE, label="outbox 적재", lx=2380, ly=874))
    o.append(arrow([(2915, 650), (2915, 690)]))
    # remote writer
    o.append(arrow([(2700, 630), (2664, 630), (2664, 1090), (1520, 1090), (1520, 1580), (1480, 1580)], TEAL,
                   label="기한 된 행 선점", lx=2100, ly=1082))
    o.append(arrow([(1480, 1700), (2700, 1700)], TEAL, label="세션·시도·이벤트 적재", lx=2100, ly=1692))
    o.append(arrow([(2915, 1110), (2915, 880)], TEAL, label="분석 화면 조회", lx=3030, ly=1000))
    o.append("</svg>")
    return "".join(o)


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print("wrote", OUT)
