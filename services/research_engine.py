"""Generic, UI-neutral per-opportunity research orchestration.

No fixture IDs, historical conclusions, deployments writes or implicit paid calls.
The caller explicitly supplies a provider only on an authorized research action.
"""
from dataclasses import asdict,dataclass,replace
from datetime import datetime,timezone
from enum import Enum
from zoneinfo import ZoneInfo
import hashlib,json,time
from pathlib import Path
import os
import requests
from research_foundation import protocol as p
from research_foundation.citations import citation_checks
from research_foundation.contract import ResearchInput,Opportunity,Source,SharedResult,CONTRACT_VERSION,deep_research_packet,validate_shared_result
from research_foundation.hard_gates import REQUIRED_GATES,Finding,State,evaluate_gates
from services.official_evidence import OfficialEvidenceClient


INPUT_TOKEN_BOUND=175000  # Leaves room for 25k output within the existing 200k-TPM request budget.


class ResearchState(str,Enum):
    DISCOVERED='DISCOVERED'
    PRELIMINARY_SCREENED='PRELIMINARY_SCREENED'
    QUEUED_FOR_RESEARCH='QUEUED_FOR_RESEARCH'
    RESEARCHED_AND_VALIDATED='RESEARCHED_AND_VALIDATED'
    RESEARCH_FAILED='RESEARCH_FAILED'
    NOT_YET_RESEARCHED='NOT_YET_RESEARCHED'


class ResearchAbort(RuntimeError):pass


def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def context_key(request):
    data=asdict(request);data.pop('opportunity');data.pop('missing_documents')
    return fingerprint(data)


@dataclass
class ResearchBudget:
    max_opportunities:int=3
    max_calls:int=6
    max_usd:float=5.
    used_calls:int=0
    reserved_usd:float=0.

    def reserve(self,stage):
        # Sol short-context reference rates with all input at the cache-write rate.
        amount=(INPUT_TOKEN_BOUND*2.5+(25000 if stage==1 else 8000)*10)/1e6
        if self.used_calls>=self.max_calls or self.reserved_usd+amount>self.max_usd:
            return False
        self.used_calls+=1;self.reserved_usd+=amount;return True

    def __post_init__(self):
        if (isinstance(self.max_opportunities,bool) or not isinstance(self.max_opportunities,int) or not 0<=self.max_opportunities<=100
                or not isinstance(self.max_calls,int) or isinstance(self.max_calls,bool) or not 0<=self.max_calls<=200
                or not isinstance(self.max_usd,(int,float)) or not 0<=self.max_usd<=100):
            raise ValueError('Invalid bounded research budget')


def initial_records(review):
    selected={r['identity'] for r in review['queue']['selected']}
    result={}
    for row in review['queue']['pool']:
        oid=row['identity'][1]
        history=[ResearchState.DISCOVERED.value,ResearchState.PRELIMINARY_SCREENED.value]
        state=ResearchState.QUEUED_FOR_RESEARCH if row['identity'] in selected else ResearchState.NOT_YET_RESEARCHED
        result[oid]={'opportunity_id':oid,'state':state.value,'history':history+[state.value],
                     'selection_reason':row['selection_reason'],'candidate':row['records'][0],
                     'preliminary_viability':row['decision']['state'],'research_depth':'preliminary'}
    return result


def make_packet(request,evidence):
    if request.opportunity.opportunity_id!=evidence['opportunity_id']:raise ValueError('Opportunity/evidence identity mismatch')
    sources=list(request.sources)
    sources.extend(Source(s['source_id'],s['url'],s['text'],s['version'],s['retrieved_at'],True) for s in evidence['sources'])
    original=replace(request,sources=tuple(sources),missing_documents=tuple(evidence['coverage']['gaps']))
    original_packet=deep_research_packet(original)
    docs=[{'source_id':s.source_id,'url':s.url,'text':s.text,'version':s.version,'retrieved_at':s.retrieved_at} for s in sources]
    if request.project_description:
        docs.append({'source_id':'user-project-context','url':None,'text':request.project_description,
                     'kind':'user_context','version':context_key(request),'retrieved_at':request.as_of})
    # Do not duplicate source text, or ever copy prioritizer/model fields.
    original_packet['sources']=[{'source_id':s.source_id,'text_sha256':hashlib.sha256(s.text.encode()).hexdigest()} for s in sources]
    return {'original_request':original_packet,'documents':docs,'opportunity_source_ids':[s['source_id'] for s in evidence['sources']],'evidence_coverage':evidence['coverage'],
            'strategic_goal_status':'source_checked' if request.verified_goals else 'unavailable'}


