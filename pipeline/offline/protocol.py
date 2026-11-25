"""Versioned compact codebook and bounded, canonical offline protocol."""
import gzip,hashlib,json,zlib
from datetime import datetime,timedelta,timezone
from uuid import UUID
from pathlib import Path
from pydantic import BaseModel,ConfigDict,Field
import contract

TOPIC='nv.offline.learning.v1'
MAX_COMPRESSED=128*1024
MAX_EXPANDED=256*1024
MAX_EVENTS=2000
# Never derive deployed codes from enum ordering. Version 1 remains immutable.
CODEBOOK=json.loads(Path(__file__).with_name('codebook-v1.json').read_text(encoding='utf-8'))
EVENT_CODES={int(k):v for k,v in CODEBOOK['event_types'].items()}
OP_CODES={int(k):v for k,v in CODEBOOK['operations'].items()}


class Manifest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    installation_id:UUID
    player_id:str=Field(min_length=1,max_length=128)
    session_id:UUID
    first_sequence:int=Field(ge=1)
    event_count:int=Field(ge=1,le=MAX_EVENTS)
    chunk_hashes:list[str]=Field(min_length=1,max_length=64)
    dictionary_version:int=Field(default=1,ge=1,le=1)

    def digest(self):return digest(self.model_dump(mode='json'))


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def decode(raw,encoding='identity'):
    if len(raw)>MAX_COMPRESSED:raise ValueError('compressed_body_limit')
    if encoding=='gzip':
        decoder=zlib.decompressobj(16+zlib.MAX_WBITS)
        try:raw=decoder.decompress(raw,MAX_EXPANDED+1)
        except zlib.error:raise ValueError('invalid_gzip')
        if len(raw)>MAX_EXPANDED or decoder.unconsumed_tail or not decoder.eof or decoder.unused_data:
            raise ValueError('invalid_or_oversized_gzip')
    elif encoding!='identity':raise ValueError('unsupported_content_encoding')
    if len(raw)>MAX_EXPANDED:raise ValueError('expanded_body_limit')
    body=json.loads(raw)
    if not isinstance(body,dict) or set(body)!={'events'} or not isinstance(body['events'],list):
        raise ValueError('chunk_must_contain_events_only')
    if not 1<=len(body['events'])<=200:raise ValueError('chunk_event_count')
    return body


def canonical(body,manifest,received):
    records=[]
    for original in body['events']:
        if not isinstance(original,dict):raise ValueError('invalid_event')
        event=dict(original)
        event.setdefault('player_id',manifest.player_id);event.setdefault('session_id',str(manifest.session_id))
        if event['player_id']!=manifest.player_id or event['session_id']!=str(manifest.session_id):
            raise ValueError('manifest_identity_mismatch')
        if isinstance(event.get('event_type'),bool):raise ValueError('unknown_event_code')
        if isinstance(event.get('event_type'),int):
            if event['event_type'] not in EVENT_CODES:raise ValueError('unknown_event_code')
            event['event_type']=EVENT_CODES[event['event_type']]
        if isinstance(event.get('details'),dict):
            details=dict(event['details']);operation=details.get('operation')
            if isinstance(operation,bool):raise ValueError('unknown_operation_code')
            if isinstance(operation,int):
                if operation not in OP_CODES:raise ValueError('unknown_operation_code')
                details['operation']=OP_CODES[operation]
            event['details']=details
        model=contract.LearningEventV2.model_validate(event)
        if model.occurred_at<received-timedelta(days=90):raise ValueError('offline_age_exceeds_90_days')
        # Same canonical hash as the online route. Never refresh occurred_at to get around its age policy.
        records.append(contract.to_record(model,received))
    return records
