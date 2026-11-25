"""Prepare an isolated, unexposed RF3 baseline stack. Generated config contains disposable test secrets."""
import argparse, copy, json, secrets, subprocess
from pathlib import Path


def prepare(output, project):
    root = Path(__file__).resolve().parents[1]
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    dest = output / 'compose.private.json'
    if dest.exists():
        raise SystemExit('Refuse to overwrite an existing experiment')
    if not project.startswith('nv-baseline-'):
        raise SystemExit('Use an isolated nv-baseline-* project name')
    existing=subprocess.check_output(['docker','ps','-a','--filter',f'label=com.docker.compose.project={project}','--format','{{.Names}}'],text=True)
    volumes_existing=subprocess.check_output(['docker','volume','ls','--filter',f'label=com.docker.compose.project={project}','--format','{{.Name}}'],text=True)
    if existing.strip() or volumes_existing.strip():
        raise SystemExit('Project already exists; choose a new isolated project and output directory')
    original = json.loads((root / 'compose.json').read_text())
    services = {k: copy.deepcopy(v) for k, v in original['services'].items()
                if k in ['kafka-1','kafka-2','kafka-3','mongo','collector','spark','topic-init','deps-ready','remote-writer']}
    app = 'nodeverse-pipeline-current:20261125'
    key, password = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    for name, s in services.items():
        s.pop('ports', None); s.pop('profiles', None); s.pop('env_file', None); s.pop('build', None)
        if name in ('collector','topic-init','deps-ready','remote-writer'): s['image'] = app
        s['restart'] = 'no'
    services['collector']['environment']['INGEST_KEY'] = key
    services['collector']['environment']['MONGO_DB'] = 'baseline_local'
    s = services['spark']; s['image'] = 'nodeverse-v2-live-spark:latest'
    s['volumes'] = [f'{root.as_posix()}/spark:/app:ro',f'{root.as_posix()}/common:/opt/nodeverse/common:ro',
                    f'{root.as_posix()}/remote:/opt/nodeverse/remote:ro','lake:/data','ivy:/ivy',f'{output.as_posix()}:/results']
    s['command'] = ['--master','local[4]','--driver-memory','2g','--conf','spark.jars.ivy=/ivy',
      '--packages','org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3,io.delta:delta-spark_2.12:3.2.1',
      '--conf','spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension',
      '--conf','spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog',
      '--conf','spark.sql.session.timeZone=UTC','--py-files',
      ','.join('/app/'+m+'.py' for m in ('tables','audit_state','sinks','compaction','bronze','silver','gold','periodic')),
      '/app/delta_stream.py']
    s['environment'].update(INGEST_KEY=key,DEDUP_TTL_HOURS='168',SILVER_OPTIMIZATION_ENABLED='0',
      REMOTE_EXPORT_ENABLED='1',BRONZE_TRIGGER='5 seconds',STAGE_TRIGGER='1 second',
      SHUFFLE_PARTITIONS='4',COMPACT_EVERY_BATCHES='300',MAX_OFFSETS_PER_TRIGGER='10000',
      PROGRESS_PATH='/results/progress.json')
    # Resolve generated ${...} defaults explicitly; no host production env is used.
    s['environment'] = {k: v for k,v in s['environment'].items() if '${' not in str(v)}
    services['target-mongo'] = {'image':'mongo:8.0','volumes':['target-mongo:/data/db']}
    services['target-mysql'] = {'image':'mysql:8.4','environment':{'MYSQL_ROOT_PASSWORD':password,'MYSQL_DATABASE':'baseline'},
      'volumes':['target-mysql:/var/lib/mysql'],'command':['--innodb-buffer-pool-size=128M'],
      'healthcheck':{'test':['CMD-SHELL','mysqladmin ping -h localhost --silent'],'interval':'5s','timeout':'3s','retries':30}}
    env={'MONGO_URI':'mongodb://mongo:27017','MONGO_DB':'baseline_local',
      'DIRECT_MONGO_URI':'mongodb://target-mongo:27017','DIRECT_MONGO_DATABASE':'baseline_remote',
      'DIRECT_MYSQL_HOST':'target-mysql','DIRECT_MYSQL_PORT':'3306','DIRECT_MYSQL_DATABASE':'baseline',
      'DIRECT_MYSQL_USER':'root','DIRECT_MYSQL_PASSWORD':password,'REMOTE_WORKERS':'2','REMOTE_BATCH':'30',
      'REMOTE_MEMBER_CACHE_SECONDS':'0','REMOTE_DONE_TTL_DAYS':'0','REMOTE_CONTEXT_PATH':'/results/context.json'}
    s['environment']['MONGO_DB']='baseline_local'
    services['remote-writer']['environment']=env
    services['remote-writer']['volumes']=[f'{output.as_posix()}:/results:ro']
    services['remote-writer']['depends_on']['target-mysql']={'condition':'service_healthy'}
    # Bootstrap before the writer's background member-revival thread queries the table.
    services['baseline-init']={'image':app,'environment':env,'depends_on':{'target-mysql':{'condition':'service_healthy'}},
      'command':['python','-c',"import os,pymysql;c=pymysql.connect(host='target-mysql',user='root',password=os.environ['DIRECT_MYSQL_PASSWORD'],database='baseline');q=c.cursor();q.execute('CREATE TABLE IF NOT EXISTS game_members(member_id CHAR(32) PRIMARY KEY,external_member_key VARCHAR(150) UNIQUE,nickname VARCHAR(80),data_source VARCHAR(20),registered_at DATETIME)');c.commit();c.close()"]}
    services['remote-writer']['depends_on']['baseline-init']={'condition':'service_completed_successfully'}
    services['driver']={'image':app,'command':['python','/bench/tools/baseline_driver.py'],
      'environment':dict(env, INGEST_KEY=key),'volumes':[f'{root.as_posix()}:/bench:ro',f'{output.as_posix()}:/results'],
      'profiles':['test'],'depends_on':{'target-mysql':{'condition':'service_healthy'},'baseline-init':{'condition':'service_completed_successfully'}}}
    volumes={k:{} for k in ('lake','mongo','ivy','kafka-1','kafka-2','kafka-3','target-mysql','target-mongo')}
    # Reuse cached dependency jars, never the production data or checkpoints.
    volumes['ivy']={'external':True,'name':'nodeverse-v2-live_ivy'}
    dest.write_text(json.dumps({'name':project,'services':services,'volumes':volumes},indent=2),encoding='utf-8')
    (output/'context.json').write_text('{"members":{}}',encoding='utf-8')
    print(json.dumps({'project':project,'config':str(dest),'host_ports':0,'production_data_volumes':0}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);p.add_argument('--project',required=True)
    a=p.parse_args();prepare(a.output,a.project)
