"""Administrator reading model of the 24 games in the 2026-11-10 report.

Only exact execution IDs (case insensitive) classify records. Never infer an ID
from a title, legacy topic, or an operation. No ingestion/storage contract changes.
"""
from collections import Counter
from .learning import is_retry_run, is_replay_run

AREAS = [('structures', '자료구조'), ('algorithms', '알고리즘'), ('sql', 'SQL'), ('data', '데이터 탐색')]
GAMES = [
    ('ST01', 'structures', '순서가 있는 보관소', '배열', '인덱스 조회와 삽입·삭제'),
    ('ST02', 'structures', '끊어진 운송로', '연결 리스트', '노드와 포인터 연결'),
    ('ST03', 'structures', '최근 작업 복구실', '스택', 'LIFO · Push / Pop / Peek'),
    ('ST04', 'structures', '접수 순서 안내소', '큐 / 덱', 'FIFO · 원형 큐 · 양쪽 끝 연산'),
    ('ST05', 'structures', '이름으로 찾는 물품대장', '해시 테이블', '체이닝과 선형 탐사'),
    ('DS09', 'structures', '가지 잇는 나무', '트리 구조', '부모·자식·루트·리프 연결'),
    ('ST07', 'structures', '갈림길 창고', '이진 탐색 트리', 'BST의 탐색·삽입 규칙'),
    ('ST08', 'structures', '긴급 작업 배정실', '힙 · 우선순위 큐', '최소 힙의 삽입·꺼내기'),
    ('DS10', 'structures', '연결망 건설소', '그래프 구조', '정점·간선·방향·가중치'),
    ('ST10', 'structures', '학습 지원 센터', '자료구조 종합', '상황에 맞는 자료구조 선택'),
    ('ALG02', 'algorithms', '물건 찾기 비교실', '탐색', '선형·이진 탐색'),
    ('ALG01', 'algorithms', '순서 맞춤 작업대', '기초 정렬', '버블·선택·삽입 정렬'),
    ('ALG03', 'algorithms', '나누고 합치는 공방', '분할 정복 정렬', '병합 정렬과 퀵 정렬'),
    ('ST06', 'algorithms', '계층형 자료실', '트리 순회', '전위·중위·후위·레벨 순회'),
    ('ST09', 'algorithms', '연결망 조사실', '그래프 탐색', 'BFS / DFS'),
    ('ALG04', 'algorithms', '최소 비용 배달소', '최단 경로', '다익스트라와 경로 복원'),
    ('SQL01', 'sql', '필요한 칸만 꺼내기', '조회와 필터', 'SELECT · WHERE · ORDER BY · LIMIT'),
    ('SQL02', 'sql', '같은 값은 같은 색으로', '그룹과 집계', 'GROUP BY · HAVING · 집계 함수'),
    ('SQL03', 'sql', '번호가 같은 서랍끼리 연결', '테이블 결합', 'INNER JOIN · LEFT JOIN'),
    ('SQL04', 'sql', '계산한 값으로 다시 칠하기', '집계 기반 조건', '평균·최댓값 토큰으로 조건 만들기'),
    ('DATA02', 'data', '관측 준비실', '데이터 관측', '행·열·자료형·결측 비율'),
    ('DATA01', 'data', '기록 수리 공방', '데이터 정제', '결측·중복·형식 정리'),
    ('DATA03', 'data', '대표값 실험실', '기술 통계', '평균·중앙값·범위와 이상치'),
    ('DATA04', 'data', '차트 관측소', '데이터 시각화', '막대·선·산점도와 결론'),
]
# 사람에게 보여 줄 분류 태그 (게임 learning_catalog.gd 의 기획 ID 와 같다: 메뉴 카드와 게임 안 제목에 나오는 값).
# 화면 표시에만 쓴다. 저장·집계·필터·내보내기의 키는 계속 실행 ID(code)다.
TAGS = {
    'ST01': 'DS-01', 'ST02': 'DS-02', 'ST03': 'DS-03', 'ST04': 'DS-04', 'ST05': 'DS-05',
    'DS09': 'DS-06', 'ST07': 'DS-07', 'ST08': 'DS-08', 'DS10': 'DS-09', 'ST10': '보너스',
    'ALG02': 'AL-01', 'ALG01': 'AL-02', 'ALG03': 'AL-03', 'ST06': 'AL-04', 'ST09': 'AL-05', 'ALG04': 'AL-06',
    'SQL01': 'SQ-01', 'SQL02': 'SQ-02', 'SQL03': 'SQ-03', 'SQL04': 'SQ-04',
    'DATA02': 'DA-01', 'DATA01': 'DA-02', 'DATA03': 'DA-03', 'DATA04': 'DA-04',
}
CATALOG = {code: dict(code=code, tag=TAGS[code], area=area, title=title, concept=concept, goal=goal)
           for code, area, title, concept, goal in GAMES}


