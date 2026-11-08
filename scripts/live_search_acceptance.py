#!/usr/bin/env python3
"""Bounded acceptance runner using the generic Search engine, never benchmark execution.
Default discovery/inspection makes only public Grants.gov requests. Explicit --run
is scoped to two discovered IDs, four paid HTTP requests and $5 reference budget.
"""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
import requests
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from services.grants_api import get_grants
from services.search_foundation import discover_project,build_project_review
from services.research_engine import (AzureSolProvider,ResearchBudget,ResearchAbort,run_research,
    request_for_candidate,protocol_hash)
from services.matching import project_relevance
STATE=Path('/tmp/grantscope-final-acceptance-20261107')
AGENCY='Department of Environmental Quality'
PROJECT='The NC Department of Environmental Quality seeks funding to restore rural watershed health through riparian vegetation restoration, nutrient-runoff monitoring and water-quality assessment, working with local governments and landowners. Proposed sites, lead-applicant or partner arrangements, match commitments and application readiness require verification.'
PROFILE={'mission':'North Carolina environmental protection; user-provided context, not verified strategic goals',
         'applicant_identity':AGENCY,'applicant_category':'NC state government agency','geography':('North Carolina rural watersheds',),
         'activities':('Riparian vegetation restoration','Nutrient-runoff monitoring','Water-quality assessment'),
         'constraints':('Match, sites and partner commitments unconfirmed',)}
AZ='/tmp/grantscope-azure-cli/bin/az'
SUB='9ff1fdde-236a-4d20-8d51-3e63ec86ed18'


def write_new(path,value):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(value,stream,indent=2,ensure_ascii=False)


def cli(arguments):
    r=subprocess.run([AZ,*arguments,'--only-show-errors','-o','json'],capture_output=True,text=True,timeout=90)
    if r.returncode:raise ResearchAbort('Azure CLI authentication/metadata access failed; no raw stderr logged')
    return json.loads(r.stdout)


def deployments():
    return cli(['cognitiveservices','account','deployment','list','--subscription',SUB,'-g','rg-primary-unc-sdis-solveathon-team07','-n','grantscope-ai-team07',
        '--query','[].{name:name,model:properties.model,sku:sku,state:properties.provisioningState,upgrade:properties.versionUpgradeOption}'])


def discover():
    STATE.mkdir(mode=0o700,exist_ok=False)
    protected={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'app.py',ROOT/'modules/dashboard.py',ROOT/'.grantscope/ai_recommendations.json']}
    write_new(STATE/'protected-before.json',protected)
    seeds=get_grants('water watershed restoration',100)
    result=discover_project(AGENCY,PROJECT,seeds,get_grants)
    write_new(STATE/'discovery.json',{'agency':AGENCY,'project':PROJECT,'profile':PROFILE,**result})
    unique={str(g['id']):g for g in result['grants'] if g.get('id') is not None}
    ranked=sorted(unique.values(),key=lambda g:-(project_relevance('water watershed restoration riparian',g)[0] or 0))
    print(json.dumps({'unique_discovered':len(unique),'partial_query_errors':result['retrieval_errors'],
        'candidates':[{'id':str(g['id']),'title':g.get('title'),'deadline':g.get('closeDate'),'status':g.get('oppStatus')} for g in ranked[:35]]},indent=2),flush=True)


class GuardedEntraSession:
    """Authentication-only adapter. The generic provider builds/validates all payloads.
    No project API key is read. Authorization exists only in memory.
    """
    def __init__(self):self.session=requests.Session();self.calls=0;self.estimated_usd=0.
    def post(self,url,**kwargs):
        if self.calls>=4:raise ResearchAbort('Acceptance HTTP limit reached')
        if url!='https://grantscope-ai-team07.openai.azure.com/openai/v1/chat/completions':raise ResearchAbort('Unexpected inference endpoint')
        if kwargs['json']['model']!='grantscope-bench-gpt61sol-v1':raise ResearchAbort('Unexpected model deployment')
        token=cli(['account','get-access-token','--subscription',SUB,'--resource','https://cognitiveservices.azure.com/'])['accessToken']
        headers={k:v for k,v in kwargs.get('headers',{}).items() if k.lower()!='api-key'}
        headers['Authorization']='Bearer '+token;kwargs['headers']=headers
        self.calls+=1
        write_new(STATE/f'paid-call-{self.calls}-started.json',{'at':datetime.now(timezone.utc).isoformat(),
            'stage_schema':kwargs['json']['response_format']['json_schema']['name'],'payload_sha256':hashlib.sha256(json.dumps(kwargs['json'],sort_keys=True).encode()).hexdigest()})
        # Do not follow redirects, retry or make a compatibility probe.
        response=self.session.post(url,**kwargs)
        response._content=response.content.replace(token.encode(),b'[REDACTED]')
        return response


