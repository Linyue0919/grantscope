"""Search adapter for retained candidate pools, conservative gates and queue planning.

No Azure calls and no persistent recommendation-cache writes. This does not infer
reviewed hard restrictions from model scores or legacy eligibility labels.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from research_foundation.citations import citation_checks
from research_foundation.hard_gates import REQUIRED_GATES, Finding, State, evaluate_gates
from research_foundation.research_queue import QueueConfig, build_queue, identity
from services.discovery import diversified_retrieval_queries, merge_cached_opportunities
from services.verified_goals import VERIFIED_GOALS
from services.matching import project_relevance
from services.research_engine import request_for_candidate
from research_foundation.contract import (Agency,Opportunity,ResearchInput,SharedResult,
    CONTRACT_VERSION,deep_research_packet,validate_shared_result)

CASE_ROOT = Path(__file__).resolve().parents[1]/'data/researched_cases'


def discover_project(agency, project, seeds, fetch_grants):
    """Retain seeds on partial retrieval failures; bounded diversified retrieval."""
    pool=list(seeds);errors=[]
    for query in diversified_retrieval_queries(VERIFIED_GOALS.get(agency, {}), project):
        try:pool.extend(fetch_grants(query, rows=25))
        except Exception:
            errors.append(f'One diversified query failed: {query}')
    return {'grants':pool,'retrieval_errors':errors,'raw_retrieved':len(pool)}


def candidate_decision(findings=(), sources=(), phase='preliminary'):
    result=evaluate_gates(findings,sources,phase)
    state={State.PASS:'ACTIONABLE' if result.actionable else 'CONDITIONAL',
           State.CONDITIONAL:'CONDITIONAL',State.CONFIRMED_EXCLUSION:'CONFIRMED_EXCLUSION',
           State.INSUFFICIENT_EVIDENCE:'INSUFFICIENT_EVIDENCE'}[result.state]
    return {'state':state,'gate_result':result}


def build_project_review(grants, agency, project, cached_records=(), budget=10, selected_ids=(),
                         verified_gate_inputs=None,agency_profile=None,mode="project_first"):
    """One identity per opportunity, all raw variants retained by the queue.

    Only explicit reviewed inputs can confirm a hard exclusion. Legacy model
    judgments remain prioritization/review signals, never gate attestations.
    """
    verified_gate_inputs=verified_gate_inputs or {}
    cached={str(r['opportunity_id']):r for r in cached_records}
    merged=list(grants)+merge_cached_opportunities([],cached_records)
    candidates=[];decisions={}
    for grant in merged:
        grant=deepcopy(grant)
        value=grant.get('id') if grant.get('id') is not None else grant.get('opportunity_id')
        if value is None or not str(value).strip():
            original=deepcopy(grant)
            grant['id']='unresolved-'+hashlib.sha256(json.dumps(original,sort_keys=True,default=str).encode()).hexdigest()[:20]
            grant['source']='unresolved.grants.gov';grant['original_record']=original
            grant['identity_warning']='Official opportunity ID unavailable; retained for audit, not deep research'
        if grant.get('id') is None:grant['id']=str(value)
        oid=str(grant['id'])
        prior=cached.get(oid,{});semantic=prior.get('semantic') or {}
        score=semantic.get('project_relevance_score') if mode=='project_first' and semantic.get('status') in {'Evaluated','Prioritized'} else None
        if isinstance(score,bool) or not isinstance(score,(int,float)) or not 0<=score<=100:score=None
        inputs=verified_gate_inputs.get(oid,{})
        findings=list(inputs.get('findings',()))
        if not findings:
            # Legacy exclusion is a review signal until source/route attestations
            # satisfy the hard-gate contract; do not fabricate a reviewer.
            findings=[Finding(g,State.INSUFFICIENT_EVIDENCE,
                       'Official requirement and project conditions have not been independently verified') for g in REQUIRED_GATES]
        decision=candidate_decision(findings,inputs.get('sources',()),inputs.get('phase','preliminary'))
        original=request_for_candidate(agency,project,grant,profile=agency_profile,mode=mode)
        if inputs.get('sources'):
            original=__import__('dataclasses').replace(original,sources=tuple(inputs['sources']))
        packet=deep_research_packet(original)
        shared=SharedResult(CONTRACT_VERSION,oid,packet['request_fingerprint'],'preliminary',
            {'full_notice_verified':False,'amendments_verified':False},
            {'project':{'status':'cached_priority_only' if score is not None else 'unavailable','score':score},
             'strategic':{'status':'unavailable','score':None}},decision['gate_result'],(),(),decision['gate_result'].unresolved,
            'needs_review','reject' if decision['state']=='CONFIRMED_EXCLUSION' else
            'insufficient_evidence' if decision['state']=='INSUFFICIENT_EVIDENCE' else 'conditional_lead',
            'needs_review',('Verify the current official notice and unresolved application conditions',),
            {'status':'Preliminary only; no new AI evaluation'})
        validate_shared_result(shared)
        decision['shared_result']=shared
        decision['original_input_packet']=packet
        decisions[identity(grant)]=decision
        ranking_text=project if mode=='project_first' else ' '.join(g.text for g in (agency_profile or {}).get('verified_goals',()))
        lexical_score,matched_terms=project_relevance(ranking_text,grant,prior.get('official_details'))
        candidates.append({**deepcopy(grant),'opportunity_id':oid,
             'priority_score':score if score is not None else lexical_score,
             'cached_ai_score':score,'priority_origin':'Cached GPT-4o' if score is not None else 'Keyword aid (not AI)',
             'keyword_terms':matched_terms,
             'agency':grant.get('agencyName') or grant.get('agencyCode') or 'Unknown federal agency',
             'program_type':grant.get('category') or 'Unknown program type',
             'gate_state':decision['state'],'uncertain':decision['state']!='ACTIONABLE',
             'user_selected':oid in selected_ids})
    queue=build_queue(candidates,QueueConfig(budget=budget,user=budget,uncertainty=budget,
        diversity=budget,recall_audit=budget,priority=budget))
    for row in queue['pool']:
        row['decision']=decisions[row['identity']]
        prior=cached.get(row['identity'][1],{})
        row['official_screen_note']=prior.get('eligibility_reason')
        row['official_details']=deepcopy(prior.get('official_details') or {})
    return {'agency':agency,'project':project,'queue':queue,'candidate_count':len(queue['pool']),
            'scope':mode+'; queue selection is planning, not completed deep research'}


def load_demo_case():
    manifest=json.loads((CASE_ROOT/'manifest.json').read_text())['364144']
    raw=(CASE_ROOT/manifest['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=manifest['sha256']:raise ValueError('Precomputed case integrity check failed')
    case=json.loads(raw)
    checks=citation_checks(case['analysis'],case['packet'])
    if not all(c['passed'] for c in checks):raise ValueError('Precomputed case citation validation failed')
    if (case['decision']['application_viability']!='CONDITIONAL'
            or case['decision']['project_activity_score']!=45 or case['decision']['strategic_score']!=75):
        raise ValueError('Precomputed case differs from the validated pilot result')
    return case
