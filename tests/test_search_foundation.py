from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import Mock,patch
import pytest
from streamlit.testing.v1 import AppTest
from research_foundation.hard_gates import Finding,State,Source,Citation
from research_foundation.citations import canonicalize
from services.search_foundation import build_project_review,discover_project,load_demo_case
from services.grant_store import LocalGrantStore

AGENCY='Department of Environmental Quality'


def records():
    return [{'opportunity_id':'1','semantic':{'status':'Evaluated','project_relevance_score':99}},
            {'opportunity_id':'2','semantic':{'status':'Evaluated','project_relevance_score':1}},
            {'opportunity_id':'4','title':'Outside seed','semantic':{}}]


def test_full_pool_low_score_cached_ids_and_official_exclusion():
    source=Source('test','https://example.gov/test','Only synthetic institutes may apply.','synthetic-v1','2026-11-07',True)
    exclusion=Finding('applicant',State.CONFIRMED_EXCLUSION,'Synthetic reviewed exclusion',
        (Citation('test','Only synthetic institutes may apply.','test'),),'synthetic-rule',True,True)
    grants=[{'id':'1','title':'High score but excluded'},{'id':'2','title':'Low score retained'},{'id':'3','title':'Unknown'}]
    result=build_project_review(grants,AGENCY,'Water',records(),2,verified_gate_inputs={'1':{'findings':[exclusion],'sources':[source]}})
    rows={r['identity'][1]:r for r in result['queue']['pool']}
    assert set(rows)=={'1','2','3','4'}
    assert rows['1']['decision']['state']=='CONFIRMED_EXCLUSION'
    assert rows['2']['priority_score']==1 and rows['2']['decision']['state']=='INSUFFICIENT_EVIDENCE'
    assert not any(r['deep_research_complete'] for r in rows.values())
    assert len(result['queue']['selected'])==2


def test_diversified_retrieval_failure_keeps_seed_and_duplicate_variants():
    def fetch(q,rows):
        if q=='water':raise RuntimeError('Synthetic outage')
        return [{'id':'1','title':'Alternate variant'}]
    discovery=discover_project(AGENCY,'water',[{'id':'1','title':'Seed'}],fetch)
    assert discovery['grants'][0]['title']=='Seed' and discovery['retrieval_errors']
    review=build_project_review([{'id':'1','title':'Seed'},{'id':'01','title':'Alternate'}],AGENCY,'Water')
    assert review['candidate_count']==1 and len(review['queue']['pool'][0]['records'])==2


def test_published_demo_is_actual_conditional_result_with_official_dates():
    from pathlib import Path
    if not (Path(__file__).resolve().parents[1]/'data/researched_cases/manifest.json').exists():
        pytest.skip('Optional recorded research demo is not distributed')
    case=load_demo_case()
    assert case['decision']['application_viability']=='CONDITIONAL'
    assert case['decision']['project_activity_score']==45 and case['decision']['strategic_score']==75
    notice=canonicalize(next(d['text'] for d in case['packet']['documents'] if d['source_id']=='official-364144-notice'))
    assert 'December 17, 2026' in notice and 'January 26, 2027' in notice
    assert 'State Forester' in notice and '1:1' in notice


