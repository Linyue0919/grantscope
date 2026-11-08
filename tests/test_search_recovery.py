"""Regression coverage for actual failure mechanics and one-click ranking."""
from copy import deepcopy
from unittest.mock import Mock,patch
import json
import pytest
from research_foundation import protocol as p
from services.research_engine import make_packet,AzureSolProvider
from services.search_workflow import opportunity_timing,rank_results,shortlist_review
from tests.test_dynamic_research import Evidence,Provider,factory,GRANTS,make_review


def values():
    packet=make_packet(factory()(GRANTS[0]),Evidence().fetch('910001'))
    provider=Provider();analysis=provider.complete(packet,1)['value']
    decision=provider.complete(packet,2,analysis)['value']
    decision.update(decision_claims=[],evidence_claim_ids=['C-1','D-1','E-1'])
    return packet,analysis,decision


def test_stage_two_references_validated_claims_without_rewriting_quotes():
    packet,analysis,decision=values()
    assert all(c['passed'] for c in p.validate_decision(decision,analysis,packet))
    assert p.resolve_decision_claims(decision,analysis,packet)[0]==analysis['dimensions'][2]['claims'][0]
    bad=deepcopy(decision);bad['evidence_claim_ids']=['C-999']
    with pytest.raises(ValueError,match='claim ID'):p.validate_decision(bad,analysis,packet)
    wrong=deepcopy(analysis);wrong['dimensions'][2]['claims'][0]['source_id']='user-project-context'
    with pytest.raises(ValueError):p.validate_decision(decision,wrong,packet)
    altered=deepcopy(analysis);altered['dimensions'][2]['claims'][0]['quote']='All agencies may apply.'
    with pytest.raises(ValueError):p.validate_decision(decision,altered,packet)


def test_new_assertions_still_require_contiguous_source_specific_quotes():
    packet,analysis,decision=values()
    bad=deepcopy(analysis['dimensions'][2]['claims'][0]);bad['quote']='Watershed ... may apply.'
    decision['decision_claims']=[bad]
    with pytest.raises(ValueError,match='citation'):p.validate_decision(decision,analysis,packet)
    bad.update(source_id=None,kind='unresolved_requirement',quote='unverified metadata')
    with pytest.raises(ValueError,match='citation'):p.validate_decision(decision,analysis,packet)


def test_status_preserves_forecast_closed_and_archive_and_deadlines():
    for status in ['Forecasted','Closed','Archived']:
        result=opportunity_timing({'oppStatus':status,'closeDate':'12/20/2027'})
        assert result['status']==status and not result['accepting_possible']
    assert opportunity_timing({'oppStatus':'POSTED','closeDate':'01/01/2020'})['past']
    assert opportunity_timing({})['status']=='Status unavailable'
    assert not opportunity_timing({})['accepting_possible']


def test_user_ranking_ignores_queue_order_and_high_relevance_reject_is_not_promising():
    review=make_review(count=3)
    records={g['id']:{'opportunity_id':g['id'],'candidate':{**g,'oppStatus':'POSTED','closeDate':'12/01/2027'},
             'state':'RESEARCHED_AND_VALIDATED','classification':'CONDITIONAL',
             'decision':{'should_apply':'conditional_lead','project_activity_score':s}} for g,s in zip(GRANTS,[10,80,99])}
    records['910003']['decision']['should_apply']='reject'
    assert [r['opportunity_id'] for r in rank_results(records,review)]==['910002','910001','910003']
    review['queue']['selected'].reverse()
    assert rank_results(records,review)[0]['opportunity_id']=='910002'


def test_concise_project_queries_and_pool_retention():
    from services.discovery import diversified_retrieval_queries
    text='The North Carolina agency seeks funding to improve rural broadband infrastructure and internet connectivity.'
    queries=diversified_retrieval_queries({},text)
    assert queries[0]=='rural broadband' and all(len(q.split())<=4 for q in queries)
    grants=[{**g,'oppStatus':'POSTED'} for g in GRANTS]
    review=shortlist_review(grants,'NC agency','rural broadband',limit=2)
    assert review['candidate_count']==4 and review['queue']['selected_count']==2
    assert '910002' in {r['identity'][1] for r in review['queue']['selected']}


def test_provider_does_not_sleep_a_minute_between_small_requests():
    packet,analysis,decision=values()
    response=Mock(status_code=200,headers={})
    response.json.return_value={'model':'gpt-6.1-sol-2026-09-29','usage':{'prompt_tokens':100,'completion_tokens':100},
        'choices':[{'finish_reason':'stop','message':{'content':json.dumps(decision)}}]}
    response.text='{}';session=Mock();session.post.return_value=response
    provider=AzureSolProvider({'AZURE_OPENAI_ENDPOINT':'https://example.openai.azure.com','AZURE_OPENAI_API_KEY':'SYNTHETIC_ONLY'},session=session)
    with patch('services.research_engine.time.sleep') as sleep:
        provider.complete(packet,2,analysis);provider.complete(packet,2,analysis)
        sleep.assert_not_called()
    sent=session.post.call_args.kwargs['json']
    assert 'validated_claim_registry' in sent['messages'][1]['content']


def test_dashboard_agency_first_review_does_not_require_a_fake_project_or_reuse_project_scores():
    from services.search_foundation import build_project_review
    from services.research_engine import run_research,ResearchBudget,request_for_candidate
    review=build_project_review(GRANTS[:1],'NC environment agency',None,
        [{'opportunity_id':'910001','semantic':{'status':'Evaluated','project_relevance_score':99}}],
        budget=1,mode='agency_first')
    assert review['queue']['pool'][0]['records'][0]['cached_ai_score'] is None
    original=review['queue']['pool'][0]['decision']['original_input_packet']
    assert original['mode']=='agency_first' and original['project_description'] is None
    result=run_research(review,lambda g:request_for_candidate('NC environment agency',None,g,mode='agency_first'),
        Provider(),evidence_client=Evidence(),budget=ResearchBudget(1,2,2))
    assert result['records']['910001']['state']=='RESEARCHED_AND_VALIDATED'
    assert result['records']['910001']['decision']['project_activity_score'] is None


def test_save_reload_preserves_research_scope_without_losing_coordinator_notes(tmp_path):
    from services.grant_store import LocalGrantStore
    from modules.search_research import save_research_record
    store=LocalGrantStore(tmp_path/'grants.json')
    store.save('NC agency','123',{'notes':'Coordinator note','decision':'Maybe'})
    save_research_record(store,'NC agency','123',{'notes':'Conditional lead','project_description':'Original project',
        'viability_state':'CONDITIONAL','research_depth':'deep; human review pending'})
    saved=LocalGrantStore(store.path).get('NC agency','123')
    assert saved['project_description']=='Original project' and saved['viability_state']=='CONDITIONAL'
    assert saved['decision']=='Maybe' and saved['notes'].startswith('Coordinator note')