def final_result(request,evidence,analysis,decision,reviewed_gate_inputs=None):
    supplied=reviewed_gate_inputs or {};findings=list(supplied.get('findings',()))
    supplied_names={f.gate for f in findings};by={d['dimension']:d for d in analysis['dimensions']}
    mapping={'applicant':'D','funding_purpose':'C','geography_land':'C','match':'E','sponsorship':'D','timing':'E'}
    for gate in REQUIRED_GATES:
        if gate in supplied_names:continue
        if gate=='official_documents':reason='Notice text read; amendment/policy completeness still requires verification'
        else:reason=by[mapping[gate]]['rationale']
        # A model cannot attest its own eligibility or turn thematic inference into a hard exclusion.
        findings.append(Finding(gate,State.CONDITIONAL,reason,unresolved=(reason,)))
    gates=evaluate_gates(findings,supplied.get('sources',()),'final')
    viability=('CONFIRMED_EXCLUSION' if gates.state==State.CONFIRMED_EXCLUSION else
               'ACTIONABLE' if gates.actionable else 'CONDITIONAL' if evidence['coverage']['primary_notice_ingested'] else 'INSUFFICIENT_EVIDENCE')
    if viability=='ACTIONABLE' and decision['application_viability']!='ACTIONABLE':viability='CONDITIONAL'
    if viability!='CONFIRMED_EXCLUSION' and decision['application_viability']=='INSUFFICIENT_EVIDENCE':viability='INSUFFICIENT_EVIDENCE'
    should=('reject' if viability=='CONFIRMED_EXCLUSION' or decision['should_apply']=='reject' else 'pursue' if viability=='ACTIONABLE' else
            'insufficient_evidence' if decision['should_apply']=='insufficient_evidence' else 'conditional_lead')
    shared=SharedResult(CONTRACT_VERSION,request.opportunity.opportunity_id,fingerprint(make_packet(request,evidence)),'deep',
        evidence['coverage'],{'project':{'score':decision['project_activity_score'] if request.mode=='project_first' else None,'status':'model_assessment' if request.mode=='project_first' else 'not_applicable'},
            'strategic':{'score':decision['strategic_score'],'status':'model_assessment' if request.verified_goals else 'unavailable'}},
        gates,tuple(decision['decision_claims']),tuple(analysis['counterevidence']),
        tuple(dict.fromkeys(analysis['missing_documents_or_requirements']+evidence['coverage']['gaps']+list(gates.unresolved))),
        'direct_route_excluded' if any(r['gate']=='applicant' and r['state']=='CONFIRMED_EXCLUSION' for r in gates.gates) else
        'direct_route_supported_subject_to_notice' if gates.actionable else 'needs_review',
        should,decision['can_act_in_time'],tuple(decision['next_actions']),
        {'provider':'experimental deep research','human_entailment':'not independently adjudicated'})
    validate_shared_result(shared)
    return {'classification':viability,'shared_result':asdict(shared),'analysis':analysis,'decision':decision,
            'model_viability':decision['application_viability'],'final_gate_policy':'Model claims do not constitute official eligibility attestation'}


