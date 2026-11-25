"""Single, fenced batch Spark worker. Notification Kafka is not the receipt ledger."""
import json,os,sys,threading,time,uuid
from datetime import datetime,timedelta,timezone
sys.path.insert(0,'/app');sys.path.insert(0,'/opt/nodeverse')
from pymongo import ReturnDocument,UpdateOne
from pymongo.errors import DuplicateKeyError
from common.db import local_mongo
from remote.outbox import stage
import tables as tb

def now():return datetime.now(timezone.utc)

class Processor:
    def __init__(self,spark,database=None):
        self.spark=spark;self.db=database if database is not None else local_mongo()
        self.owner=uuid.uuid4().hex;self.stop=threading.Event();self.lost=threading.Event()
        self.next_stage=0.0
        self.lease_seconds=max(15,int(os.getenv('OFFLINE_LEASE_SECONDS','120')))
        self.rate=max(1,min(200,int(os.getenv('OFFLINE_STAGE_RATE','20'))))
        self.limit=max(1,min(1000,int(os.getenv('OFFLINE_QUEUE_LIMIT','200'))))
    def acquire(self):
        try:
            row=self.db.offline_locks.find_one_and_update({'_id':'processor','$or':[
                {'owner':self.owner},{'expires_at':{'$lte':now()}}]},
                {'$set':{'owner':self.owner,'expires_at':now()+timedelta(seconds=self.lease_seconds)}},upsert=True,return_document=ReturnDocument.AFTER)
            return row['owner']==self.owner
        except DuplicateKeyError:return False
    def check(self):
        if self.lost.is_set() or not self.db.offline_locks.find_one({'_id':'processor','owner':self.owner,'expires_at':{'$gt':now()}}):
            raise RuntimeError('offline_processor_lease_lost')
    def update(self,ident,fields):
        self.check()
        result=self.db.offline_uploads.update_one({'_id':ident,'worker_owner':self.owner,'state':'processing'},{'$set':fields})
        if result.matched_count!=1:raise RuntimeError('offline_job_ownership_lost')
    def heartbeat(self):
        while not self.stop.wait(min(10,self.lease_seconds/3)):
            try:
                if self.db.offline_locks.update_one({'_id':'processor','owner':self.owner},
                  {'$set':{'expires_at':now()+timedelta(seconds=self.lease_seconds)}}).matched_count!=1:self.lost.set();return
            except Exception:self.lost.set();return
    def records(self,job):
        rows=[r for c in self.db.offline_chunks.find({'upload_id':job['_id']}).sort('index',1) for r in c['records']]
        if len(rows)!=job['manifest']['event_count']:raise ValueError('stored_chunk_count_mismatch')
        return sorted(rows,key=lambda r:r['sequence'])
    def path(self,name):return tb.path('offline.'+name)
    def merge(self,name,source,keys):
        from delta.tables import DeltaTable
        self.check();path=self.path(name)
        if not DeltaTable.isDeltaTable(self.spark,path):
            writer=source.limit(0).write.format('delta').mode('error')
            if 'event_date' in source.columns:writer=writer.partitionBy('event_date')
            writer.save(path)
        condition=' AND '.join('t.'+k+' = s.'+k for k in keys)
        if 'event_date' in source.columns:
            dates=[str(r[0]) for r in source.select('event_date').distinct().collect()]
            condition+=' AND t.event_date IN ('+','.join("'"+d+"'" for d in dates)+')'
        # Keys include immutable original play date. Never use the online seven-day lookback here.
        DeltaTable.forPath(self.spark,path).alias('t').merge(source.alias('s'),condition).whenNotMatchedInsertAll().execute()
    def bronze(self,job,rows):
        from pyspark.sql import types as T
        schema=T.StructType([T.StructField(k,T.StringType()) for k in ['event_id','payload_hash','value','upload_id','event_date']])
        data=[(r['event_id'],r['payload_hash'],json.dumps(r),job['_id'],r['occurred_at'][:10]) for r in rows]
        self.merge('bronze_learning',self.spark.createDataFrame(data,schema),['event_date','event_id'])
    def publish_history(self,rows):
        from pyspark.sql import functions as F
        source=(self.spark.read.schema(tb.LEARNING_JSON).json(self.spark.sparkContext.parallelize([json.dumps(r) for r in rows]))
          .withColumn('occurred_at',F.to_timestamp('occurred_at')).withColumn('received_at',F.to_timestamp('received_at'))
          .withColumn('event_time',F.col('occurred_at')).withColumn('event_date',F.to_date('occurred_at')))
        for key,typ in tb.KAFKA_POS:source=source.withColumn(key,F.lit(None).cast(typ))
        source=source.select(tb.SCHEMAS['silver.learning_events'][0].fieldNames())
        self.merge('silver_learning',source,['event_date','event_id'])
        dates=sorted({r['occurred_at'][:10] for r in rows})
        history=self.spark.read.format('delta').load(self.path('silver_learning')).where(F.col('event_date').isin(dates))
        # An explicit offline-only daily aggregate. Never rewrite live Gold or failure-spike alerts.
        daily=(history.withColumn('play_date',F.to_date('occurred_at')).groupBy('play_date','player_id','minigame_id')
          .agg(F.count('*').alias('events'),F.sum(F.when(F.col('event_type')=='attempt_started',1).otherwise(0)).alias('attempts'),
               F.sum(F.when(F.col('event_type')=='attempt_succeeded',1).otherwise(0)).alias('successes')))
        operations=[]
        for row in daily.collect():
            d=row.asDict();d['play_date']=str(d['play_date']);d['updated_at']=now();d['scope']='offline_only'
            ident=d['play_date']+':'+d['player_id']+':'+d['minigame_id']
            operations.append(UpdateOne({'_id':ident},{'$set':d},upsert=True))
        self.check()
        if operations:self.db.offline_play_daily.bulk_write(operations,ordered=False)
    def process(self,job):
        self.check();rows=self.records(job);ident=job['_id'];ids=[r['event_id'] for r in rows]
        if job.get('bronze_done') is not True:
            self.bronze(job,rows);self.update(ident,{'bronze_done':True})
        known={r['_id']:r for r in self.db.remote_event_outbox.find({'_id':{'$in':ids}},{'payload_hash':1,'state':1})}
        if any(r['event_id'] in known and known[r['event_id']]['payload_hash']!=r['payload_hash'] for r in rows):
            raise ValueError('existing_event_content_conflict')
        failed={r['state'] for r in known.values()} & {'blocked','quarantined','parked'}
        if failed:raise ValueError('delivery_requires_review:'+','.join(sorted(failed)))
        if len(known)==len(rows) and all(r['state']=='stored' for r in known.values()):
            self.publish_history(rows);self.check()
            self.update(ident,{'state':'staged','finished_at':now(),'delivery_confirmed_at':now(),'confirmed_events':len(rows)});return
        live=self.db.remote_event_outbox.count_documents({'state':{'$in':['pending','processing','retrying']},'delivery_lane':{'$ne':'offline'}},limit=1)
        queued=self.db.remote_event_outbox.count_documents({'delivery_lane':'offline','state':{'$in':['pending','processing','retrying','waiting_context']}},limit=self.limit)
        cursor=job.get('stage_cursor',0)
        if not live and queued<self.limit and cursor<len(rows) and time.monotonic()>=self.next_stage:
            count=min(self.rate,self.limit-queued,len(rows)-cursor)
            stage(rows[cursor:cursor+count],db=self.db,lane='offline');cursor+=count
            self.next_stage=time.monotonic()+count/self.rate
        self.check()
        self.update(ident,{'state':'queued','stage_cursor':cursor,'next_attempt_at':now()+timedelta(seconds=5 if cursor>=len(rows) else 1)})
    def tick(self):
        self.check()
        job=self.db.offline_uploads.find_one_and_update({'state':{'$in':['queued','retrying']},'next_attempt_at':{'$lte':now()}},
            {'$set':{'state':'processing','worker_owner':self.owner},'$inc':{'attempts':1}},
            sort=[('next_attempt_at',1),('created_at',1)],return_document=ReturnDocument.AFTER)
        if not job:return False
        try:self.process(job)
        except ValueError as e:
            self.update(job['_id'],{'state':'blocked','reason':str(e)[:160]})
        except Exception as e:
            self.update(job['_id'],{'state':'retrying','reason':type(e).__name__,'next_attempt_at':now()+timedelta(seconds=10)})
            print(json.dumps({'task':'offline_retry','error':type(e).__name__}),flush=True)
        return True

