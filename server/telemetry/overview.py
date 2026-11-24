"""전체 현황 화면 전용 읽기 모델.

기존 집계(summary, learning_report, catalog.report, visual_report)를 그대로 쓰고,
화면에 필요한 비교·정렬·표시 값만 만든다. 새 수치를 추정하지 않는다.
"""
from datetime import timedelta

from .catalog import CATALOG, CATEGORY_AREAS, game_for
from .learning import learning_report
from .pipeline_events import EVENT_LABELS
from .queries import selection, summary

AREA_CODES = {area: code for code, area in CATEGORY_AREAS.items()}
SMALL_SAMPLE = 5  # 이보다 적은 문제 실행은 비율 해석에 주의 표시

SUCCESS_TYPES = {'attempt_succeeded', 'operation_succeeded', 'success', 'task_completed', 'problem_completed'}
FAILURE_TYPES = {'attempt_failed', 'operation_failed', 'failure'}
ACTION_LABELS = {
    'attempt': '이전 시도', 'success': '이전 성공', 'failure': '이전 실패', 'hint': '힌트 사용', 'level_start': '이전 레벨 시작',
    'task_started': '문제 시작', 'task_completed': '문제 해결', 'task_abandoned': '문제 포기',
    'attempt_started': '풀이 시도', 'paused': '일시정지', 'resumed': '재개',
    **EVENT_LABELS, 'problem_completed': '문제 해결', 'operation_succeeded': '연산 성공', 'operation_failed': '연산 실패',
}


def format_seconds(seconds):
    if seconds is None:
        return None
    seconds = round(seconds)
    minutes, rest = divmod(seconds, 60)
    return f'{minutes}분 {rest}초' if minutes else f'{rest}초'


def previous_window(request_get, filter_form):
    """같은 길이의 바로 앞 기간. 필터가 유효할 때만."""
    if not filter_form.is_valid():
        return None
    start, end = filter_form.cleaned_data['start'], filter_form.cleaned_data['end']
    days = (end - start).days + 1
    params = request_get.copy()
    params['end'] = (start - timedelta(days=1)).isoformat()
    params['start'] = (start - timedelta(days=days)).isoformat()
    return params


def comparison(current_stats, current_learning, request_get, filter_form):
    """이전 기간 비교. 이전 기간에 비교할 기록이 있을 때만 값을 채운다."""
    params = previous_window(request_get, filter_form)
    if params is None:
        return {}
    prev_form, players, sessions, events = selection(params)
    if not prev_form.is_valid():
        return {}
    prev_stats = summary(players, sessions, events)
    prev_learning = learning_report(prev_form, players)
    result = {'label': f"{prev_form.cleaned_data['start']:%m.%d}~{prev_form.cleaned_data['end']:%m.%d} 대비"}
    before, now = prev_stats['active_players'], current_stats['active_players']
    if before:
        change = round(100 * (now - before) / before, 1)
        result['players'] = {'value': f'{abs(change)}%', 'direction': _direction(change), 'tone': _tone(change, higher_is_good=True)}
    before, now = prev_learning.get('completion_rate'), current_learning.get('completion_rate')
    if before is not None and now is not None:
        change = round(now - before, 1)
        result['completion'] = {'value': f'{abs(change)}%p', 'direction': _direction(change), 'tone': _tone(change, higher_is_good=True)}
    before, now = prev_learning.get('avg_active_seconds'), current_learning.get('avg_active_seconds')
    if before is not None and now is not None:
        change = round(now - before)
        # 풀이 시간은 짧다고 무조건 좋은 것이 아니므로 색으로 좋고 나쁨을 표시하지 않는다.
        result['time'] = {'value': format_seconds(abs(change)) if change else '0초', 'direction': _direction(change), 'tone': 'neutral'}
    return result


def _direction(change):
    return 'up' if change > 0 else 'down' if change < 0 else 'flat'


def _tone(change, higher_is_good):
    if change == 0:
        return 'neutral'
    return 'good' if (change > 0) == higher_is_good else 'bad'


def _scoped_params(request_get, *drop):
    params = request_get.copy()
    for field in ('page', 'task_id', 'content_version', 'topic', 'scope', 'event_type', *drop):
        params.pop(field, None)
    return params


