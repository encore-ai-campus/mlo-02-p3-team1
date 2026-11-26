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


def completed_at(events):
    """When the run's game was completed (first task_completed event), or None."""
    times = [e.occurred_at for e in events if e.event_type == 'task_completed']
    return min(times) if times else None


def attempts_after_completion(attempts, events):
    """Attempts started after the game was completed in the same run (builds before the replay fix reopen
    the last level in the completed run instead of starting a new run)."""
    done = completed_at(events)
    return [a for a in attempts if done is not None and a.started_at > done]


def retry_count(attempts, events):
    """재시작: restarts of a level before the game was completed, after a failed or still-open attempt.

    Each attempt is compared with the previous attempt of the same level in this run. Replaying a level that
    was already cleared (previous attempt succeeded) is practice, and an attempt started after the game was
    completed is a replay (다시 하기); neither counts. Attempts of unknown level (legacy) form one group."""
    levels = attempt_levels(attempts, events)
    late = {str(a.pk) for a in attempts_after_completion(attempts, events)}
    previous, count = {}, 0
    for attempt in sorted(attempts, key=lambda a: (a.started_at, a.number)):
        if str(attempt.pk) in late:
            continue
        level = levels.get(str(attempt.pk))
        before = previous.get(level)
        if before is not None and before.outcome != 'success':
            count += 1
        previous[level] = attempt
    return count


def is_retry_run(attempts, events):
    """A run is a restart run (재시작) when retry_count > 0."""
    return retry_count(attempts, events) > 0


def is_replay_run(run, attempts, events):
    """다시 하기: the player had already completed this game in an earlier run (run.is_replay, set when the
    snapshot is loaded), or played on after completing it in this same run."""
    return bool(getattr(run, 'is_replay', False)) or bool(attempts_after_completion(attempts, events))


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
    # 재시작 (retry_runs / restart_runs): a level restarted before completion after a failed/open attempt (is_retry_run).
    # 다시 하기 (replay_runs): the game was already completed, earlier or in this run (is_replay_run).
    # 오답률 (wrong_rate): operation_failed / (operation_succeeded + operation_failed). A reset (R) is a new
    # attempt, not an operation, so it is not counted.
    runs = selected_runs(form, players)
    runs = list(runs.select_related('task').prefetch_related('attempts', 'events'))
    groups = {}
    evaluable, helped, completed, abandoned, retry_runs, replay_runs, wrong_ops, ops = 0, 0, 0, 0, 0, 0, 0, 0
    active_times = []
    for run in runs:
        task = run.task
        row = groups.setdefault(task.pk, {'task_id': task.task_id, 'version': task.content_version, 'title': task.title,
            'topic': task.get_topic_display(), 'runs': 0, 'completed': 0, 'abandoned': 0, 'attempts': 0,
            'retry_runs': 0, 'replay_runs': 0, 'wrong_ops': 0, 'ops': 0, 'hint_runs': 0, 'active_times': [],
            'failure_counts': defaultdict(int)})
        attempts = sorted(run.attempts.all(), key=lambda a: (a.started_at, a.number))
        row['runs'] += 1
        row['attempts'] += len(attempts)
        run_events = list(run.events.all())
        if is_retry_run(attempts, run_events):
            row['retry_runs'] += 1
            retry_runs += 1
        if is_replay_run(run, attempts, run_events):
            row['replay_runs'] += 1
            replay_runs += 1
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
            if event.event_type in ('operation_succeeded', 'operation_failed'):
                row['ops'] += 1
                ops += 1
            if event.event_type == 'operation_failed':
                row['wrong_ops'] += 1
                wrong_ops += 1
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
        row['restart_runs'] = row['retry_runs']
        row['wrong_rate'] = round(100 * row['wrong_ops'] / row['ops'], 1) if row['ops'] else None
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
            'restart_runs': retry_runs, 'replay_runs': replay_runs, 'wrong_ops': wrong_ops, 'ops': ops,
            'wrong_rate': round(100 * wrong_ops / ops, 1) if ops else None,
            'completion_rate': round(100 * completed / len(runs), 1) if runs else None,
            'avg_active_seconds': round(sum(active_times)/len(active_times)/1000, 1) if active_times else None,
            'hint_evaluable': evaluable, 'hint_next_success': helped,
            'hint_next_rate': round(100 * helped/evaluable, 1) if evaluable else None,
            'tasks': sorted(groups.values(), key=lambda r: (-r['abandon_rate'], r['completion_rate'], r['task_id'], r['version'])),
            'failures': [{'operation': k[0], 'reason': k[1], 'count': v} for k, v in sorted(failures.items(), key=lambda item: (-item[1], item[0]))]}
