from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from django.utils import timezone
from .mongo import Records


def selected_runs(form, players):
    return getattr(form, 'mongo_runs', Records())


def attempt_levels(attempts, events):
    """Level of each attempt, read from its attempt_started event (details.level); None when unknown.

    The game opens a new attempt for every level of a multi-level minigame, and also when the player resets
    the same level (R). Only the second kind is a retry, so attempts are compared within the same level.
    Pipeline-projected events keep details under payload['details']; pipeline_learning_events keep them flat.
    """
    levels = {}
    for event in events:
        if event.event_type != 'attempt_started' or not event.attempt_id:
            continue
        payload = event.payload if isinstance(event.payload, dict) else {}
        details = payload.get('details') if isinstance(payload.get('details'), dict) else payload
        levels.setdefault(str(event.attempt_id), details.get('level'))
    return {str(a.pk): levels.get(str(a.pk)) for a in attempts}


def retry_count(attempts, events):
    """Restarts of a level already started in this run (attempts minus distinct levels).

    Attempts of unknown level (legacy) form one group, so old records keep the old meaning (attempts - 1)."""
    levels = attempt_levels(attempts, events)
    return sum(n - 1 for n in Counter(levels.get(str(a.pk)) for a in attempts).values())


def is_retry_run(attempts, events):
    """A run is a retry when one level was started more than once."""
    return retry_count(attempts, events) > 0


def hinted_attempt(attempts, hint):
    """The attempt (level) the hint was used in; a hint without an attempt link falls back to the next attempt."""
    if hint.attempt_id:
        own = next((a for a in attempts if str(a.pk) == str(hint.attempt_id)), None)
        if own:
            return own
    return next((a for a in attempts if a.started_at > hint.occurred_at), None)


def learning_report(form, players):
    """Problem metrics use runs started in the window, followed through current outcome.

    Legacy events without run links are never guessed into problem/attempt metrics.
    """
    if not form.is_valid():
        return {'runs': 0, 'tasks': [], 'failures': [], 'hint_evaluable': 0, 'hint_next_success': 0}
    runs = selected_runs(form, players)
    runs = list(runs.select_related('task').prefetch_related('attempts', 'events'))
    groups = {}
    evaluable, helped, completed, abandoned, retry_runs = 0, 0, 0, 0, 0
    active_times = []
    for run in runs:
        task = run.task
        row = groups.setdefault(task.pk, {'task_id': task.task_id, 'version': task.content_version, 'title': task.title,
            'topic': task.get_topic_display(), 'runs': 0, 'completed': 0, 'abandoned': 0, 'attempts': 0,
            'retry_runs': 0, 'hint_runs': 0, 'active_times': [], 'failure_counts': defaultdict(int)})
        attempts = sorted(run.attempts.all(), key=lambda a: (a.started_at, a.number))
        row['runs'] += 1
        row['attempts'] += len(attempts)
        if is_retry_run(attempts, list(run.events.all())):
            row['retry_runs'] += 1
            retry_runs += 1
        if run.status == 'completed':
            completed += 1
            row['completed'] += 1
            if run.active_ms is not None:
                active_times.append(run.active_ms)
                row['active_times'].append(run.active_ms)
        if run.status == 'abandoned':
            abandoned += 1
            row['abandoned'] += 1
        for event in run.events.all():
            if event.event_type == 'operation_failed':
                row['failure_counts'][(event.operation or 'unknown', event.failure_reason or 'unknown')] += 1
        hints = sorted((e for e in run.events.all() if e.event_type == 'hint'), key=lambda e: (e.occurred_at, e.sequence))
        if hints:
            row['hint_runs'] += 1
            # One observation per run: the outcome of the attempt the first hint was used in (same level).
            following = hinted_attempt(attempts, hints[0])
            if following and following.outcome in ('success', 'failure'):
                evaluable += 1
                helped += int(following.outcome == 'success')
    for row in groups.values():
        row['completion_rate'] = round(100 * row['completed'] / row['runs'], 1)
        row['abandon_rate'] = round(100 * row['abandoned'] / row['runs'], 1)
        times = row.pop('active_times')
        row['avg_active_seconds'] = round(sum(times) / len(times) / 1000, 1) if times else None
        counts = row.pop('failure_counts')
        row['failure_total'] = sum(counts.values())
        row['failure_top'] = [{'operation': k[0], 'reason': k[1], 'count': v}
                              for k, v in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:3]]
    # A run cohort is followed to completion; these failures may occur after the selected end date.
    failure_rows = [(event.operation, event.failure_reason) for run in runs for event in run.events.all() if event.event_type == 'operation_failed']
    failures = defaultdict(int)
    for operation, reason in failure_rows:
        failures[(operation or 'unknown', reason or 'unknown')] += 1
    return {'runs': len(runs), 'completed': completed, 'abandoned': abandoned, 'in_progress': sum(r.status == 'in_progress' for r in runs), 'retry_runs': retry_runs,
            'completion_rate': round(100 * completed / len(runs), 1) if runs else None,
            'avg_active_seconds': round(sum(active_times)/len(active_times)/1000, 1) if active_times else None,
            'hint_evaluable': evaluable, 'hint_next_success': helped,
            'hint_next_rate': round(100 * helped/evaluable, 1) if evaluable else None,
            'tasks': sorted(groups.values(), key=lambda r: (-r['abandon_rate'], r['completion_rate'], r['task_id'], r['version'])),
            'failures': [{'operation': k[0], 'reason': k[1], 'count': v} for k, v in sorted(failures.items(), key=lambda item: (-item[1], item[0]))]}
