#!/usr/bin/env python3
"""Explicit bounded live acceptance of the real one-click Streamlit workflow.
No automatic retries. Stores raw responses privately outside the repository.
"""
import os,sys,json,hashlib
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from streamlit.testing.v1 import AppTest
from services.research_engine import configured_provider,ResearchAbort,ResearchStore
from services.grant_store import LocalGrantStore
from scripts.live_search_acceptance import deployments,write_new

OUT=Path('/tmp/grantscope-recovery-acceptance-20261107')
SCENARIOS=[('Department of Environmental Quality','Restore North Carolina rural watershed health through riparian vegetation restoration, nutrient-runoff monitoring and water-quality assessment with local governments and landowners. Lead applicant arrangements, sites and match commitments are not yet verified.'),
           ('Wildlife Resources Commission','Restore coastal North Carolina fish and wildlife habitat through wetland and riparian restoration and fish passage improvements following pollution-related natural resource damage. Coordinate with local governments and federal restoration trustees. Specific restoration plans, sites, applicant route and readiness need verification.')]


def main():
    OUT.mkdir(mode=0o700,exist_ok=True)
    protected={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['app.py','modules/dashboard.py','.grantscope/ai_recommendations.json']}
    before=deployments()
    if not (OUT/'deployments-before.json').exists():write_new(OUT/'deployments-before.json',before)
    assert json.loads((OUT/'deployments-before.json').read_text())==before
    if not (OUT/'protected.json').exists():write_new(OUT/'protected.json',protected)
    assert json.loads((OUT/'protected.json').read_text())==protected
    os.environ['GRANTSCOPE_AZURE_CLI']='/tmp/grantscope-azure-cli/bin/az'
    real=configured_provider({})
    class Guard:
        def __init__(self):
            markers=list(OUT.glob('call-*-started.json'));responses=list(OUT.glob('call-*-response.json'))
            if len(markers)!=len(responses):raise ResearchAbort('Ambiguous previous request; stop')
            old=[json.loads(p.read_text()) for p in responses]
            self.calls=len(markers);self.reserved=max([json.loads(p.read_text())['reserved'] for p in markers] or [0])
            self.actual=sum(r.get('estimated_cost_usd',0) for r in old);self.aborted=any(r.get('fatal') for r in old)
        def complete(self,packet,stage,analysis=None):
            amount=(175000*2.5+(25000 if stage==1 else 8000)*10)/1e6
            if self.aborted or self.calls>=8 or self.reserved+amount>5:raise ResearchAbort('Acceptance global cap or stop condition')
            self.calls+=1;self.reserved+=amount
            write_new(OUT/f'call-{self.calls}-started.json',{'stage':stage,'id':packet['original_request']['opportunity']['opportunity_id'],'reserved':self.reserved})
            result=real.complete(packet,stage,analysis)
            write_new(OUT/f'call-{self.calls}-response.json',result)
            self.actual+=result.get('estimated_cost_usd',0)
            if result.get('fatal') or self.actual>5:self.aborted=True
            print(json.dumps({'call':self.calls,'stage':stage,'id':packet['original_request']['opportunity']['opportunity_id'],
                'http':result.get('http_status'),'seconds':result.get('elapsed_seconds'),'estimated_usd':result.get('estimated_cost_usd'),'error':result.get('error')}),flush=True)
            return result
    guard=Guard();store=LocalGrantStore(OUT/'saved.json');cache=ResearchStore(OUT/'cache')
    results=[]
    for index,(agency,project) in enumerate(SCENARIOS,1):
        if guard.aborted:break
        with patch('modules.search_workflow.configured_provider',return_value=guard),patch('modules.search_workflow.ResearchStore',return_value=cache),patch('modules.search_workflow.LocalGrantStore',return_value=store):
            at=AppTest.from_string('from modules.search import show_search\nshow_search()').run()
            at.selectbox(key='search_agency').select(agency).run()
            at.text_area(key='search_project').input(project)
            at.button(key='search_submit').click().run(timeout=1800)
            if at.exception:raise RuntimeError('Streamlit exception; inspect private artifacts')
            state={k:v for k,v in at.session_state.filtered_state.items() if k.startswith('workflow_') and isinstance(v,dict)}
            if len(state)!=1:raise RuntimeError('Missing unique workflow state')
            key,snapshot=next(iter(state.items()))
            write_new(OUT/f'scenario-{index}-completed.json',{'agency':agency,'project':project,'scope':key,
                'state':{k:v for k,v in snapshot.items() if k in {'grants','records','errors','run'}}})
            calls=guard.calls
            save=next((b for b in at.button if b.key and b.key.startswith('workflow_save_')),None)
            if save:at.button(key=save.key).click().run()
            at.run()
            if guard.calls!=calls:raise RuntimeError('Rerun repeated a paid call')
            records=snapshot['records'];selected=[r['identity'][1] for r in snapshot['review']['queue']['selected']]
            result={'agency':agency,'discovered':len(records),'selected':selected,'calls_so_far':calls,
                'states':{oid:{'state':records[oid]['state'],'reason':records[oid].get('reason'),
                    'classification':records[oid].get('classification'),'decision':records[oid].get('decision')} for oid in selected},
                'save_and_rerun_no_new_calls':True,'saved_count':len(store.list_records()),'warnings':[w.value for w in at.warning]}
            results.append(result);write_new(OUT/f'scenario-{index}-summary.json',result)
            print(json.dumps({k:v for k,v in result.items() if k!='states'}),flush=True)
    after=deployments();write_new(OUT/'deployments-after.json',after)
    assert before==after
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in protected.items())
    write_new(OUT/'summary.json',{'scenarios':results,'calls':guard.calls,'reserved_usd':guard.reserved,'estimated_actual_usd':guard.actual,'aborted':guard.aborted,'protected_unchanged':True})
    print(json.dumps({'calls':guard.calls,'reserved_usd':guard.reserved,'estimated_actual_usd':guard.actual,'output':str(OUT)}),flush=True)

if __name__=='__main__':main()
