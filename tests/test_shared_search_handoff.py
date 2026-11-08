"""Shared Dashboard/Search identity, evidence routing and project-first policy."""
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from services.integration_search import search_potential_matches,research_one_candidate
from services.research_engine import ResearchStore
from services.grant_store import LocalGrantStore
from tests.test_integration_search import HITS,PROJECT,detail,screen
from tests.test_dynamic_research import Provider,Evidence


def test_search_uses_original_dashboard_functions_not_a_second_ai_or_effort_engine():
    import modules.dashboard as dashboard
    import modules.search_workflow as deep_cards
    import modules.integrated_search as search
    import services.integration_search as pipeline
    import services.application_effort as effort
    assert pipeline.run_matching is dashboard.run_matching
    assert pipeline.AzureFitEvaluator is dashboard.AzureFitEvaluator
    assert pipeline.AzureEligibilityEvaluator is dashboard.AzureEligibilityEvaluator
    assert search.assess_effort is dashboard.assess_effort is deep_cards.assess_effort is effort.assess_effort


def test_project_lead_survives_zero_strategic_ai_and_irrelevant_high_ai_is_not_a_match():
    class Fit:
        def __init__(self,config):pass
        def __call__(self,record,*args):
            return {'status':'ok','score':99 if record['id']=='910002' else 0,'goal_ids':[], 'evidence':[],'explanation':'Synthetic strategy assessment'}
    with patch('services.integration_search.AzureFitEvaluator',Fit),patch('services.integration_search.AzureEligibilityEvaluator',return_value=lambda *a:{'status':'skipped'}):
        result=search_potential_matches('Department of Environmental Quality',PROJECT,search_fn=lambda *a:HITS,details_fn=detail,
            ai_config={'AZURE_OPENAI_ENDPOINT':'https://example.openai.azure.com','AZURE_OPENAI_API_KEY':'synthetic'},enable_ai=True)
    assert [r['id'] for r in result['potentials']]==['910001']
    assert len(result['all_records'])==5


def test_deep_effort_uses_full_announcement_channel_and_preserves_official_no_match(tmp_path):
    from services.application_effort import assess_effort
    class EffortEvidence(Evidence):
        def fetch(self,oid):
            evidence=super().fetch(oid)
            evidence['financials']={'cost_sharing':False}
            evidence['sources'][0]['text']='A budget narrative is required. The application must include a project narrative. Cost sharing requirements are described elsewhere.'
            return evidence
    run=research_one_candidate(screen(),'910001',Provider(),cache=ResearchStore(tmp_path/'research'),evidence_client=EffortEvidence())
    row=run['records']['910001']
    captured=[]
    def observe(details,**kwargs):
        result=assess_effort(details,**kwargs);captured.append((details,kwargs,result));return result
    with patch('modules.search_workflow.assess_effort',side_effect=observe):
        at=AppTest.from_string('import streamlit as st\nfrom modules.search_workflow import render_card\nfrom services.grant_store import LocalGrantStore\nrender_card(st.session_state["row"],"Department of Environmental Quality","Water project",LocalGrantStore(st.session_state["path"]),"shared_test")')
        at.session_state['row']=row;at.session_state['path']=str(tmp_path/'saved.json')
        at.run()
    assert not at.exception
    details,kwargs,result=captured[-1]
    assert details['cost_sharing'] is False and kwargs['announcement_url']=='https://example.gov/910001'
    assert result['announcement_analyzed'] and 'Full announcement (NOFO)' in result['sources_checked']
    assert 'cost_sharing' not in [r['key'] for r in result['requirements']]
    assert any('Application Effort:' in m.value for m in at.markdown)
    assert any('Application preparation:' in m.value for m in at.markdown)
