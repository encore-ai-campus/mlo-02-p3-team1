"""Generate compose.json (standard library only). Run: python build_compose.py

Services: kafka-1..3 (KRaft, RF 3, min ISR 2), topic-init (5 contract topics),
collector (/v2/events), spark (delta_stream.py), mongo (nodeverse_logs).
"""
import json
from pathlib import Path

from topics import RETENTION_MS, TOPICS

KAFKA_IMAGE = 'apache/kafka:3.9.1'
BOOTSTRAP = 'kafka-1:9092,kafka-2:9092,kafka-3:9092'
# helper modules shipped to the Spark driver and Python workers (delta_stream.py is the entry point)
SPARK_MODULES = ['tables.py', 'audit_state.py', 'sinks.py', 'bronze.py', 'silver.py', 'gold.py', 'periodic.py']
SPARK_PACKAGES = 'org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3,io.delta:delta-spark_2.12:3.2.1'

services = {}
volumes = {'lake': {}, 'mongo': {}, 'ivy': {}}
for i in range(1, 4):
    name = f'kafka-{i}'
    volumes[name] = {}
    services[name] = {
        'image': KAFKA_IMAGE, 'hostname': name, 'restart': 'unless-stopped',
        'environment': {
            'CLUSTER_ID': 'MkU3OEVBNTcwNTJENDM2Qk',
            'KAFKA_NODE_ID': i,
            'KAFKA_PROCESS_ROLES': 'broker,controller',
            'KAFKA_CONTROLLER_QUORUM_VOTERS': '1@kafka-1:9093,2@kafka-2:9093,3@kafka-3:9093',
            'KAFKA_LISTENERS': 'PLAINTEXT://:9092,CONTROLLER://:9093',
            'KAFKA_ADVERTISED_LISTENERS': f'PLAINTEXT://{name}:9092',
            'KAFKA_LISTENER_SECURITY_PROTOCOL_MAP': 'CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT',
            'KAFKA_CONTROLLER_LISTENER_NAMES': 'CONTROLLER',
            'KAFKA_INTER_BROKER_LISTENER_NAME': 'PLAINTEXT',
            'KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR': 3,
            'KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR': 3,
            'KAFKA_TRANSACTION_STATE_LOG_MIN_ISR': 2,
            'KAFKA_MIN_INSYNC_REPLICAS': 2,
            'KAFKA_AUTO_CREATE_TOPICS_ENABLE': 'false',
            'KAFKA_LOG_DIRS': '/var/lib/kafka/data',
            'KAFKA_HEAP_OPTS': '-Xms256m -Xmx512m'},
        'volumes': [f'{name}:/var/lib/kafka/data'],
        # CPU review item 1: a JVM admin client every 10 s peaked at ~150 % per broker. The healthcheck now only
        # tests that the listener accepts connections; topic-init below proves the Kafka API with retries.
        'healthcheck': {'test': ['CMD', 'nc', '-z', 'localhost', '9092'],
                        'interval': '10s', 'timeout': '3s', 'retries': 18, 'start_period': '30s'}}

create = ' && '.join(
    f'/opt/kafka/bin/kafka-topics.sh --bootstrap-server {BOOTSTRAP} --create --if-not-exists --topic {t} '
    f'--partitions {p} --replication-factor 3 --config min.insync.replicas=2 --config retention.ms={RETENTION_MS}'
    for t, p in TOPICS.items())
# An open port is not a working cluster (metadata quorum, 3 registered brokers for RF 3), so the whole create step
# is retried until it succeeds; topic-init exits non-zero after ~3 minutes and nothing that needs topics starts.
services['topic-init'] = {
    'image': KAFKA_IMAGE,
    'depends_on': {f'kafka-{i}': {'condition': 'service_healthy'} for i in range(1, 4)},
    'entrypoint': ['/bin/bash', '-ec'],
    'command': ['for attempt in $$(seq 1 36); do '
                f'if {{ {create}; }}; then '
                f'/opt/kafka/bin/kafka-topics.sh --bootstrap-server {BOOTSTRAP} --describe; exit 0; fi; '
                'echo "kafka not ready (attempt $$attempt/36), retrying in 5s" >&2; sleep 5; done; exit 1']}

