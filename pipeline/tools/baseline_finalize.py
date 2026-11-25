"""Read-only reference and latency checks for the isolated completed baseline."""
import json,os
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient
import pymysql
from baseline_driver import stats

assert os.environ['DIRECT_MYSQL_HOST']=='target-mysql' and os.environ['DIRECT_MYSQL_DATABASE']=='baseline'
local=MongoClient('mongodb://mongo:27017',tz_aware=True).baseline_local
remote=MongoClient('mongodb://target-mongo:27017',tz_aware=True).baseline_remote
results=json.loads(Path('/results/results.json').read_text()); summary={}
for stage in results['stages']:
    start,end=stage['started_at'],stage['ended_at']
    rows=list(local.remote_event_outbox.find({'event.received_at':{'$gte':start,'$lte':end}},
        {'event.received_at':1,'queued_at':1,'completed_at':1,'state':1}))
    prequeue=[(r['queued_at']-datetime.fromisoformat(r['event']['received_at'].replace('Z','+00:00'))).total_seconds()*1000 for r in rows]
    summary[stage['stage']]={'rows':len(rows),'received_to_queued_ms':stats(prequeue)}
sql=pymysql.connect(host='target-mysql',user='root',password=os.environ['DIRECT_MYSQL_PASSWORD'],database='baseline')
with sql.cursor() as c:c.execute('SELECT member_id FROM game_members'); members={r[0] for r in c.fetchall()}
sql.close()
sessions={s['_id']:s for s in remote.game_sessions.find({},{'player_id':1})}
problems={p['_id'] for p in remote.game_problems.find({},{'_id':1})}
runs={r['_id']:r for r in remote.problem_runs.find({},{'task_id':1,'session_id':1,'status':1})}
attempts={a['_id']:a for a in remote.solution_attempts.find({},{'run_id':1,'outcome':1})}
bad=0; events=0
for e in remote.gameplay_events.find({},{'session_id':1,'run_id':1,'attempt_id':1}):
    events+=1
    bad+=bool(e['session_id'] not in sessions or e['run_id'] not in runs or
              (e.get('attempt_id') and e['attempt_id'] not in attempts))
bad+=sum(s['player_id'].replace('-','') not in members for s in sessions.values())
bad+=sum(r['session_id'] not in sessions or r['task_id'] not in problems for r in runs.values())
bad+=sum(a['run_id'] not in runs for a in attempts.values())
integrity={'events':events,'archives':remote.pipeline_learning_events.count_documents({}),'members':len(members),
 'sessions':len(sessions),'completed_runs':sum(r['status']=='completed' for r in runs.values()),
 'successful_attempts':sum(a['outcome']=='success' for a in attempts.values()),'reference_errors':bad}
result={'latency':summary,'integrity':integrity}
Path('/results/finalize.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
assert bad==0 and events==sum(s['events'] for s in results['stages'])
