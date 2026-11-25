"""Reference EXE-side SQLite outbox; no game-source edits or credential storage."""
import gzip,json,sqlite3,uuid,random,time,contextlib
from datetime import datetime,timezone
import contract
from pathlib import Path
from offline.protocol import Manifest,digest,canonical,MAX_COMPRESSED,MAX_EXPANDED,MAX_EVENTS


class Queue:
    def __init__(self,path,max_bytes=64*1024*1024):
        self.path=Path(path);self.max_bytes=max_bytes
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.executescript('''PRAGMA journal_mode=WAL;PRAGMA synchronous=FULL;
              CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY,manifest TEXT,state TEXT);
              CREATE TABLE IF NOT EXISTS chunks(upload_id TEXT,n INTEGER,body BLOB,acked INTEGER DEFAULT 0,PRIMARY KEY(upload_id,n));
              CREATE TABLE IF NOT EXISTS ids(event_id TEXT PRIMARY KEY,hash TEXT,upload_id TEXT);
              CREATE TABLE IF NOT EXISTS pending(event_id TEXT PRIMARY KEY,session_id TEXT,sequence INTEGER,body TEXT,hash TEXT,UNIQUE(session_id,sequence));
              CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);''')
            c.execute('INSERT OR IGNORE INTO metadata VALUES(?,?)',('installation_id',str(uuid.uuid4())))
            self.installation_id=c.execute('SELECT value FROM metadata WHERE key=?',('installation_id',)).fetchone()[0]
    @contextlib.contextmanager
    def connect(self):
        c=sqlite3.connect(self.path,timeout=10);c.execute('PRAGMA synchronous=FULL')
        try:
            with c:yield c
        finally:c.close()
    def append(self,event):
        """Persist each canonical event before preparing network windows; run I/O off the game render thread."""
        model=contract.LearningEventV2.model_validate(event)
        event=contract.to_record(model,datetime.now(timezone.utc));event.pop('received_at');event.pop('payload_hash')
        payload=json.dumps(event,sort_keys=True,separators=(',',':'),ensure_ascii=False);hash_=contract.body_hash(event)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            existing=c.execute('SELECT hash FROM ids WHERE event_id=?',(event['event_id'],)).fetchone()
            pending=c.execute('SELECT hash FROM pending WHERE event_id=?',(event['event_id'],)).fetchone()
            if existing or pending:
                if (existing or pending)[0]!=hash_:raise ValueError('local event content conflict')
                return
            used=c.execute('SELECT COALESCE(SUM(length(CAST(body AS BLOB))),0) FROM pending').fetchone()[0]
            used+=c.execute('SELECT COALESCE(SUM(length(body)),0) FROM chunks').fetchone()[0]
            if used+len(payload.encode())>self.max_bytes:raise ValueError('local queue payload quota; preserve existing events')
            c.execute('INSERT INTO pending VALUES(?,?,?,?,?)',(event['event_id'],event['session_id'],event['sequence'],payload,hash_))
    def prepare(self,session_id,limit=MAX_EVENTS):
        """Move one contiguous window from per-event storage into immutable chunks atomically."""
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            rows=c.execute('SELECT event_id,body FROM pending WHERE session_id=? ORDER BY sequence LIMIT ?',
              (session_id,max(1,min(MAX_EVENTS,limit)))).fetchall()
            if not rows:return None
            return self.enqueue(self.installation_id,[json.loads(r[1]) for r in rows],_connection=c,_pending_ids=[r[0] for r in rows])
    def enqueue(self,installation_id,events,_connection=None,_pending_ids=None):
        if not 1<=len(events)<=MAX_EVENTS:raise ValueError('split into windows of at most 2000 events')
        events=sorted(events,key=lambda e:e['sequence']);first=events[0]
        if [e['sequence'] for e in events]!=list(range(first['sequence'],first['sequence']+len(events))):raise ValueError('sequence gap')
        if any(e['session_id']!=first['session_id'] or e['player_id']!=first['player_id'] for e in events):raise ValueError('one player/session per upload')
        bodies=[];pending=[]
        def encoded(rows):return json.dumps({'events':rows},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        for e in events:
            candidate=pending+[e];raw=encoded(candidate);compressed=gzip.compress(raw,mtime=0)
            if pending and (len(candidate)>200 or len(raw)>MAX_EXPANDED or len(compressed)>MAX_COMPRESSED):
                bodies.append(encoded(pending));pending=[e]
            else:pending=candidate
            if len(encoded(pending))>MAX_EXPANDED or len(gzip.compress(encoded(pending),mtime=0))>MAX_COMPRESSED:raise ValueError('single event too large')
        if pending:bodies.append(encoded(pending))
        manifest=Manifest(installation_id=installation_id,player_id=first['player_id'],session_id=first['session_id'],
          first_sequence=first['sequence'],event_count=len(events),chunk_hashes=[digest(json.loads(b)) for b in bodies])
        hashes={r['event_id']:r['payload_hash'] for r in canonical({'events':events},manifest,datetime.now(timezone.utc))}
        ident=str(uuid.uuid4());compressed=[gzip.compress(b,mtime=0) for b in bodies]
        with (self.connect() if _connection is None else contextlib.nullcontext(_connection)) as c:
            if _connection is None:c.execute('BEGIN IMMEDIATE')
            if _pending_ids:c.executemany('DELETE FROM pending WHERE event_id=?',[(i,) for i in _pending_ids])
            used=c.execute('SELECT COALESCE(SUM(length(body)),0) FROM chunks').fetchone()[0]
            used+=c.execute('SELECT COALESCE(SUM(length(CAST(body AS BLOB))),0) FROM pending').fetchone()[0]
            if used+sum(map(len,compressed))>self.max_bytes:raise ValueError('local queue payload quota; preserve queued data')
            # Never regenerate identity on retry; reusing an event in a different upload is explicit, not accidental.
            if len({e['event_id'] for e in events})!=len(events):raise ValueError('duplicate event id')
            for e in events:
                if c.execute('SELECT 1 FROM ids WHERE event_id=?',(e['event_id'],)).fetchone():raise ValueError('event already queued; resume original upload')
            c.execute('INSERT INTO uploads VALUES(?,?,?)',(ident,json.dumps(manifest.model_dump(mode='json')),'pending'))
            c.executemany('INSERT INTO chunks(upload_id,n,body) VALUES(?,?,?)',[(ident,i,b) for i,b in enumerate(compressed)])
            c.executemany('INSERT INTO ids VALUES(?,?,?)',[(e['event_id'],hashes[e['event_id']],ident) for e in events])
        return ident
    def sync(self,ident,http,key):
        with self.connect() as c:
            row=c.execute('SELECT manifest,state FROM uploads WHERE id=?',(ident,)).fetchone()
            if not row:raise ValueError('unknown upload')
            chunks=c.execute('SELECT n,body FROM chunks WHERE upload_id=? ORDER BY n',(ident,)).fetchall()
        headers={'X-API-Key':key};path='/v2/offline/uploads/'+ident
        r=http.put(path,json=json.loads(row[0]),headers=headers);r.raise_for_status()
        r=http.get(path,headers=headers);r.raise_for_status();status=r.json()
        for n,body in chunks:
            if n not in status['received_chunks']:
                r=http.put(path+'/chunks/'+str(n),content=body,headers={**headers,'Content-Encoding':'gzip','Content-Type':'application/json'})
                r.raise_for_status()
                if not r.json().get('durably_received'):raise RuntimeError('receipt missing')
            with self.connect() as c:c.execute('UPDATE chunks SET acked=1 WHERE upload_id=? AND n=?',(ident,n))
        r=http.post(path+'/seal',headers=headers);r.raise_for_status()
        r=http.get(path,headers=headers);r.raise_for_status();status=r.json()
        with self.connect() as c:c.execute('UPDATE uploads SET state=? WHERE id=?',('completed' if status['remote_complete'] else 'received',ident))
        return status
    def prune_completed(self,ident):
        with self.connect() as c:
            state=c.execute('SELECT state FROM uploads WHERE id=?',(ident,)).fetchone()
            if not state or state[0]!='completed':raise ValueError('remote completion not confirmed')
            c.execute('DELETE FROM chunks WHERE upload_id=?',(ident,))
    def sync_with_retry(self,ident,http,key,attempts=5):
        import httpx
        for attempt in range(attempts):
            try:return self.sync(ident,http,key)
            except httpx.HTTPStatusError as e:
                if e.response.status_code not in (429,502,503,504):raise
                try:delay=min(60,max(1,float(e.response.headers.get('Retry-After',2**attempt))))
                except ValueError:delay=min(60,2**attempt)
            except httpx.TransportError:delay=min(60,2**attempt)
            if attempt==attempts-1:raise RuntimeError('sync retry limit; keep SQLite and resume later')
            time.sleep(delay+random.uniform(0,min(1,delay*.1)))
