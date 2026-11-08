"""Focused adaptive coverage, timing and preference regression tests (no network)."""
from copy import deepcopy
from unittest.mock import patch
from datetime import date
from services.search_workflow import run_adaptive_research,display_category,qualified_records
from services.research_engine import request_for_candidate,context_key
from tests.test_dynamic_research import Provider,Evidence,GRANTS

PROJECT='Restore riparian vegetation and monitor water quality for rural North Carolina residents.'


def details(oid):
    return {'opportunity_status':'POSTED','close_date':'2027-12-01','description':'Watershed restoration and water quality monitoring',
            'eligibility_description':'State and local governments may apply','award_ceiling':1000000}


def test_expired_camel_preliminary_cannot_be_recommended():
    record={'candidate':{'id':'361008','title':'CAMEL K-12','oppStatus':'POSTED','closeDate':'10/05/2026'},'state':'NOT_YET_RESEARCHED'}
    assert display_category(record)=='Not suitable or not currently open'


def test_adaptive_replaces_missing_and_rejected_candidates_without_deleting_pool():
    class Rejected(Provider):
        def complete(self,packet,stage,analysis=None):
            result=super().complete(packet,stage,analysis)
            if stage==2 and packet['original_request']['opportunity']['opportunity_id']=='910002':
                result['value']['should_apply']='reject'
            return result
    provider=Rejected()
    result=run_adaptive_research(GRANTS,'NC environment agency',PROJECT,provider,
        fetch_details=details,evidence_client=Evidence(missing=['910001']),max_candidates=8,max_calls=16)
    assert len(result['records'])==4 and len(result['coverage']['attempted_ids'])==4
    assert result['records']['910001']['state']=='RESEARCH_FAILED'
    assert result['records']['910003']['state']=='RESEARCHED_AND_VALIDATED'
    useful=qualified_records(result['records'],result['review'])
    assert {r['opportunity_id'] for r in useful}=={'910003','910004'}
    assert len(provider.calls)==6
    again=run_adaptive_research(GRANTS,'NC environment agency',PROJECT,provider,
        fetch_details=details,evidence_client=Evidence(missing=['910001']),previous=result['records'])
    assert len(provider.calls)==6
    assert again['records']['910001']['state']=='RESEARCH_FAILED'


def test_preferences_isolate_cache_and_exact_date_is_not_readiness():
    a=request_for_candidate('NC agency',PROJECT,GRANTS[0],profile={'funding_needed_usd':250000,'earliest_closing_date':'2026-12-14'})
    b=request_for_candidate('NC agency',PROJECT,GRANTS[0],profile={'funding_needed_usd':300000,'earliest_closing_date':'2026-12-14'})
    c=request_for_candidate('NC agency',PROJECT,GRANTS[0],profile={'funding_needed_usd':250000,'earliest_closing_date':'2026-12-15'})
    assert len({context_key(x) for x in [a,b,c]})==3
    assert a.earliest_closing_date=='2026-12-14' and a.as_of!='2026-12-14'


def test_provider_abort_stops_but_keeps_audit_records():
    provider=Provider(fatal=True)
    result=run_adaptive_research(GRANTS,'NC agency',PROJECT,provider,fetch_details=details,evidence_client=Evidence())
    assert result['aborted'] and len(provider.calls)==1 and len(result['records'])==4


def test_four_inputs_and_vague_project_does_not_make_paid_calls(tmp_path):
    from streamlit.testing.v1 import AppTest
    with patch('modules.search_workflow.configured_provider') as provider:
        at=AppTest.from_string('from modules.search_workflow import show_one_click_search\nshow_one_click_search()').run()
        assert len(at.selectbox)==1 and len(at.text_area)==1 and len(at.number_input)==1 and len(at.date_input)==1
        assert not at.checkbox and not at.text_input
        at.text_area(key='search_project').input('K-12')
        at.button(key='search_submit').click().run()
        provider.assert_not_called()
        assert any('activities' in i.value for i in at.info)


def test_high_score_does_not_override_official_contradiction_or_deadline_conflict():
    record={'candidate':{'id':'123','oppStatus':'POSTED','closeDate':'2027-12-01'},
            'state':'RESEARCHED_AND_VALIDATED','classification':'CONDITIONAL',
            'decision':{'should_apply':'conditional_lead','project_activity_score':95,'can_act_in_time':'needs_review'},
            'analysis':{'dimensions':[{'dimension':d,'assessment':'conditional','claims':[]} for d in 'ACD'],
                        'counterevidence':[{'kind':'disqualifying_contradiction','source_id':'official-notice','quote':'Only a specified region is eligible'}]}}
    assert display_category(record)=='Not suitable or confirmed excluded'
    record['analysis']['counterevidence']=[]
    record['decision']['can_act_in_time']='not_open_or_past'
    assert display_category(record)=='Not suitable or confirmed excluded'


def test_refreshed_official_extension_controls_expired_discovery_date():
    from services.search_workflow import opportunity_timing
    timing=opportunity_timing({'oppStatus':'POSTED','closeDate':'10/05/2026'},
        {'status':'POSTED','close_date':'2027-01-20'})
    assert not timing['past'] and timing['close_date']=='2027-01-20'
    old=opportunity_timing({'oppStatus':'POSTED','closeDate':'10/05/2026'})
    assert old['contradiction'] and old['past']


def test_funding_shortfall_is_explained_without_deleting_partial_funding_lead():
    from services.search_workflow import funding_note
    assert 'partial funding' in funding_note(300000,{'award_ceiling':100000})
    assert 'below' in funding_note(300000,{'award_floor':500000})
    assert 'incomplete' in funding_note(300000,{})


def test_fresh_listing_prevents_old_cached_open_decision_from_being_recommended():
    from services.search_workflow import record_timing
    r={'candidate':{'oppStatus':'POSTED','closeDate':'2027-12-01'},
       'evidence':{'status':'POSTED','close_date':'2027-12-01','fetched_at':'2026-11-07T10:00:00+00:00'},
       'official_summary':{'opportunity_status':'CLOSED','close_date':'2026-10-05'},
       'summary_checked_at':'2026-11-07T12:00:00+00:00','state':'NOT_YET_RESEARCHED'}
    assert record_timing(r)['status']=='Closed'
    assert display_category(r)=='Not suitable or not currently open'
