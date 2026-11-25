"""Plan/execute a bounded, journalled replay of state-object schema rejections.

No ID/sequence regeneration, no DLQ deletion, no changes to existing accepted content.
The journal contains raw game data: keep it outside Git and copy it to private backup.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.admin import AdminClient
from pymongo import MongoClient
import contract


def snapshot_records(topic, maximum=20000):
    bootstrap=os.environ['KAFKA_BOOTSTRAP']
    metadata=AdminClient({'bootstrap.servers':bootstrap}).list_topics(timeout=8)
    consumer=Consumer({'bootstrap.servers':bootstrap,'group.id':'readonly-state-recovery',
                       'enable.auto.commit':False,'enable.partition.eof':True})
    parts=[];ends={};total=0
    for partition in metadata.topics[topic].partitions:
        low,high=consumer.get_watermark_offsets(TopicPartition(topic,partition),timeout=8)
        total+=high-low
        if high>low:parts.append(TopicPartition(topic,partition,low));ends[partition]=high
    if total>maximum:
        consumer.close();raise RuntimeError('Snapshot exceeds bounded recovery limit')
    consumer.assign(parts);done=set();result=[];deadline=time.monotonic()+30
    try:
        while len(done)<len(ends) and time.monotonic()<deadline:
            message=consumer.poll(.2)
            if message is None:continue
            if message.error():
                from confluent_kafka import KafkaError
                if message.error().code()==KafkaError._PARTITION_EOF:done.add(message.partition());continue
                raise RuntimeError('Kafka snapshot read failed')
            if message.offset()<ends[message.partition()]:
                result.append(json.loads(message.value()))
            if message.offset()+1>=ends[message.partition()]:done.add(message.partition())
        if len(done)!=len(ends):raise RuntimeError('Incomplete Kafka snapshot')
    finally:consumer.close()
    return result


def prepare():
    accepted={}
    for row in snapshot_records('nv.learning.v2'):
        accepted.setdefault(row.get('event_id'),set()).add(row.get('payload_hash'))
    candidates={};conflicts=[];invalid=0
    for row in snapshot_records('nv.dlq.v1'):
        errors=row.get('errors') or []
        if row.get('reason')!='schema_error' or not errors or any(
                error.get('loc') not in ('details.state_after','details.state_before') for error in errors):
            continue
        if row.get('raw_truncated'):invalid+=1;continue
        try:
            body=json.loads(row['raw'])
            model=contract.LearningEventV2.model_validate(body)
            normalized=contract.to_record(model,datetime.now(timezone.utc))
        except Exception:invalid+=1;continue
        ident=normalized['event_id'];known=accepted.get(ident,set())
        if known and known!={normalized['payload_hash']}:
            conflicts.append(ident);continue
        entry={'event_id':ident,'session_id':normalized['session_id'],'sequence':normalized['sequence'],
               'expected_hash':normalized['payload_hash'],'original_body':body,
               'status':'already_accepted' if known else 'prepared'}
        if ident in candidates and candidates[ident]['expected_hash']!=entry['expected_hash']:
            conflicts.append(ident)
        else:candidates[ident]=entry
    return {'created_at':datetime.now(timezone.utc).isoformat(),'conflicts':conflicts,
            'invalid':invalid,'events':sorted(candidates.values(),key=lambda e:(e['session_id'],e['sequence']))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journal',required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--url',default='http://127.0.0.1:8000/v2/events')
    parser.add_argument('--key-stdin',action='store_true',help='Read public gateway key from stdin, never journal/argv')
    args=parser.parse_args();path=Path(args.journal)
    if not args.execute:
        if path.exists():raise SystemExit('Refuse to overwrite recovery journal')
        result=prepare();path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'prepared':len(result['events']),'conflicts':len(result['conflicts']),
                          'invalid':result['invalid'],'execute':False}));return
    result=json.loads(path.read_text(encoding='utf-8'))
    api_key=sys.stdin.readline().rstrip('\r\n') if args.key_stdin else os.environ['INGEST_KEY']
    if result['conflicts'] or result['invalid']:raise SystemExit('Resolve conflicts/invalid candidates first')
    db=MongoClient(os.environ['MONGO_URI'])[os.getenv('MONGO_DB','nodeverse_logs')]
    # Recheck all known outbox content immediately before any write.
    for entry in result['events']:
        known=db.remote_event_outbox.find_one({'_id':entry['event_id']},{'payload_hash':1})
        if known and known.get('payload_hash')!=entry['expected_hash']:
            raise SystemExit('Existing accepted content conflicts; replay aborted')
    for entry in result['events']:
        if entry['status'] in ('accepted','already_accepted'):continue
        request=urllib.request.Request(args.url,data=json.dumps(entry['original_body']).encode(),
                headers={'Content-Type':'application/json','X-API-Key':api_key},method='POST')
        entry['status']='sending';path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        try:
            with urllib.request.urlopen(request,timeout=15) as response:
                if response.status!=202:raise RuntimeError('Replay not accepted')
                reply=json.load(response)
                if reply.get('event_id')!=entry['event_id']:raise RuntimeError('Replay identity mismatch')
            entry['status']='accepted'
        except Exception:
            entry['status']='uncertain';path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            raise SystemExit('Replay interrupted; inspect private journal before retry')
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'events':len(result['events']),'accepted':sum(e['status']=='accepted' for e in result['events']),
                      'already_accepted':sum(e['status']=='already_accepted' for e in result['events'])}))


if __name__=='__main__':main()