def test_actual_search_foundation_no_paid_calls_and_save(tmp_path,monkeypatch):
    monkeypatch.setenv("GRANTSCOPE_LEGACY_SEARCH","1")
    store=LocalGrantStore(tmp_path/'saved.json')
    cache=Mock();cache.get.return_value={'records':records()}
    seed=[{'id':'1','title':'High candidate'},{'id':'2','title':'Low candidate'}]
    with patch('modules.search.LocalGrantStore',return_value=store),patch('modules.search.AIRecommendationCache',return_value=cache),\
         patch('modules.search.get_grants',return_value=seed),patch('modules.search.prepare_ai_recommendations') as paid:
        at=AppTest.from_string('from modules.search import show_search\nshow_search()').run()
        at.selectbox(key='search_agency').select(AGENCY);at.text_area[0].input('Water sensors')
        at.button(key='search_submit').click().run()
        assert not at.exception
        assert 'Low candidate' in [x.value for x in at.subheader]
        assert 'Outside seed' in [x.value for x in at.subheader]
        assert any('INSUFFICIENT_EVIDENCE' in x.value for x in at.markdown)
        key=next(x.key for x in at.button if x.key and x.key.startswith('research_save_') and x.key.endswith('_2'))
        at.button(key=key).click().run()
        assert 'INSUFFICIENT_EVIDENCE' in store.get(AGENCY,'2')['notes']
        paid.assert_not_called();cache.save.assert_not_called()
        from pathlib import Path
        if not (Path(__file__).resolve().parents[1]/'data/researched_cases/manifest.json').exists():
            return  # Core retention and Save assertions above run without optional recorded demo.
        at.checkbox(key='search_show_example').check().run()
        at.button(key='research_demo_save').click().run()
        assert 'CONDITIONAL' in store.get(AGENCY,'364144')['notes']
        assert 'rural North Carolina' in store.get(AGENCY,'364144')['notes']


def test_demo_status_failure_does_not_claim_current_open():
    from pathlib import Path
    if not (Path(__file__).resolve().parents[1]/'data/researched_cases/manifest.json').exists():
        pytest.skip('Optional recorded research demo is not distributed')
    from services.grants_api import GrantsAPIError
    with patch('modules.search_research.get_grant_details',side_effect=GrantsAPIError('Synthetic outage')):
        at=AppTest.from_string('from modules.search_research import render_demo\nrender_demo()').run()
        at.button(key='research_demo_live_status').click().run()
        assert not at.exception
        assert any('Current availability is unverified' in x.value for x in at.warning)
        assert not at.session_state.filtered_state.get('research_demo_live_status_result')


def test_keyword_aid_is_not_an_ai_score_and_saves_preserve_notes(tmp_path):
    from modules.search_research import save_research_record
    review=build_project_review([{'id':'9','title':'Water quality monitoring'}],AGENCY,'water quality monitoring')
    row=review['queue']['pool'][0]
    assert row['priority_score']==100 and row['records'][0]['cached_ai_score'] is None
    assert row['records'][0]['priority_origin']=='Keyword aid (not AI)'
    store=LocalGrantStore(tmp_path/'saved.json');store.save(AGENCY,'9',{'notes':'Coordinator note'})
    save_research_record(store,AGENCY,'9',{'notes':'INSUFFICIENT_EVIDENCE; original project water'})
    saved=store.get(AGENCY,'9')['notes']
    assert saved.startswith('Coordinator note') and 'INSUFFICIENT_EVIDENCE' in saved
    save_research_record(store,AGENCY,'9',{'notes':'INSUFFICIENT_EVIDENCE; original project water'})
    assert store.get(AGENCY,'9')['notes']==saved


def test_demo_wrong_source_is_rejected_even_if_bundle_hash_updated(tmp_path):
    from pathlib import Path
    if not (Path(__file__).resolve().parents[1]/'data/researched_cases/manifest.json').exists():
        pytest.skip('Optional recorded research demo is not distributed')
    import hashlib
    import services.search_foundation as f
    case=load_demo_case()
    claim=next(c for d in case['analysis']['dimensions'] for c in d['claims'] if c['source_id'])
    claim['source_id']='deq-plan-2025-2029-objective-1a'
    p=tmp_path/'case.json';p.write_text(json.dumps(case))
    (tmp_path/'manifest.json').write_text(json.dumps({'364144':{'path':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}}))
    with patch.object(f,'CASE_ROOT',tmp_path),pytest.raises(ValueError,match='citation'):
        f.load_demo_case()


def test_search_uses_shared_contract_without_anchoring_original_packet():
    row=build_project_review([{'id':'1','title':'Water quality'}],AGENCY,'water',records())['queue']['pool'][0]
    decision=row['decision'];shared=decision['shared_result'];packet=decision['original_input_packet']
    assert shared.opportunity_id=='1' and shared.relevance['project']['score']==99
    assert shared.application_viability.actionable is False
    assert 'priority_score' not in json.dumps(packet) and 'project_relevance_score' not in json.dumps(packet)
    assert packet['project_description']=='water'
