"""Durable chunk receipt is distinct from Delta/remote delivery completion."""
import json,re,os
from datetime import datetime,timedelta,timezone
from uuid import UUID
from fastapi import APIRouter,Header,HTTPException,Request
from fastapi.concurrency import run_in_threadpool
from pymongo import UpdateOne
from pymongo import ReturnDocument
import uuid
from pymongo.errors import DuplicateKeyError
from pymongo.write_concern import WriteConcern
from common.db import local_mongo
from offline.protocol import Manifest,canonical,decode,digest,MAX_COMPRESSED,TOPIC

router=APIRouter(prefix='/v2/offline',tags=['offline learning import'])
def now():return datetime.now(timezone.utc)
def auth(key):
    from collector import check_key
    check_key(key)
    if os.getenv('OFFLINE_ENABLED','0')!='1':raise HTTPException(503,'offline_import_disabled')
def db():return local_mongo().with_options(write_concern=WriteConcern(w='majority',j=True))
def upload(database,ident):
    row=database.offline_uploads.find_one({'_id':str(ident)})
    if not row:raise HTTPException(404,'upload_not_found')
    return row


@router.put('/uploads/{upload_id}')
async def create(upload_id:UUID,request:Request,x_api_key:str=Header(default='')):
    auth(x_api_key)
    raw=bytearray()
    async for part in request.stream():
        if len(raw)+len(part)>16*1024:raise HTTPException(413,'manifest_body_limit')
        raw.extend(part)
    try:manifest=Manifest.model_validate_json(bytes(raw))
    except ValueError:raise HTTPException(422,'invalid_offline_manifest_or_dictionary_version')
    return await run_in_threadpool(create_manifest,upload_id,manifest)

