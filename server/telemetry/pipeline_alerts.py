"""Pipeline alert status, read from the pipeline observatory on .81 (read-only relay).

The observatory already samples the pipeline every 10 seconds and keeps the result in memory,
so this module never touches the pipeline's data stores. To keep load on .81 flat no matter how many
staff screens are open, every upstream call is shared through a short cache: at most one snapshot
request per SNAPSHOT_TTL seconds, and a failed call is not retried until FAILURE_BACKOFF passes.
Only the fields the staff screen needs are passed on; free-form error text is never forwarded.
"""
import json
import threading
import time
from urllib import error as urlerror, request as urlrequest
from urllib.parse import urlencode

from django.conf import settings

SNAPSHOT_TTL = 10
ATTENTION_TTL = 30
FAILURE_BACKOFF = 15
TIMEOUT = 3
ATTENTION_STATES = ('waiting_context', 'parked', 'blocked', 'quarantined')
QUEUE_STATES = ('pending', 'processing', 'retrying', 'waiting_context', 'parked', 'blocked', 'quarantined', 'stored')
MAX_EVENTS = 100

_cache = {}
_cache_lock = threading.Lock()
_fetch_locks = {}


class UpstreamError(Exception):
    def __init__(self, state):
        super().__init__(state)
        self.state = state


def _fetch(path):
    url = settings.OBSERVATORY_URL.rstrip('/') + path
    req = urlrequest.Request(url, headers={'X-Observatory-Key': settings.OBSERVATORY_KEY, 'Accept': 'application/json'})
    try:
        with urlrequest.urlopen(req, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode('utf-8'))
    except urlerror.HTTPError as e:
        raise UpstreamError({401: 'unauthorized', 503: 'starting', 422: 'bad_request'}.get(e.code, 'unavailable')) from None
    except (urlerror.URLError, TimeoutError, OSError, ValueError):
        raise UpstreamError('unavailable') from None


def _cached(path, ttl):
    """Return (state, data, fetched_at). Concurrent callers for one path share a single upstream call."""
    now = time.monotonic()
    entry = _cache.get(path)
    if entry and now < entry['until']:
        return entry['value']
    with _cache_lock:
        lock = _fetch_locks.setdefault(path, threading.Lock())
    with lock:
        entry = _cache.get(path)
        if entry and time.monotonic() < entry['until']:
            return entry['value']
        try:
            value = ('ok', _fetch(path), time.time())
            until = time.monotonic() + ttl
        except UpstreamError as e:
            value = (e.state, None, time.time())
            until = time.monotonic() + FAILURE_BACKOFF
        _cache[path] = {'value': value, 'until': until}
        return value


def clear_cache():
    _cache.clear()


def _text(value, limit=300):
    return value[:limit] if isinstance(value, str) else None


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _alert(item):
    return {'id': _text(item.get('id'), 120), 'level': 'error' if item.get('level') == 'error' else 'warning',
            'title': _text(item.get('title'), 120), 'detail': _text(item.get('detail')),
            'first_seen': _text(item.get('first_seen'), 40)}


def _event(item):
    phase = item.get('phase') if item.get('phase') in ('opened', 'changed', 'resolved') else 'opened'
    return {**_alert(item), 'phase': phase, 'at': _text(item.get('at'), 40)}


def _service(part):
    state = (part or {}).get('state')
    return state if isinstance(state, str) and len(state) <= 30 else 'unknown'


def summarize(snapshot):
    queue = snapshot.get('queue') or {}
    counts = queue.get('counts')
    if isinstance(counts, dict):
        counts = {state: _number(counts.get(state)) or 0 for state in QUEUE_STATES}
    else:
        counts = None
    return {
        'at': _text(snapshot.get('at'), 40),
        'snapshot_age_s': _number(snapshot.get('snapshot_age_s')),
        'sampler_ok': not snapshot.get('sampler_error'),
        'alerts_persistent': snapshot.get('alerts_persistent') is not False,
        'alerts': [_alert(a) for a in (snapshot.get('alerts') or []) if isinstance(a, dict)],
        'incidents': [_event(e) for e in (snapshot.get('incidents') or [])[:MAX_EVENTS] if isinstance(e, dict)],
        'services': {'collector': _service(snapshot.get('collector')), 'progress': _service(snapshot.get('progress')),
                     'mongo': _service(snapshot.get('mongo')), 'remote': _service(snapshot.get('remote'))},
        'queue': {'counts': counts, 'oldest_due_age_s': _number(queue.get('oldest_due_age_s')),
                  'oldest_context_age_s': _number(queue.get('oldest_context_age_s'))},
        'queries': [{'name': _text(q.get('name'), 80), 'label': _text(q.get('label'), 80), 'active': bool(q.get('active')),
                     'batch_id': _number(q.get('batch_id')), 'input_rows': _number(q.get('input_rows')),
                     'batch_ms': _number(q.get('batch_ms'))}
                    for q in (snapshot.get('queries') or []) if isinstance(q, dict)],
    }


def status():
    if not settings.OBSERVATORY_KEY:
        return {'state': 'unconfigured'}
    state, data, fetched_at = _cached('/api/snapshot', SNAPSHOT_TTL)
    result = {'state': state, 'fetched_at': fetched_at}
    if state == 'ok' and isinstance(data, dict):
        result.update(summarize(data))
    elif state == 'ok':
        result['state'] = 'unavailable'
    return result


def attention(state_name):
    if not settings.OBSERVATORY_KEY:
        return {'state': 'unconfigured', 'records': []}
    state, data, _ = _cached('/api/attention?' + urlencode({'state': state_name}), ATTENTION_TTL)
    if state != 'ok' or not isinstance(data, dict):
        return {'state': state if state != 'ok' else 'unavailable', 'records': []}
    records = []
    for row in (data.get('records') or [])[:20]:
        if isinstance(row, dict):
            records.append({'reference': _text(row.get('reference'), 20), 'reason_code': _text(row.get('reason_code'), 60),
                            'reason_label': _text(row.get('reason_label'), 80), 'attempts': _number(row.get('attempts')),
                            'archive_stored': row.get('archive_stored') if isinstance(row.get('archive_stored'), bool) else None,
                            'queued_at': _text(row.get('queued_at'), 40), 'updated_at': _text(row.get('updated_at'), 40)})
    return {'state': _text(data.get('state'), 30) or 'unavailable', 'records': records, 'more': bool(data.get('more'))}


# ---------- views ----------
from django.http import JsonResponse  # noqa: E402
from django.shortcuts import render  # noqa: E402
from django.views.decorators.http import require_GET  # noqa: E402

from accounts.views import admin_page, api  # noqa: E402


def _json(data, status=200):
    response = JsonResponse(data, status=status, json_dumps_params={'ensure_ascii': False})
    response['Cache-Control'] = 'no-store'
    return response


@require_GET
@admin_page
def alerts_page(request):
    return render(request, 'telemetry/pipeline_alerts.html', {'poll_seconds': SNAPSHOT_TTL})


@api('GET', authenticated=True)
def status_api(request):
    return _json(status())


@api('GET', authenticated=True)
def attention_api(request):
    state = request.GET.get('state', '')
    if state not in ATTENTION_STATES:
        return _json({'error': 'unsupported_state', 'allowed': list(ATTENTION_STATES)}, status=400)
    return _json(attention(state))
