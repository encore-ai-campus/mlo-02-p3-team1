"""One explicit metadata-only index setup. Default prints the plan without mutation."""
import argparse,json
from common.db import local_mongo
from observatory.metrics import LATENCY_INDEX
KEYS=[('state',1),('completed_at',-1),('_id',1)]

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');a=p.parse_args()
 if a.execute:local_mongo().remote_event_outbox.create_index(KEYS,name=LATENCY_INDEX)
 print(json.dumps({'index':LATENCY_INDEX,'keys':KEYS,'executed':a.execute}))
if __name__=='__main__':main()
