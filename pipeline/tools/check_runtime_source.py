"""Read-only comparison of running container source against this checkout. Never prints environment secrets."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True)
    parser.add_argument('--role', choices=['spark', 'writer', 'collector'], required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.role == 'spark':
        paths = {str(p.relative_to(root)).replace('\\', '/'): '/app/' + p.name
                 for p in (root / 'spark').glob('*.py')
                 if p.stem in {'delta_stream', 'tables', 'audit_state', 'sinks', 'compaction', 'bronze', 'silver', 'gold', 'periodic'}}
        paths.update({str(p.relative_to(root)).replace('\\', '/'): '/opt/nodeverse/' + str(p.relative_to(root)).replace('\\', '/')
                      for folder in ('common', 'remote') for p in (root / folder).glob('*.py')})
    else:
        files = ['contract.py', 'collector.py'] if args.role == 'collector' else ['common/settings.py', 'remote/projection.py', 'remote/worker.py']
        paths = {p: '/app/' + p for p in files if (root / p).is_file()}
    code = ('import hashlib,json,pathlib,sys; paths=json.loads(sys.argv[1]); '
            'print(json.dumps({k:hashlib.sha256(pathlib.Path(v).read_bytes()).hexdigest() '
            'if pathlib.Path(v).is_file() else None for k,v in paths.items()}))')
    actual = json.loads(subprocess.check_output(['docker', 'exec', args.container, 'python3', '-c', code, json.dumps(paths)], text=True))
    rows = [{'file': p, 'match': actual[p] == hashlib.sha256((root / p).read_bytes()).hexdigest()}
            for p in sorted(paths)]
    result = {'container': args.container, 'role': args.role, 'all_match': all(r['match'] for r in rows), 'files': rows}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['all_match'] else 1)


if __name__ == '__main__':
    main()
