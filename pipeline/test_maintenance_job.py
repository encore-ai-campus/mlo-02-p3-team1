import json
import pytest
from tools.maintenance_job import execute,SPARK
from observatory.sampler import findings


def info():
    return {'Config':{'Labels':{'com.docker.compose.project':'nodeverse-v2-live'},'Cmd':['/app/delta_stream.py'],'Env':[]},
            'State':{'Running':True},'Image':'test-image','Mounts':[], 'NetworkSettings':{'Networks':{'test-net':{}}}}


@pytest.mark.parametrize('fail',[False,True])
def test_maintenance_resumes_writer_on_success_and_failure(fail):
    calls=[];states=[]
    def command(*args):
        calls.append(args)
        if args[0]=='run':
            if fail:raise RuntimeError('maintenance failed')
            return 'row-count validation passed'
        if args[0]=='inspect':return json.dumps([{'State':{'StartedAt':'2000-01-01T00:00:00.000Z'}}])
        if args[0]=='exec':return json.dumps({'updated_at':'2026-11-27T00:00:00Z','queries':[{'active':True}]*8})
        return ''
    if fail:
        with pytest.raises(RuntimeError):execute(info(),['gold.failure_alerts'],None,command,states.append)
    else:execute(info(),['gold.failure_alerts'],None,command,states.append)
    assert ('stop','-t','90',SPARK) in calls and ('start',SPARK) in calls
    assert states[-1]['state']==('failed' if fail else 'ok')


def test_resume_failure_is_not_reported_as_success():
    states=[]
    def command(*args):
        if args[0]=='start':raise RuntimeError('failed to start')
        return ''
    with pytest.raises(RuntimeError,match='resume failed'):
        execute(info(),['gold.failure_alerts'],None,command,states.append)
    assert states[-1]['state']=='resume_failed'


def test_integrity_and_maintenance_have_visible_actionable_alerts():
    base={'progress':{'state':'ok'},'mongo':{'state':'ok'},'collector':{'state':'ok'},'remote':{'state':'ok'},
          'queries':[],'queue':{'counts':{}},'operations':{'integrity':{'state':'recovery_required'},'maintenance':{'state':'failed'}}}
    assert {x['id'] for x in findings(base)}=={'remote-integrity','maintenance'}
    base['operations']['maintenance']={'state':'running','failure_unresolved':True}
    assert 'maintenance' in {x['id'] for x in findings(base)}  # retry start is not success