def run_research(review,request_factory,provider,*,budget=None,evidence_client=None,previous=None,reviewed_gates=None,on_update=None,retry_failed=False):
    """Works for Search and Dashboard. Provider is explicit, injected and never implicit.

    Retain every candidate. One analysis + one decision per selected candidate;
    no retry in a run. Failed prior paths retry only on a new explicit action.
    """
    budget=budget or ResearchBudget();client=evidence_client or OfficialEvidenceClient()
    records=initial_records(review);previous=previous or {};attempted_opportunities=0;aborted=None;new_provider_attempts=0;new_http_requests=0
    selected_ids={r['identity'][1] for r in review['queue']['selected']}
    def persist():
        if on_update:on_update(records)
    for oid,old in previous.items():
        if oid in records and oid not in selected_ids and old.get('state')==ResearchState.RESEARCHED_AND_VALIDATED.value:
            # Request/agency/project and protocol isolation checked below before reuse.
            req=request_factory(records[oid]['candidate'])
            if old.get('context_key')==context_key(req) and old.get('protocol_hash')==protocol_hash():
                records[oid]={**old,'cache_reused':True,'freshness':'Previously researched; refresh evidence before acting'}
    for row in review['queue']['selected']:
        oid=row['identity'][1];record=records[oid];request=request_factory(row['records'][0])
        scope=context_key(request)
        verified=(reviewed_gates or {}).get(oid)
        preliminary=evaluate_gates(verified.get('findings',()),verified.get('sources',()),'preliminary') if verified else row['decision']['gate_result']
        if preliminary.state==State.CONFIRMED_EXCLUSION:
            record.update(state=ResearchState.PRELIMINARY_SCREENED.value,classification='CONFIRMED_EXCLUSION',
                preliminary_gates=asdict(preliminary),reason='Confirmed source-supported exclusion; no model call made',context_key=scope,protocol_hash=protocol_hash())
            record['history'].append(record['state']);persist();continue
        prior=previous.get(oid,{})
        if prior.get('inflight_stage') and not retry_failed:
            records[oid]={**prior,'state':ResearchState.RESEARCH_FAILED.value,
                'reason':'Previous request completion is ambiguous; verify before an explicit paid retry'}
            aborted=records[oid]['reason'];persist();break
        if (not retry_failed and prior.get('state')==ResearchState.RESEARCH_FAILED.value
                and prior.get('context_key')==scope and prior.get('protocol_hash')==protocol_hash()):
            records[oid]={**prior,'retry_requires_explicit_action':True};continue
        if attempted_opportunities>=budget.max_opportunities:
            if (prior.get('state')==ResearchState.RESEARCHED_AND_VALIDATED.value and prior.get('context_key')==scope
                    and prior.get('protocol_hash')==protocol_hash()):
                records[oid]={**prior,'cache_reused':True,'freshness':'Previously researched; not refreshed in this action'};continue
            record.update(state=ResearchState.NOT_YET_RESEARCHED.value,reason='Research budget exhausted; candidate retained')
            record['history'].append(record['state']);continue
        record.update(context_key=scope,protocol_hash=protocol_hash(),calls=[])
        try:
            evidence=client.fetch(oid);record['evidence']=evidence
            # Only a trusted, source-backed document gate may attest completeness; never a model.
            if evidence['coverage']['primary_notice_ingested'] and verified and any(g['gate']=='official_documents' and g['state']=='PASS' for g in preliminary.gates) and verified.get('coverage'):
                evidence['coverage']={**evidence['coverage'],**{k:v for k,v in verified['coverage'].items() if k in {'gaps','amendments_verified'}}}
                record['evidence']=evidence
            if not evidence['coverage']['primary_notice_ingested']:
                attempted_opportunities+=1
                record.update(state=ResearchState.RESEARCH_FAILED.value,reason='Full official notice unavailable; no model call made')
                record['history'].append(record['state']);continue
            evidence_key=fingerprint({'sources':[(s['source_id'],s.get('url'),s.get('raw_sha256'),hashlib.sha256(s['text'].encode()).hexdigest()) for s in evidence['sources']],
                'coverage':evidence['coverage'],'status':evidence.get('status')})
            input_key=fingerprint({'context':scope,'opportunity':asdict(request.opportunity),'evidence':evidence_key,'protocol':protocol_hash()})
            record['input_key']=input_key
            if oid in previous and previous[oid].get('input_key')==input_key and previous[oid].get('state')==ResearchState.RESEARCHED_AND_VALIDATED.value:
                records[oid]={**previous[oid],'cache_reused':True};continue
            attempted_opportunities+=1
            reused_analysis=prior.get('analysis') if prior.get('input_key')==input_key else None
            if not reused_analysis and not budget.reserve(1):
                record.update(state=ResearchState.NOT_YET_RESEARCHED.value,reason='Model call/cost budget exhausted; evidence retained')
                record['history'].append(record['state']);continue
            packet=make_packet(request,evidence)
            record['source_documents']=packet['documents']
            def call(stage,analysis=None):
                nonlocal new_provider_attempts,new_http_requests
                record['inflight_stage']=stage
                record['calls'].append({'stage':stage,'status':'started','request_sent':False,
                                        'started_at':datetime.now(timezone.utc).isoformat()})
                persist()  # A crash cannot silently turn an ambiguous paid request into a safe retry.
                new_provider_attempts+=1
                try:envelope=provider.complete(packet,stage,analysis)
                except Exception:raise ResearchAbort('Provider runtime/transport error; request completion ambiguous') from None
                new_http_requests+=int(bool(envelope.get('request_sent')))
                record['calls'][-1].update({k:v for k,v in envelope.items() if k!='value'})
                record['calls'][-1]['status']='failed' if envelope.get('error') else 'completed'
                record.pop('inflight_stage',None)
                if envelope.get('fatal'):raise ResearchAbort(envelope.get('error','Provider error'))
                if envelope.get('error'):raise ValueError(envelope['error'])
                value=envelope['value']
                cited_value=value if stage==1 else {'dimensions':[{'claims':value.get('decision_claims',[])}],'counterevidence':[]}
                try:
                    record['calls'][-1]['citation_checks']=citation_checks(cited_value,packet)
                    checks=p.validate_analysis(value,packet) if stage==1 else p.validate_decision(value,analysis,packet)
                except (ValueError,KeyError,TypeError) as exc:
                    record['calls'][-1]['validation_error']=str(exc)
                    raise
                record['calls'][-1]['citation_checks']=checks
                return value
            if reused_analysis:
                p.validate_analysis(reused_analysis,packet);analysis=reused_analysis;record['analysis_reused']=True
            else:analysis=call(1)
            record['analysis']=analysis
            persist()
            if not budget.reserve(2):
                record.update(state=ResearchState.NOT_YET_RESEARCHED.value,reason='Analysis completed; decision budget exhausted; no full recommendation')
                record['history'].append(record['state']);continue
            decision=call(2,analysis)
            record.update(final_result(request,evidence,analysis,decision,(reviewed_gates or {}).get(oid)))
            record.update(state=ResearchState.RESEARCHED_AND_VALIDATED.value,research_depth='deep; citation/consistency validated, human review pending',researched_at=datetime.now(timezone.utc).isoformat())
        except ResearchAbort as exc:
            record.update(state=ResearchState.RESEARCH_FAILED.value,reason=str(exc));aborted=str(exc)
        except Exception as exc:
            record.update(state=ResearchState.RESEARCH_FAILED.value,reason='Evidence or validation failed: '+(str(exc) if isinstance(exc,ValueError) else type(exc).__name__))
        record['history'].append(record['state'])
        persist()
        if aborted:break
    persist()
    return {'records':records,'budget':asdict(budget),'aborted':aborted,
            'milestones':{'discovered':len(records),'preliminary_screened':sum(ResearchState.PRELIMINARY_SCREENED.value in r['history'] for r in records.values()),
                          'new_provider_attempts':new_provider_attempts,'new_http_requests':new_http_requests},
            'summary':{s.value:sum(r['state']==s.value for r in records.values()) for s in ResearchState}}


