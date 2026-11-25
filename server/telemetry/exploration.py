"""Read-only, administrator-only analysis interactions. No ingestion or schema changes."""
from datetime import datetime, time, timedelta
from uuid import UUID
from django.http import JsonResponse
from django.utils import timezone
from accounts.views import api
from .queries import selection
from .catalog import report, CATALOG
from .mongo import database, Records
from .models import Player, BehaviorEvent


def scope(request):
    from .forms import AnalysisFilter
    checked=AnalysisFilter(request.GET)
    if not checked.is_valid():
        return None, JsonResponse({'error':'필터를 확인하세요','details':checked.errors.get_json_data()},status=400)
    if (checked.cleaned_data['end']-checked.cleaned_data['start']).days>90:
        return None, JsonResponse({'error':'비교는 최대 91일 범위로 조회하세요'},status=400)
    form, players, sessions, events = selection(request.GET)
    if not form.is_valid():
        return None, JsonResponse({'error': '필터를 확인하세요', 'details': form.errors.get_json_data()}, status=400)
    if (form.cleaned_data['end'] - form.cleaned_data['start']).days > 90:
        return None, JsonResponse({'error': '비교는 최대 91일 범위로 조회하세요'}, status=400)
    return (form, players, sessions, events), None


@api('GET', authenticated=True)
def compare_players(request):
    try:
        ids = list(dict.fromkeys(str(UUID(x)) for x in request.GET.getlist('ids')))
    except ValueError:
        return JsonResponse({'error': '플레이어 ID가 올바르지 않습니다'}, status=400)
    if not 2 <= len(ids) <= 3:
        return JsonResponse({'error': '플레이어를 2~3명 선택하세요'}, status=400)
    data, error = scope(request)
    if error is not None: return error
    form, players, sessions, events = data
    members = {str(p.pk): p for p in players.filter(pk__in=ids)}
    if len(members) != len(ids):
        return JsonResponse({'error': '현재 데이터 필터에 포함된 플레이어만 비교할 수 있습니다'}, status=400)
    runs = list(form.mongo_runs)
    result = []
    for ident in ids:
        selected = Records([r for r in runs if str(r.session.player_id) == ident])
        selected_events = Records([e for e in events if str(e.session.player_id) == ident])
        totals = report(selected, selected_events)['totals']
        result.append({'id': ident, 'name': members[ident].display_name,
            'source': members[ident].source, **{key: totals[key] for key in
            ('runs', 'completed', 'completion_rate', 'avg_seconds', 'retries', 'hints', 'failures')}})
    return JsonResponse({'players': result, 'basis': '선택 기간에 시작한 문제 실행 기준. 기록 없음은 0%가 아닙니다.'})


@api('GET', authenticated=True)
def timeline(request):
    try: run = str(UUID(request.GET.get('run', '')))
    except ValueError: return JsonResponse({'error': '문제 실행 ID가 올바르지 않습니다'}, status=400)
    db = database()
    # The projection and raw copy share IDs. Prefer projected events and deduplicate raw IDs.
    events = {}
    for d in db.gameplay_events.find({'run_id': run}).sort([('occurred_at',1),('sequence',1)]).limit(501):
        events[str(d['_id'])] = {'id':str(d['_id']), 'at':d.get('occurred_at'), 'sequence':d.get('sequence'),
            'kind':d.get('event_type'), 'operation':d.get('operation'), 'reason':d.get('failure_reason'),
            'before':d.get('state_before') or None, 'after':d.get('state_after') or None}
    for d in db.pipeline_learning_events.find({'run_id': run}).sort([('occurred_at',1),('sequence',1)]).limit(501):
        details = d.get('details') or {}
        events.setdefault(str(d.get('event_id') or d['_id']), {'id':str(d['_id']), 'at':d.get('occurred_at'),
            'sequence':d.get('sequence'), 'kind':d.get('event_type'), 'operation':details.get('operation'),
            'reason':details.get('failure_reason'), 'before':details.get('state_before') or None,
            'after':details.get('state_after') or None})
    ordered = sorted(events.values(), key=lambda e:(e['at'] or timezone.now(),e['sequence'] or 0,e['id']))
    return JsonResponse({'run':run,'events':ordered[:500], 'truncated':len(ordered)>500,
        'basis':'저장된 이벤트 순서입니다. 상태가 미수집된 이벤트는 재구성하지 않습니다.'})