services['collector'] = {
    'build': {'context': '.', 'dockerfile': 'Dockerfile'}, 'restart': 'unless-stopped',
    'ports': ['${COLLECTOR_BIND:-127.0.0.1}:${COLLECTOR_PORT:-8000}:8000'],
    'environment': {'INGEST_KEY': '${INGEST_KEY:?Set INGEST_KEY in .env}', 'KAFKA_BOOTSTRAP': BOOTSTRAP, 'MONGO_URI': 'mongodb://mongo:27017', 'MONGO_DB': 'nodeverse_logs'},
    'depends_on': {'topic-init': {'condition': 'service_completed_successfully'}},
    'healthcheck': {'test': ['CMD', 'python', '-c',
                            'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=3)'],
                    'interval': '10s', 'timeout': '5s', 'retries': 6, 'start_period': '15s'}}

services['mongo'] = {
    'image': 'mongo:7.0.16', 'restart': 'unless-stopped',
    'ports': ['${MONGO_BIND:-127.0.0.1}:${MONGO_PORT:-27017}:27017'],
    'volumes': ['mongo:/data/db'],
    # CPU review item 1: mongosh starts a Node.js runtime per check (~47 % peak). mongod opens 27017 only after
    # storage recovery, so a TCP connect is a cheap readiness signal; clients retry pings themselves.
    'healthcheck': {'test': ['CMD', 'bash', '-c', 'exec 3<>/dev/tcp/127.0.0.1/27017'],
                    'interval': '10s', 'timeout': '3s', 'retries': 6, 'start_period': '10s'}}

services['spark'] = {
    'build': {'context': '.', 'dockerfile': 'Dockerfile.spark'}, 'user': '0:0', 'restart': 'unless-stopped',
    'entrypoint': ['/opt/spark/bin/spark-submit'],
    'command': ['--master', 'local[${SPARK_CORES:-4}]', '--driver-memory', '${SPARK_DRIVER_MEMORY:-2g}',
                '--conf', 'spark.jars.ivy=/ivy',
                '--packages', SPARK_PACKAGES,
                '--conf', 'spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension',
                '--conf', 'spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog',
                '--conf', 'spark.sql.warehouse.dir=/data/delta',
                '--conf', 'spark.sql.session.timeZone=UTC',
                '--py-files', ','.join('/app/' + m for m in SPARK_MODULES),
                '/app/delta_stream.py'],
    'environment': {'KAFKA_BOOTSTRAP': BOOTSTRAP, 'MONGO_URI': 'mongodb://mongo:27017', 'MONGO_DB': 'nodeverse_logs',
                    'REMOTE_EXPORT_ENABLED': '${REMOTE_EXPORT_ENABLED:-0}', 'BRONZE_TRIGGER': '${BRONZE_TRIGGER:-5 seconds}', 'STAGE_TRIGGER': '${STAGE_TRIGGER:-1 second}',
                    'SHUFFLE_PARTITIONS': '${SHUFFLE_PARTITIONS:-4}', 'MAX_OFFSETS_PER_TRIGGER': '${MAX_OFFSETS_PER_TRIGGER:-10000}',
                    'LAKE_ROOT': '/data/delta', 'CHECKPOINT_ROOT': '/data/checkpoints', 'TZ': 'UTC',
                    'INGEST_KEY': '${INGEST_KEY:?Set INGEST_KEY in .env}', 'COLLECTOR_URL': 'http://collector:8000'},
    'volumes': ['./spark:/app:ro', './common:/opt/nodeverse/common:ro', './remote:/opt/nodeverse/remote:ro',
                'lake:/data', 'ivy:/ivy'],
    'depends_on': {'topic-init': {'condition': 'service_completed_successfully'},
                   'mongo': {'condition': 'service_healthy'}}}

services['remote-writer'] = {
    'build': {'context': '.', 'dockerfile': 'Dockerfile'},
    'profiles': ['remote'], 'restart': 'unless-stopped',
    'command': ['python', '-m', 'remote.worker'],
    'env_file': '.env.remote',
    'environment': {'MONGO_URI': 'mongodb://mongo:27017', 'MONGO_DB': 'nodeverse_logs',
                    'REMOTE_CONTEXT_PATH': '/run/private/remote-context.json'},
    'volumes': ['./.env.remote-context.json:/run/private/remote-context.json:ro'],
    'depends_on': {'mongo': {'condition': 'service_healthy'}}}

Path(__file__).with_name('compose.json').write_text(
    json.dumps({'name': 'nodeverse-dev', 'services': services, 'volumes': volumes}, indent=2) + '\n', encoding='utf-8')
print('wrote compose.json')