def attention_tasks(learning, request_get, limit=5):
    """재시도율(재시도한 실행 ÷ 문제 실행)이 높은 문제. 같은 비율이면 실행 수가 많은 순.

    실패 원인은 그 문제 실행에 기록된 연산 실패(operation_failed)만 센다. 문제 완료와 섞지 않는다.
    """
    rows = []
    for task in learning.get('tasks', []):
        if not task['runs'] or not task['retry_runs']:
            continue
        game = game_for(task['task_id'])
        url = None
        if game:
            params = _scoped_params(request_get)
            params['category'] = game['area']
            params['game_id'] = game['code']
            url = '/staff/games/?' + params.urlencode()
        logs = _scoped_params(request_get)
        logs['task_id'] = task['task_id']
        logs['content_version'] = task['version']
        failed = logs.copy()
        failed['event_type'] = 'operation_failed'
        total = task.get('failure_total', 0)
        rate = round(100 * task['retry_runs'] / task['runs'])
        rows.append({'code': game['code'] if game else task['task_id'], 'title': game['title'] if game else (task['title'] or '미분류 문제'),
                     'task_id': task['task_id'], 'version': task['version'], 'runs': task['runs'], 'retry_runs': task['retry_runs'],
                     'rate': rate, 'small': task['runs'] < SMALL_SAMPLE, 'url': url,
                     'completed': task['completed'], 'completion_rate': task['completion_rate'],
                     'attempts': task['attempts'], 'attempts_per_run': round(task['attempts'] / task['runs'], 1),
                     'avg_time': format_seconds(task.get('avg_active_seconds')), 'hint_runs': task.get('hint_runs', 0),
                     'failure_total': total,
                     'failure_top': [{**item, 'share': round(100 * item['count'] / total) if total else None}
                                     for item in task.get('failure_top', [])],
                     'events_url': '/staff/events/?' + logs.urlencode(),
                     'failures_url': '/staff/events/?' + failed.urlencode()})
    rows.sort(key=lambda r: (-r['rate'], -r['runs'], r['code']))
    return rows[:limit]


def area_rows(catalog, request_get=None, base_url='/staff/'):
    """분야 행. overview_url은 전체 현황에 그 분야 필터를 거는 주소(이미 선택돼 있으면 해제)."""
    current = (request_get or {}).get('category', '')
    rows = []
    for area in catalog['areas']:
        params = _scoped_params(request_get, 'game_id') if request_get is not None else None
        overview_url = None
        if params is not None:
            params.pop('category', None)
            if current != area['key']:
                params['category'] = area['key']
            overview_url = base_url + ('?' + params.urlencode() if params else '')
        rows.append({**area, 'code': AREA_CODES.get(area['key'], area['key'].upper()), 'current': current == area['key'],
                     'overview_url': overview_url,
                     'width': round(area['completion_rate']) if area['completion_rate'] is not None else 0})
    return rows


RECENT_LIMIT = 50


def recent_rows(events):
    rows = []
    for event in events:
        kind = event.event_type
        run = getattr(event, 'run', None) if getattr(event, 'run_id', None) else None
        task_id = run.task.task_id if run else ''
        game = game_for(task_id) if task_id else None
        player = event.session.player
        attempt = getattr(event, 'attempt', None) if getattr(event, 'attempt_id', None) else None
        result = 'success' if kind in SUCCESS_TYPES else 'failure' if kind in FAILURE_TYPES else None
        rows.append({'run_id': str(run.pk) if run else '', 'key': str(event.pk), 'occurred_at': event.occurred_at, 'player': player, 'player_id': event.session.player_id,
                     'game_code': game['code'] if game else task_id, 'game_title': game['title'] if game else '',
                     'area': game['area'] if game else '', 'task_id': task_id, 'version': run.task.content_version if run else '',
                     'kind': kind, 'action': ACTION_LABELS.get(kind, kind), 'detail': getattr(event, 'failure_reason', '') or '',
                     'operation': getattr(event, 'operation', '') or '', 'attempt': attempt.number if attempt else None,
                     'session': str(event.session_id), 'sequence': event.sequence, 'result': result,
                     'solved': kind in ('task_completed', 'problem_completed'), 'hint': kind == 'hint'})
    return rows


def kpi_states(learning, catalog):
    """미수집·기록 없음·실제 0 구분."""
    runs = learning.get('runs', 0)
    completed = learning.get('completed', 0)
    if learning.get('avg_active_seconds') is not None:
        time_state = 'value'
    elif not runs or not completed:
        time_state = 'no_completed'
    else:
        time_state = 'not_collected'  # 해결 기록은 있지만 풀이 시간이 저장되지 않음
    return {'has_runs': bool(runs), 'time_state': time_state,
            'avg_time': format_seconds(learning.get('avg_active_seconds')), 'missing_time': catalog.get('missing_active', 0)}


def area_tabs(catalog, cleaned, request_get):
    """게임 분석 상단의 분야 탭: 전체 + 4개 분야, 등록 게임 수와 현재 선택."""
    params = request_get.copy()
    for field in ('page', 'game_id', 'task_id', 'content_version', 'topic', 'category', 'scope'):
        params.pop(field, None)
    current = cleaned.get('category') or ''
    tabs = [{'key': '', 'label': '전체', 'count': catalog['registered'], 'url': '/staff/games/?' + params.urlencode(),
             'current': not current}]
    for area in catalog['areas']:
        tabs.append({'key': area['key'], 'label': area['label'], 'count': area['registered'], 'url': area['url'],
                     'current': current == area['key']})
    return tabs


def failure_rows(learning, limit=5):
    """자주 실패하는 연산·원인. 비율은 표시된 기간 전체 연산 실패 수 대비."""
    items = learning.get('failures') or []
    total = sum(item['count'] for item in items)
    return [{**item, 'share': round(100 * item['count'] / total, 1) if total else None, 'total': total}
            for item in items[:limit]]
