#!/usr/bin/env python3
"""Authorized citation-repair continuation; default mode is entirely offline."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import smoke_ai_research as s
b=s.b
ORIGINAL=Path('/tmp/grantscope-smoke-20261107-results')
STATE=Path('/tmp/grantscope-smoke-20261107-state')
DEFAULT_OUTPUT=Path('/tmp/grantscope-citation-continuation-20261107')


def prepare():
    s.configure()
    manifest=s.smoke_manifest()
    packet=b.load_packet(manifest['cases'][0])
    event_bytes=(ORIGINAL/'events.jsonl').read_bytes()
    events=[json.loads(line) for line in event_bytes.decode().splitlines()]
    previous={e['model_key']:e for e in events if e.get('raw_content') and e['stage']==1}
    analyses={key:json.loads(e['raw_content']) for key,e in previous.items()}
    reports={}
    for key,value in analyses.items():
        checks=b.citation_checks(value,packet)
        try:b.validate_analysis(value,packet);valid=True;error=None
        except ValueError as exc:valid=False;error=str(exc)
        reports[key]={'complete_analysis_passes':valid,'error':error,
                      'categories':dict(Counter(c['category'] for c in checks)), 'checks':checks,
                      'original_validation_status':previous[key]['status']}
    artifacts={'events.jsonl':b.digest(event_bytes)}
    for name in ['01-request.json','02-request.json','contract.json']:
        data=(ORIGINAL/name).read_bytes();artifacts[name]=b.digest(data)
        if name.endswith('request.json'):
            original_packet=json.loads(json.loads(data)['messages'][1]['content'])['frozen_packet']
            if original_packet != packet:raise b.PilotAbort('Frozen packet differs from the original experiment')
    contract={'base_contract_sha256':b.contract_hash(manifest),'continuation_driver_sha256':b.digest(Path(__file__).read_bytes()),
              'original_artifact_sha256':artifacts,'scope':'364144-only; Sol existing analysis -> decision; GPT55 at most one new analysis -> decision',
              'maximum_new_calls':4,'scheduled_maximum_new_calls':3,'max_usd':15,
              'cache_aware_reference_ceiling_usd':round(b.reserve_token_cost('gpt61sol',2)+sum(b.reserve_token_cost('gpt55',x) for x in (1,2)),6),
              'human_reference_labels_available':False,'public_reference_rates_accepted_by_user':True}
    contract['contract_sha256']=b.digest(contract)
    return packet,analyses,reports,contract


def run(args):
    packet,analyses,reports,contract=prepare()
    if args.expected_contract != contract['contract_sha256'] or contract['cache_aware_reference_ceiling_usd']>15:
        raise b.PilotAbort('Continuation contract/cost mismatch')
    before=json.loads((STATE/'deployments-post-inference.json').read_text())
    current=s.deployments()
    if current != before:raise b.PilotAbort('Existing deployment configuration changed')
    for cfg in b.MODELS.values():s.verify_created(next(d for d in current if d['name']==cfg['deployment']),cfg)
    out=Path(args.output_dir);out.mkdir(mode=0o700,exist_ok=False)
    if (out.stat().st_mode & 0o777)!=0o700:raise b.PilotAbort('Private output directory required')
    b.private_write(out/'contract.json',json.dumps(contract,indent=2))
    b.private_write(out/'offline-revalidation.json',json.dumps(reports,indent=2,ensure_ascii=False))
    b.private_write(out/'deployments-before.json',json.dumps(current,indent=2))
    attempts=0;reserved=0.;last_start={}
    # The correction is prospective and generic; never include prior mistakes/answers.
    correction='''\nCitation contract: compare NFC Unicode and collapsed whitespace only. Quote the specifically
attributed source, preserving numbers, dates, negation and qualifiers. Do not paraphrase quotations.
Reasoned inferences require cited support; uncited uncertainty must be labeled unresolved_requirement,
not a verified fact. Never assert material eligibility, readiness or activity allowability from silence.'''
    from requests import Session
    with Session() as session:
        for key in ('gpt61sol','gpt55'):
            if key=='gpt61sol':
                if not reports[key]['complete_analysis_passes']:continue
                analysis=analyses[key];stages=(2,)
            else:analysis=None;stages=(1,2)
            for stage in stages:
                # Revalidate original artifacts and current hash before EACH paid call.
                if prepare()[3]['contract_sha256'] != contract['contract_sha256']:
                    raise b.PilotAbort('Evidence/artifact/contract changed')
                if stage==2:b.validate_analysis(analysis,packet)
                payload=b.payload_for(key,packet,stage,analysis)
                if stage==1:payload['messages'][0]['content']+=correction
                if len(json.dumps(payload,ensure_ascii=False).encode())+4096>b.MAX_INPUT_TOKEN_BOUND:
                    raise b.PilotAbort('Input bound exceeded; no truncation')
                cost=b.reserve_token_cost(key,stage)
                if attempts>=4 or reserved+cost>15:raise b.PilotAbort('Incremental call/cost limit reached')
                auth=b.cli_json(s.AZ,['account','get-access-token','--subscription',b.SUBSCRIPTION,'--resource','https://cognitiveservices.azure.com/'])
                wait=max(0,b.PACING_SECONDS-(time.perf_counter()-last_start.get(key,-1e9)))
                if wait:time.sleep(wait)
                attempts+=1;reserved+=cost
                cfg=b.MODELS[key]
                record={'attempt':attempts,'model_key':key,'deployment':cfg['deployment'],'model_version':cfg['version'],
                        'stage':stage,'opportunity_id':'364144','at':datetime.now(timezone.utc).isoformat(),
                        'contract_sha256':contract['contract_sha256'],'payload_sha256':b.digest(payload),
                        'reserved_upper_usd':cost,'pacing_wait_seconds':wait}
                b.event(out/'events.jsonl',{**record,'status':'started'})
                b.private_write(out/f'{attempts:02d}-request.json',json.dumps(payload,indent=2,ensure_ascii=False))
                start=time.perf_counter();last_start[key]=start;fatal=False
                try:
                    response=session.post(b.ENDPOINT+'/openai/v1/chat/completions',headers={'Authorization':'Bearer '+auth['accessToken'],'Content-Type':'application/json'},
                        json=payload,timeout=(10,180),allow_redirects=False)
                    record.update(http_status=response.status_code,request_id=response.headers.get('x-request-id') or response.headers.get('apim-request-id'),raw_response_body=response.text)
                    envelope=response.json()
                    record.update(usage=envelope.get('usage',{}),returned_model=envelope.get('model'))
                    if response.status_code!=200:raise b.PilotAbort('Provider HTTP failure')
                    record['estimated_cost_usd']=b.estimate_token_cost(key,record['usage'])
                    if record['estimated_cost_usd']>cost:raise b.PilotAbort('Unexpected cost exceeds reservation')
                    choice=envelope['choices'][0];record['finish_reason']=choice.get('finish_reason');record['raw_content']=choice['message'].get('content')
                    if choice['message'].get('refusal') or choice.get('finish_reason')!='stop':raise ValueError('Refusal/incomplete output')
                    value=json.loads(record['raw_content'])
                    if stage==1:
                        record['citation_checks']=b.citation_checks(value,packet)
                        b.validate_analysis(value,packet);analysis=value
                    else:
                        b.validate_decision(value,analysis,packet)
                        direct=next(d for d in analysis['dimensions'] if d['dimension']=='D')
                        if value['can_apply']=='direct_route_supported_subject_to_notice' and direct['assessment']!='supported':
                            raise ValueError('Direct eligibility conflicts with unresolved applicant analysis')
                    record.update(status='validated',result=value,human_entailment_review='not_performed')
                except Exception as exc:
                    fatal=isinstance(exc,b.PilotAbort) or record.get('http_status')!=200 or 'raw_content' not in record
                    record.update(status='failed',abort_run=fatal,error_type=type(exc).__name__,
                        failure_category='provider_configuration_transport_or_cost' if fatal else 'model_output_validation',
                        error_reason=str(exc) if isinstance(exc,(ValueError,b.PilotAbort)) else 'transport_or_envelope_failure')
                finally:
                    record.update(end_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=round(time.perf_counter()-start,3))
                    b.event(out/'events.jsonl',record,secret_values=(auth['accessToken'],))
                print(json.dumps({k:record.get(k) for k in ['attempt','model_key','stage','status','elapsed_seconds','estimated_cost_usd','error_reason']}),flush=True)
                if fatal:raise b.PilotAbort('Experiment stopped; no retry')
                if record['status']!='validated':break
    after=s.deployments()
    b.private_write(out/'deployments-after.json',json.dumps(after,indent=2))
    if after!=before:raise b.PilotAbort('Deployment configuration changed during continuation')
    print(json.dumps({'new_calls':attempts,'reserved_upper_usd':reserved,'output_dir':str(out)}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute-authorized-continuation',action='store_true');p.add_argument('--expected-contract');p.add_argument('--output-dir',default=str(DEFAULT_OUTPUT));args=p.parse_args()
    if args.execute_authorized_continuation:run(args)
    else:
        packet,analyses,reports,contract=prepare()
        print(json.dumps({'contract':contract,'revalidation':{k:{f:v for f,v in r.items() if f!='checks'} for k,r in reports.items()}},indent=2))


if __name__=='__main__':main()
