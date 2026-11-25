"""Optional fixed-route adapter for the existing legacy gateway; not an open proxy."""
import os,secrets,urllib.request,urllib.error
from urllib.parse import urlsplit
from uuid import UUID
from fastapi import APIRouter,Header,HTTPException,Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

router=APIRouter(prefix='/v2/offline')
LIMIT=128*1024
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
def auth(key):
    expected=os.getenv('INGEST_KEY','')
    if len(expected)<24 or not secrets.compare_digest(key.encode(),expected.encode()):raise HTTPException(401,'Invalid ingestion key')
    if os.getenv('OFFLINE_ENABLED','0')!='1':raise HTTPException(503,'offline_import_disabled')
def forward(path,method,body=None,encoding='identity'):
    origin=os.getenv('V2_COLLECTOR_URL','').rstrip('/');u=urlsplit(origin)
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.path or u.query or u.fragment:
        raise HTTPException(503,'collector origin is not configured')
    key=os.getenv('V2_INGEST_KEY','')
    if not key:raise HTTPException(503,'upstream authentication missing')
    req=urllib.request.Request(origin+path,data=body,method=method,headers={'Content-Type':'application/json','Content-Encoding':encoding,'X-API-Key':key})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=30) as r:
            return Response(r.read(1024*1024),status_code=r.status,media_type='application/json')
    except urllib.error.HTTPError as e:
        headers={'Retry-After':e.headers['Retry-After']} if e.headers.get('Retry-After') else {}
        return Response(e.read(1024*1024),status_code=e.code,media_type='application/json',headers=headers)
    except (OSError,TimeoutError):raise HTTPException(503,'retry identical upload ID/chunks',headers={'Retry-After':'5'})
async def body(request):
    raw=bytearray()
    async for part in request.stream():
        if len(raw)+len(part)>LIMIT:raise HTTPException(413,'body limit')
        raw.extend(part)
    return bytes(raw)
@router.put('/uploads/{upload_id}')
async def create(upload_id:UUID,request:Request,x_api_key:str=Header(default='')):
    auth(x_api_key);return await run_in_threadpool(forward,'/v2/offline/uploads/'+str(upload_id),'PUT',await body(request))
@router.put('/uploads/{upload_id}/chunks/{index}')
async def chunk(upload_id:UUID,index:int,request:Request,x_api_key:str=Header(default='')):
    auth(x_api_key)
    if not 0<=index<64:raise HTTPException(422,'chunk index')
    return await run_in_threadpool(forward,'/v2/offline/uploads/'+str(upload_id)+'/chunks/'+str(index),'PUT',await body(request),request.headers.get('content-encoding','identity'))
@router.post('/uploads/{upload_id}/seal')
def seal(upload_id:UUID,x_api_key:str=Header(default='')):
    auth(x_api_key);return forward('/v2/offline/uploads/'+str(upload_id)+'/seal','POST',b'')
@router.get('/uploads/{upload_id}')
def status(upload_id:UUID,x_api_key:str=Header(default='')):
    auth(x_api_key);return forward('/v2/offline/uploads/'+str(upload_id),'GET')