def tag_for(code):
    """화면용 태그. 목록에 없는 ID 는 그대로 보여 준다 (추측해서 바꾸지 않는다)."""
    return TAGS.get(str(code).upper(), code)


def game_for(task_id):
    return CATALOG.get(str(task_id).upper())


def area_for(task_id):
    game = game_for(task_id)
    return game['area'] if game else 'unmapped'


def selected_codes(filters):
    return [code for code, game in CATALOG.items()
            if (not filters.get('category') or game['area'] == filters['category'])
            and (not filters.get('game_id') or code == filters['game_id'])]


def report(runs, events):
    """All counts use the selected started-run cohort, including its later events."""
    buckets = {code: [] for code in CATALOG}
    unknown = []
    for run in runs:
        game = game_for(run.task.task_id)
        (buckets[game['code']] if game else unknown).append(run)

    def metrics(items):
        states = Counter(r.status for r in items)
        actions = [e for r in items for e in r.events.all()]
        kinds = Counter(e.event_type for e in actions)
        times = [r.active_ms / 1000 for r in items if r.status == 'completed' and r.active_ms is not None]
        operations = kinds['operation_succeeded'] + kinds['operation_failed']
        return dict(runs=len(items), completed=states['completed'], abandoned=states['abandoned'],
                    in_progress=states['in_progress'], players=len({r.session.player_id for r in items}),
                    completion_rate=round(100 * states['completed'] / len(items), 1) if items else None,
                    avg_seconds=round(sum(times) / len(times), 1) if times else None,
                    timed_completed=len(times), retries=sum(is_retry_run(list(r.attempts.all()), list(r.events.all())) for r in items),
                    hints=kinds['hint'], failures=kinds['operation_failed'],
                    operation_rate=round(100 * kinds['operation_succeeded'] / operations, 1) if operations else None)

    def game_metrics(items):
        # Per game only (not per area): 오답률 from operation events, 다시 하기 runs. retries stays = 재시작.
        actions = [e.event_type for r in items for e in r.events.all()]
        wrong, ops = actions.count('operation_failed'), actions.count('operation_failed') + actions.count('operation_succeeded')
        return dict(wrong_ops=wrong, ops=ops, wrong_rate=round(100 * wrong / ops, 1) if ops else None,
                    replays=sum(is_replay_run(r, list(r.attempts.all()), list(r.events.all())) for r in items))

    games = [{**game, **metrics(buckets[code]), **game_metrics(buckets[code])} for code, game in CATALOG.items()]
    areas = []
    for key, label in AREAS:
        group = [g for g in games if g['area'] == key]
        items = [r for g in group for r in buckets[g['code']]]
        areas.append(dict(key=key, label=label, registered=len(group), observed=sum(g['runs'] > 0 for g in group),
                          **metrics(items)))
    unknown_ids = Counter(r.task.task_id for r in unknown)
    all_metrics = metrics(list(runs))
    return dict(registered=len(games), observed=sum(g['runs'] > 0 for g in games), areas=areas, games=games,
                unmapped=metrics(unknown), unmapped_ids=[dict(task_id=k, runs=n) for k, n in unknown_ids.items()],
                totals=all_metrics, missing_active=all_metrics['completed'] - all_metrics['timed_completed'],
                window_events=events.count())


# Common contract v2 category codes -> server areas. The screen classifies by
# minigame_id (catalog), never by the incoming category: ST06/ST09 are prefixed
# like structures but belong to algorithms.
CATEGORY_AREAS = {'DS': 'structures', 'ALGO': 'algorithms', 'SQL': 'sql', 'DATA': 'data'}
AREA_LABELS = dict(AREAS)


def classify(minigame_id, category=None):
    """Catalog entry for a v2 minigame_id, plus whether the sent category disagrees."""
    game = game_for(minigame_id or '')
    sent_area = CATEGORY_AREAS.get(str(category or '').upper())
    return {
        'minigame_id': str(minigame_id or ''),
        'title': game['title'] if game else None,
        'concept': game['concept'] if game else None,
        'area': game['area'] if game else 'unmapped',
        'area_label': AREA_LABELS.get(game['area'], '미분류') if game else '미분류',
        'category_mismatch': bool(game and sent_area and sent_area != game['area']),
    }
