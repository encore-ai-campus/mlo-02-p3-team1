"""Explicitly create the offline notification topic and durable import indexes."""
import os
from confluent_kafka.admin import AdminClient,NewTopic
from common.db import local_mongo
from offline.protocol import TOPIC

def main():
    database=local_mongo()
    database.offline_chunks.create_index([('upload_id',1),('index',1)],unique=True)
    database.offline_uploads.create_index([('state',1),('next_attempt_at',1)])
    database.offline_uploads.create_index([('installation_id',1),('state',1)])
    admin=AdminClient({'bootstrap.servers':os.environ['KAFKA_BOOTSTRAP']})
    if TOPIC not in admin.list_topics(timeout=10).topics:
        admin.create_topics([NewTopic(TOPIC,num_partitions=3,replication_factor=3,
          config={'min.insync.replicas':'2','retention.ms':str(7*86400000)})])[TOPIC].result(20)
    print('offline indexes/topic ready; upload/ID ledger has no TTL')

if __name__=='__main__':main()