def main():
    from confluent_kafka import Consumer
    spark=tb.spark_session('nodeverse-offline-batch',2);processor=Processor(spark)
    deadline=time.monotonic()+processor.lease_seconds+30
    while not processor.acquire():
        if time.monotonic()>deadline:raise SystemExit('another offline processor owns this database')
        time.sleep(2)
    threading.Thread(target=processor.heartbeat,daemon=True).start()
    processor.db.offline_uploads.update_many({'state':'processing'},{'$set':{'state':'retrying','next_attempt_at':now()}})
    consumer=Consumer({'bootstrap.servers':os.environ['KAFKA_BOOTSTRAP'],'group.id':'nv-offline-notifications-v1',
       'enable.auto.commit':False,'auto.offset.reset':'earliest','socket.timeout.ms':5000})
    consumer.subscribe(['nv.offline.learning.v1'])
    try:
        while True:
            processor.check()
            try:
                message=consumer.poll(.1)
                if message and not message.error():consumer.commit(message=message,asynchronous=True)
            except Exception:pass  # notifications may replay; Mongo still owns queued work
            if not processor.tick():time.sleep(.5)
    finally:
        processor.stop.set();consumer.close();processor.db.offline_locks.delete_one({'_id':'processor','owner':processor.owner});spark.stop()

if __name__=='__main__':main()
