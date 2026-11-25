"""Start the isolated driver and sample Docker resources until that experiment exits."""
import argparse,json,subprocess,time
from datetime import datetime,timezone
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);a=p.parse_args()
    out=Path(a.output).resolve(); cfg=out/'compose.private.json'; data=json.loads(cfg.read_text());project=data['name']
    assert project.startswith('nv-baseline-')
    def call(*args):return subprocess.check_output(['docker',*args],text=True).strip()
    call('compose','-f',str(cfg),'up','-d','driver')
    name=project+'-driver-1';count=0
    with (out/'resources.jsonl').open('w') as f:
        while True:
            state=json.loads(call('inspect',name))[0]['State']
            rows=[json.loads(line) for line in call('stats','--no-stream','--format','{{json .}}').splitlines()]
            f.write(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'containers':rows})+'\n');f.flush()
            if count%3==0:
                lines=call('logs','--tail','1',name)
                print(json.dumps({'sample':count,'running':state['Running'],'driver_tail':lines}),flush=True)
            count+=1
            if not state['Running']:
                print(json.dumps({'exit_code':state['ExitCode'],'samples':count}),flush=True)
                raise SystemExit(state['ExitCode'])
            time.sleep(5)

if __name__=='__main__':main()
