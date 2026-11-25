from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import Response
import offline_gateway as gateway

def test_fixed_routes_preserve_gzip_and_reject_bad_key(monkeypatch):
    monkeypatch.setenv('INGEST_KEY','gateway-test-key-at-least-24-chars')
    monkeypatch.setenv('OFFLINE_ENABLED','1');calls=[]
    def forward(*args):calls.append(args);return Response('{}',status_code=200)
    monkeypatch.setattr(gateway,'forward',forward)
    app=FastAPI();app.include_router(gateway.router);c=TestClient(app);ident=str(uuid4())
    path='/v2/offline/uploads/'+ident+'/chunks/0'
    assert c.put(path,content=b'zip').status_code==401
    assert c.put(path,content=b'zip',headers={'X-API-Key':'gateway-test-key-at-least-24-chars','Content-Encoding':'gzip'}).status_code==200
    assert calls==[(path,'PUT',b'zip','gzip')]
    assert c.put('/v2/offline/uploads/not-a-uuid',json={}).status_code==422