def run(ids):
    if len(ids)!=2 or len(set(ids))!=2 or '364144' in ids:raise ResearchAbort('Exactly two distinct non-demo IDs required')
    if (STATE/'execution-started.json').exists():raise ResearchAbort('Acceptance already attempted; do not rerun paid calls')
    d=json.loads((STATE/'discovery.json').read_text());available={str(g['id']) for g in d['grants'] if g.get('id') is not None}
    if not set(ids)<=available:raise ResearchAbort('Selected IDs are not from saved current discovery')
    before=deployments()
    baseline=STATE/'deployments-before.json'
    if baseline.exists():
        if json.loads(baseline.read_text())!=before:raise ResearchAbort('Baseline deployment metadata changed')
    else:write_new(baseline,before)
    sol=next(x for x in before if x['name']=='grantscope-bench-gpt61sol-v1')
    if sol['model']['name']!='gpt-6.1-sol' or sol['model']['version']!='2026-09-29' or sol['sku']['name']!='GlobalStandard' or sol['sku']['capacity']!=200 or sol['state']!='Succeeded' or sol['upgrade']!='NoAutoUpgrade':
        raise ResearchAbort('Deployment configuration mismatch')
    review=build_project_review(d['grants'],d['agency'],d['project'],budget=2,selected_ids=ids,agency_profile=d['profile'])
    if {r['identity'][1] for r in review['queue']['selected']}!=set(ids):raise ResearchAbort('Queue selection mismatch')
    write_new(STATE/'execution-started.json',{'protocol_hash':protocol_hash(),'selected_ids':ids,'max_opportunities':2,'max_calls':4,
        'max_usd':5,'reference_maximum_usd':2.41,'authentication':'Existing Azure CLI Entra session; no API keys read'})
    session=GuardedEntraSession()
    provider=AzureSolProvider({'AZURE_OPENAI_ENDPOINT':'https://grantscope-ai-team07.openai.azure.com','AZURE_OPENAI_API_KEY':'UNUSED_ENTRA_AUTH_PLACEHOLDER'},session=session)
    factory=lambda grant:request_for_candidate(d['agency'],d['project'],grant,profile=d['profile'])
    snapshots=0
    def persist(records):
        nonlocal snapshots;snapshots+=1
        write_new(STATE/f'records-{snapshots:03d}.json',records)
        for oid in ids:
            r=records.get(oid,{})
            print(json.dumps({'id':oid,'state':r.get('state'),'inflight_stage':r.get('inflight_stage'),
                'calls':len(r.get('calls',[])),'reason':r.get('reason')},ensure_ascii=False),flush=True)
    result=run_research(review,factory,provider,budget=ResearchBudget(2,4,5),on_update=persist)
    write_new(STATE/'result.json',result)
    after=deployments();write_new(STATE/'deployments-after.json',after)
    if after!=before:raise ResearchAbort('Deployment metadata changed')
    protected=json.loads((STATE/'protected-before.json').read_text())
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h for p,h in protected.items()):raise ResearchAbort('Protected files/cache changed')
    print(json.dumps({'paid_http_calls':session.calls,'states':{oid:result['records'][oid]['state'] for oid in ids},
        'aborted':result['aborted'],'artifact_directory':str(STATE)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--discover',action='store_true');parser.add_argument('--run',nargs=2,metavar='OPPORTUNITY_ID');args=parser.parse_args()
    if args.discover:discover()
    elif args.run:run(args.run)
    else:parser.print_help()