def protocol_hash():
    root=Path(__file__).resolve().parents[1]
    return fingerprint({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),
        root/'research_foundation/protocol.py',root/'research_foundation/citations.py',
        root/'research_foundation/contract.py',root/'research_foundation/hard_gates.py',root/'services/official_evidence.py']})


class AzureSolProvider:
    """Explicit provider. Instantiation makes no request; only complete() can bill."""
    def __init__(self,config,session=None):
        self.endpoint=str(config.get('AZURE_OPENAI_ENDPOINT','')).rstrip('/')
        from urllib.parse import urlparse
        parsed=urlparse(self.endpoint)
        if parsed.scheme!='https' or not (parsed.hostname or '').endswith('.openai.azure.com') or parsed.path:
            raise ValueError('Invalid Azure resource endpoint')
        self.key=str(config.get('AZURE_OPENAI_API_KEY',''))
        if not self.key:raise ValueError('Azure credential unavailable')
        self.session=session or requests.Session();self.last_start=0

    def complete(self,packet,stage,analysis=None):
        payload={'model':'grantscope-bench-gpt61sol-v1','messages':[{'role':'system','content':p.ANALYSIS_INSTRUCTION if stage==1 else p.DECISION_INSTRUCTION},
            {'role':'user','content':json.dumps({'original_evidence_packet':packet,**({'own_validated_analysis':analysis} if stage==2 else {})},ensure_ascii=False)}],
            'reasoning_effort':'medium','max_completion_tokens':25000 if stage==1 else 8000,
            'response_format':{'type':'json_schema','json_schema':{'name':'grant_analysis' if stage==1 else 'grant_decision','strict':True,
                'schema':p.ANALYSIS_SCHEMA if stage==1 else p.DECISION_SCHEMA}}}
        if len(json.dumps(payload,ensure_ascii=False).encode())+4096>INPUT_TOKEN_BOUND:
            return {'error':'Input exceeds conservative budget; evidence not truncated','fatal':False}
        wait=max(0,61-(time.perf_counter()-self.last_start))
        if wait:time.sleep(wait)
        start=time.perf_counter();self.last_start=start
        result={'request_sent':False,'stage':stage,'deployment':payload['model'],'started_at':datetime.now(timezone.utc).isoformat(),'pacing_seconds':wait}
        try:
            result['request_sent']=True
            r=self.session.post(self.endpoint+'/openai/v1/chat/completions',json=payload,
                headers={'api-key':self.key,'Content-Type':'application/json'},timeout=(10,180),allow_redirects=False)
            result.update(http_status=r.status_code,raw_response=r.text.replace(self.key,'[REDACTED]'))
            envelope=r.json();result['usage']=envelope.get('usage',{})
            if r.status_code!=200:raise ResearchAbort('Azure HTTP '+str(r.status_code))
            if envelope.get('model')!='gpt-6.1-sol-2026-09-29':raise ResearchAbort('Unexpected model version')
            usage=result['usage'];total=usage['prompt_tokens'];out=usage['completion_tokens'];detail=usage.get('prompt_tokens_details') or {}
            reads=detail.get('cached_tokens',0);writes=detail.get('cache_write_tokens',0)
            if any(not isinstance(v,int) or v<0 for v in [total,out,reads,writes]) or reads+writes>total:raise ResearchAbort('Ambiguous billing telemetry')
            cost=((total-reads-writes)*2+reads*.1+writes*2.5+out*10)/1e6;result['estimated_cost_usd']=cost
            if cost>(INPUT_TOKEN_BOUND*2.5+(25000 if stage==1 else 8000)*10)/1e6:raise ResearchAbort('Cost exceeded reservation')
            choice=envelope['choices'][0];result['finish_reason']=choice.get('finish_reason')
            if choice.get('finish_reason')!='stop' or choice['message'].get('refusal'):raise ValueError('Incomplete or refused output')
            result['value']=json.loads(choice['message']['content'])
        except Exception as exc:
            fatal=isinstance(exc,ResearchAbort) or result.get('http_status')!=200 or 'finish_reason' not in result
            result.update(error=str(exc).replace(self.key,'[REDACTED]') if isinstance(exc,(ResearchAbort,ValueError)) else 'Transport or envelope failure',fatal=fatal)
        result.update(ended_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=round(time.perf_counter()-start,3))
        return result


