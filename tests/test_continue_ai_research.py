"""Offline continuation order and fail-stop tests; no real Azure calls."""
import argparse
import importlib
import json
from pathlib import Path
from unittest.mock import Mock
import pytest


def setup_case(tmp_path,monkeypatch):
    if not (Path(__file__).resolve().parents[1]/"docs/ai-research-benchmark/pilot/manifest.json").exists():
        pytest.skip("Optional private pilot evidence is not distributed")
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    c=importlib.import_module('continue_ai_research');c.s.configure()
    packet=c.b.load_packet(c.s.smoke_manifest()['cases'][0])
    analysis={'project_activity_understanding':'Synthetic only','dimensions':[
        {'dimension':d,'assessment':'conditional','rationale':'Unresolved synthetic fact','claims':[]} for d in 'ABCDEF'],
        'counterevidence':[],'missing_documents_or_requirements':['Synthetic condition']}
    contract={'contract_sha256':'synthetic-contract','cache_aware_reference_ceiling_usd':2.57}
    monkeypatch.setattr(c,'prepare',lambda:(packet,{'gpt61sol':analysis},{'gpt61sol':{'complete_analysis_passes':True}},contract))
    state=tmp_path/'state';state.mkdir();monkeypatch.setattr(c,'STATE',state)
    deployments=[{'name':v['deployment'],'model':{'name':v['model'],'version':v['version']},
        'sku':{'name':'GlobalStandard','capacity':200},'state':'Succeeded','upgrade':'NoAutoUpgrade',
        'rateLimits':[{'key':'token','count':200000}]} for v in c.b.MODELS.values()]
    (state/'deployments-post-inference.json').write_text(json.dumps(deployments))
    monkeypatch.setattr(c.s,'deployments',lambda:deployments)
    monkeypatch.setattr(c.b,'cli_json',lambda *_:{'accessToken':'SYNTHETIC_NO_LOG'})
    monkeypatch.setattr(c.b,'PACING_SECONDS',0)
    return c,analysis,argparse.Namespace(expected_contract='synthetic-contract',output_dir=str(tmp_path/'out'))


def test_reuse_sol_then_one_fresh_gpt_analysis_and_decision(tmp_path,monkeypatch):
    c,analysis,args=setup_case(tmp_path,monkeypatch);calls=[]
    def post(*a,**kwargs):
        p=kwargs['json'];stage=1 if p['response_format']['json_schema']['schema']==c.b.ANALYSIS_SCHEMA else 2
        calls.append((p['model'],stage))
        result=analysis if stage==1 else {'can_apply':'needs_review','should_apply':'conditional_lead',
            'can_act_in_time':'needs_review','decision_rationale':'Synthetic only','material_conditions':['Unknown'],
            'next_actions':['Verify requirements'],'relevance_confidence':'Low','project_activity_score':50,
            'strategic_score':None,'application_viability':'CONDITIONAL'}
        response=Mock(status_code=200,headers={},text='Synthetic response')
        response.json.return_value={'usage':{'prompt_tokens':10,'completion_tokens':10},
            'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}
        return response
    monkeypatch.setattr('requests.Session.post',post);c.run(args)
    assert calls==[('grantscope-bench-gpt61sol-v1',2),('grantscope-bench-gpt55-v1',1),('grantscope-bench-gpt55-v1',2)]
    assert 'SYNTHETIC_NO_LOG' not in (Path(args.output_dir)/'events.jsonl').read_text()


def test_continuation_transport_failure_stops_all_paths(tmp_path,monkeypatch):
    import requests
    c,_,args=setup_case(tmp_path,monkeypatch);calls=[]
    def fail(*a,**kw):calls.append(1);raise requests.Timeout('SYNTHETIC_NO_LOG')
    monkeypatch.setattr('requests.Session.post',fail)
    with pytest.raises(c.b.PilotAbort):c.run(args)
    assert len(calls)==1
    log=(Path(args.output_dir)/'events.jsonl').read_text()
    assert 'SYNTHETIC_NO_LOG' not in log and json.loads(log.splitlines()[-1])['abort_run']