def create_manifest(upload_id,manifest):
    if any(not re.fullmatch('[0-9a-f]{64}',h) for h in manifest.chunk_hashes):raise HTTPException(422,'invalid_chunk_hash')
    database=db();ident=str(upload_id);old=database.offline_uploads.find_one({'_id':ident})
    if old:
        if old['manifest_hash']!=manifest.digest():raise HTTPException(409,'upload_manifest_conflict')
        return {'upload_id':ident,'state':old['state']}
    owner=uuid.uuid4().hex
    try:
        gate=database.offline_locks.find_one_and_update({'_id':'admission','$or':[{'expires_at':{'$lte':now()}},{'owner':owner}]},
            {'$set':{'owner':owner,'expires_at':now()+timedelta(seconds=15)}},upsert=True,return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:raise HTTPException(429,'admission_busy',headers={'Retry-After':'1'})
    try:return admit(database,ident,manifest)
    finally:database.offline_locks.delete_one({'_id':'admission','owner':owner})

def admit(database,ident,manifest):
    old=database.offline_uploads.find_one({'_id':ident})
    if old:
        if old['manifest_hash']!=manifest.digest():raise HTTPException(409,'upload_manifest_conflict')
        return {'upload_id':ident,'state':old['state']}
    # Serialize admissions so simultaneous clients cannot overshoot the count quota.
    active={'state':{'$in':['receiving','queued','processing','retrying']}}
    if database.offline_uploads.count_documents(active,limit=100)>=100:
        raise HTTPException(429,'offline_queue_full',headers={'Retry-After':'60'})
    installation=str(manifest.installation_id)
    if database.offline_uploads.count_documents({**active,'installation_id':installation},limit=4)>=4:
        raise HTTPException(429,'installation_upload_limit',headers={'Retry-After':'30'})
    row={'_id':ident,'manifest':manifest.model_dump(mode='json'),'manifest_hash':manifest.digest(),
         'installation_id':installation,'state':'receiving','created_at':now(),'attempts':0,'next_attempt_at':now()}
    try:database.offline_uploads.insert_one(row)
    except DuplicateKeyError:
        if upload(database,ident)['manifest_hash']!=manifest.digest():raise HTTPException(409,'upload_manifest_conflict')
    return {'upload_id':ident,'state':upload(database,ident)['state']}


def store_chunk(ident,index,body):
    database=db();job=upload(database,ident);manifest=Manifest.model_validate(job['manifest'])
    if index<0 or index>=len(manifest.chunk_hashes):raise HTTPException(422,'chunk_index')
    hash_=digest(body)
    if hash_!=manifest.chunk_hashes[index]:raise HTTPException(409,'chunk_checksum_mismatch')
    key=ident+':'+str(index);old=database.offline_chunks.find_one({'_id':key})
    if old:
        if old['hash']!=hash_:raise HTTPException(409,'chunk_conflict')
        return {'chunk':index,'durably_received':True}
    if job['state']!='receiving':raise HTTPException(409,'upload_already_sealed')
    try:records=canonical(body,manifest,job['created_at'].replace(tzinfo=timezone.utc))
    except ValueError as e:raise HTTPException(422,str(e)[:200])
    ids=[r['event_id'] for r in records]
    if len(set(ids))!=len(ids):raise HTTPException(409,'duplicate_id_in_chunk')
    existing={r['_id']:r['payload_hash'] for r in database.remote_event_outbox.find({'_id':{'$in':ids}},{'payload_hash':1})}
    if any(r['event_id'] in existing and existing[r['event_id']]!=r['payload_hash'] for r in records):
        raise HTTPException(409,'existing_online_event_conflict')
    database.offline_event_registry.bulk_write([UpdateOne({'_id':r['event_id']},{'$setOnInsert':{
        'payload_hash':r['payload_hash'],'created_at':now()}},upsert=True) for r in records],ordered=False)
    known={r['_id']:r['payload_hash'] for r in database.offline_event_registry.find({'_id':{'$in':ids}})}
    if any(known[r['event_id']]!=r['payload_hash'] for r in records):raise HTTPException(409,'event_id_conflict')
    try:database.offline_chunks.insert_one({'_id':key,'upload_id':ident,'index':index,'hash':hash_,'records':records,'created_at':now()})
    except DuplicateKeyError:
        if database.offline_chunks.find_one({'_id':key})['hash']!=hash_:raise HTTPException(409,'chunk_conflict')
    return {'chunk':index,'durably_received':True}


@router.put('/uploads/{upload_id}/chunks/{index}')
async def chunk(upload_id:UUID,index:int,request:Request,x_api_key:str=Header(default='')):
    auth(x_api_key);raw=bytearray()
    async for part in request.stream():
        if len(raw)+len(part)>MAX_COMPRESSED:raise HTTPException(413,'compressed_body_limit')
        raw.extend(part)
    try:body=decode(bytes(raw),request.headers.get('content-encoding','identity'))
    except (ValueError,UnicodeDecodeError) as e:raise HTTPException(422,str(e)[:200])
    return await run_in_threadpool(store_chunk,str(upload_id),index,body)


@router.post('/uploads/{upload_id}/seal',status_code=202)
def seal(upload_id:UUID,x_api_key:str=Header(default='')):
    auth(x_api_key);database=db();ident=str(upload_id);job=upload(database,ident);m=Manifest.model_validate(job['manifest'])
    chunks=list(database.offline_chunks.find({'upload_id':ident}).sort('index',1))
    if [c['index'] for c in chunks]!=list(range(len(m.chunk_hashes))):raise HTTPException(409,'missing_chunks')
    records=[r for c in chunks for r in c['records']]
    if len(records)!=m.event_count or len({r['event_id'] for r in records})!=len(records):raise HTTPException(409,'event_count_or_id_conflict')
    if sorted(r['sequence'] for r in records)!=list(range(m.first_sequence,m.first_sequence+m.event_count)):
        raise HTTPException(409,'sequence_gap_or_reuse')
    database.offline_uploads.update_one({'_id':ident,'state':'receiving'},{'$set':{'state':'queued','sealed_at':now()}})
    # Notification only: Mongo is the durable authority, so Kafka outage never loses an accepted upload.
    notified=False
    try:
        from collector import send
        send(TOPIC,ident,{'upload_id':ident,'manifest_hash':job['manifest_hash']});notified=True
    except Exception:pass
    return {'upload_id':ident,'durably_received':True,'state':upload(database,ident)['state'],
            'notification_sent':notified,'meaning':'receipt only; remote DB completion must be checked separately'}


@router.get('/uploads/{upload_id}')
def status(upload_id:UUID,x_api_key:str=Header(default='')):
    auth(x_api_key);database=db();ident=str(upload_id);job=upload(database,ident)
    chunks=list(database.offline_chunks.find({'upload_id':ident},{'index':1,'records.event_id':1}))
    ids=[r['event_id'] for c in chunks for r in c['records']]
    states={}
    if ids:
        for r in database.remote_event_outbox.aggregate([{'$match':{'_id':{'$in':ids}}},{'$group':{'_id':'$state','n':{'$sum':1}}}]):
            states[r['_id']]=r['n']
    complete=job['state']=='staged' and job.get('confirmed_events')==job['manifest']['event_count'] and bool(job.get('delivery_confirmed_at'))
    return {'upload_id':ident,'state':'completed' if complete else job['state'],
      'received_chunks':sorted(c['index'] for c in chunks),'expected_chunks':len(job['manifest']['chunk_hashes']),
      'delivery_states':states,'remote_complete':complete,'staged_events':job.get('stage_cursor',0),
      'history_ready':job['state']=='staged','reason':job.get('reason')}