@api('GET', authenticated=True)
def periods(request):
    from .visuals import visual_report
    from .overview import previous_window
    data, error = scope(request)
    if error is not None: return error
    form, players, sessions, events = data
    current = visual_report(form, players, events)
    previous_params = previous_window(request.GET,form)
    pf, pp, ps, pe = selection(previous_params)
    previous = visual_report(pf,pp,pe)
    return JsonResponse({'current':current['trend'],'previous':previous['trend'],
        'current_range':[str(form.cleaned_data['start']),str(form.cleaned_data['end'])],
        'previous_range':[str(pf.cleaned_data['start']),str(pf.cleaned_data['end'])],
        'previous_runs':previous['runs'], 'basis':'같은 길이의 직전 기간을 상대 날짜 순서로 비교합니다.'})


def log_query(params):
    """Additional chart drill filters shared by log page and new-record polling."""
    from .pipeline_events import SUCCESS_TYPES, FAILURE_TYPES, member_keys, EVENT_LABELS
    from .models import GameAccount
    today=timezone.localdate()
    def day(key,default):
        try:return datetime.strptime(params.get(key,''),'%Y-%m-%d').date()
        except ValueError:return default
    start,end=day('start',today-timedelta(days=6)),day('end',today)
    if start>end:start,end=end,start
    q={'occurred_at':{'$gte':timezone.make_aware(datetime.combine(start,time.min)),
                     '$lt':timezone.make_aware(datetime.combine(end+timedelta(days=1),time.min))}}
    member=params.get('member') or params.get('player_id')
    if member:
        try:p=Player.objects.filter(pk=UUID(member)).first()
        except ValueError:p=None
        q['player_id']={'$in':member_keys(p) if p else []}
    source=params.get('source')
    if source in ('live','demo'):
        from .pipeline_events import identity_map
        allowed={str(pk) for pk in Player.objects.filter(source=source).values_list('pk',flat=True)}
        keys={key for key,value in identity_map().items() if str(value['pk']) in allowed}
        if 'player_id' in q:keys &= set(q['player_id']['$in'])
        q['player_id']={'$in':sorted(keys)}
    game=(params.get('game') or params.get('game_id') or '').upper()
    if game in CATALOG:q['minigame_id']=game
    elif params.get('category'):
        q['minigame_id']={'$in':[code for code,g in CATALOG.items() if g['area']==params['category']]}
    kind=params.get('kind')
    if kind in EVENT_LABELS:q['event_type']=kind
    elif params.get('result') in ('success','failure'):
        q['event_type']={'$in':list(SUCCESS_TYPES if params['result']=='success' else FAILURE_TYPES)}
    for key,field in [('operation','details.operation'),('reason','details.failure_reason'),('run','run_id'),('content_version','content_version')]:
        if params.get(key):q[field]=params[key][:100]
    who=params.get('who')
    if who in ('member','guest'):
        # 회원 = 가입 계정(또는 그 계정이 로그인한 기기)에 연결된 기록, 게스트 = 그 밖의 모든 기록
        from .pipeline_events import identity_map
        member_ids=set(identity_map())
        current=set(q['player_id']['$in']) if 'player_id' in q else None
        if who=='member':
            q['player_id']={'$in':sorted(member_ids if current is None else current&member_ids)}
        elif current is None:
            q['player_id']={'$nin':sorted(member_ids)}
        else:
            q['player_id']={'$in':sorted(current-member_ids)}
    return q


@api('GET', authenticated=True)
def new_logs(request):
    import json
    q=log_query(request.GET)
    col=database().pipeline_learning_events
    latest=col.find_one({**q,'received_at':{'$type':'date'}},sort=[('received_at',-1),('_id',-1)])
    cursor={'at':latest['received_at'].isoformat(),'id':str(latest['_id'])} if latest else {'at':timezone.now().isoformat(),'id':''}
    after=request.GET.get('after')
    count=0
    if after:
        try:
            old=json.loads(after);at=datetime.fromisoformat(old['at'])
            if timezone.is_naive(at):raise ValueError()
            count=col.count_documents({'$and':[q,{'$or':[{'received_at':{'$gt':at}},
                {'received_at':at,'_id':{'$gt':str(old.get('id',''))}}]}]})
        except (ValueError,KeyError,TypeError):return JsonResponse({'error':'조회 기준이 올바르지 않습니다'},status=400)
    return JsonResponse({'count':count,'cursor':cursor,'basis':'수집 도착 시각 기준. 버튼을 누르기 전에는 현재 목록을 바꾸지 않습니다.'})