class ResearchStore:
    """Separate versioned research cache; never edits legacy recommendation caches."""
    def __init__(self,root='.grantscope/research_v1'):self.root=Path(root)
    def load(self,scope):
        if len(scope)!=64 or any(c not in '0123456789abcdef' for c in scope):raise ValueError('Invalid research scope')
        path=self.root/(scope+'.json')
        if not path.exists():return {}
        return json.loads(path.read_text())
    def save(self,scope,records):
        if len(scope)!=64 or any(c not in '0123456789abcdef' for c in scope):raise ValueError('Invalid research scope')
        existing=self.load(scope)
        merged=dict(existing)
        for oid,record in records.items():
            old=existing.get(oid)
            updated=dict(record)
            if old and (old.get('input_key'),old.get('protocol_hash'))!=(record.get('input_key'),record.get('protocol_hash')):
                snapshot={k:v for k,v in old.items() if k!='prior_versions'}
                updated['prior_versions']=list(old.get('prior_versions',[]))+[snapshot]
            elif old and old.get('prior_versions'):
                updated['prior_versions']=old['prior_versions']
            merged[oid]=updated
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.root.is_symlink() or (self.root.stat().st_mode & 0o777)!=0o700:raise ValueError('Research cache directory must be private')
        fd=os.open(self.root/(scope+'.tmp'),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:
            json.dump(merged,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
        os.replace(self.root/(scope+'.tmp'),self.root/(scope+'.json'))


def request_for_candidate(agency,project,candidate,*,mode='project_first',profile=None):
    """Common original-context factory for Search and agency-first Dashboard."""
    from research_foundation.contract import Agency
    profile=profile or {}
    agency_record=agency if type(agency) is Agency else Agency('nc-'+fingerprint(str(agency))[:16],str(agency),
        'North Carolina',str(profile.get('mission') or 'Agency strategy not verified'))
    return ResearchInput(mode,agency_record,tuple(profile.get('verified_goals',())),
        project if mode=='project_first' else None,tuple(profile.get('activities',())) if mode=='project_first' else (),
        str(profile.get('applicant_identity') or agency_record.name),str(profile.get('applicant_category') or 'Unverified'),
        tuple(profile.get('geography',())),tuple(profile.get('constraints',())),
        Opportunity(str(int(str(candidate.get('opportunity_id') or candidate.get('id')))) if str(candidate.get('opportunity_id') or candidate.get('id')).isdecimal() else str(candidate.get('opportunity_id') or candidate.get('id')),str(candidate.get('title') or 'Untitled'),
            str(candidate.get('agencyName') or candidate.get('agencyCode') or 'Unknown'),str(candidate.get('category') or 'Unknown')),
        tuple(profile.get('goal_sources',())),('Official evidence intake pending',),datetime.now(ZoneInfo('America/New_York')).date().isoformat())
