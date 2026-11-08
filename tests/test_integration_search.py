"""Integrated project screening/explicit research tests; no network or paid calls."""
from datetime import date
from unittest.mock import patch,Mock
from streamlit.testing.v1 import AppTest
from services.integration_search import search_potential_matches,research_one_candidate
from services.research_engine import ResearchStore
from services.grant_store import LocalGrantStore
from tests.test_match_engine import details
from tests.test_dynamic_research import Provider,Evidence

PROJECT='Restore riparian vegetation and monitor water quality to reduce nutrient runoff for residents in North Carolina watersheds.'
HITS=[{'id':'910001','title':'Watershed restoration and water quality monitoring','oppStatus':'posted','closeDate':'12/01/2027','agencyCode':'EPA'},
      {'id':'910002','title':'Cybersecurity university training','oppStatus':'posted','closeDate':'12/01/2027'},
      {'id':'361008','title':'CAMEL K-12 water quality monitoring','oppStatus':'posted','closeDate':'10/05/2026'},
      {'id':'910003','title':'Water quality monitoring and riparian restoration','oppStatus':'posted','closeDate':'12/01/2027'},
      {'id':'910004','title':'Great Lakes watershed restoration','oppStatus':'posted','closeDate':'12/01/2027'}]


def detail(oid):
    return details(types=(('06','Public universities'),) if oid=='910003' else (('00','State governments'),),
        desc='Watershed restoration, water quality monitoring and nutrient runoff reduction.' if oid!='910002' else 'Cybersecurity training for university researchers.')


def screen():
    return search_potential_matches('Department of Environmental Quality',PROJECT,300000,date(2026,11,7),
        today=date(2026,11,7),search_fn=lambda *a:HITS,details_fn=detail)


def test_project_screen_reuses_dashboard_and_excludes_irrelevance_ineligibility_expiry_and_region():
    result=screen()
    assert [r['id'] for r in result['potentials']]==['910001']
    assert len(result['all_records'])==5
    assert result['potentials'][0]['eligibility']['status']=='likely_eligible'
    assert result['potentials'][0]['relevance']['matched_goals'] # actual Dashboard agency-plan contract


def test_deep_action_only_researches_clicked_id_and_reuses_cache(tmp_path):
    result=screen();provider=Provider();cache=ResearchStore(tmp_path/'cache')
    run=research_one_candidate(result,'910001',provider,cache=cache,evidence_client=Evidence())
    assert [(oid,stage) for oid,stage,_ in provider.calls]==[('910001',1),('910001',2)]
    assert run['records']['910001']['state']=='RESEARCHED_AND_VALIDATED'
    research_one_candidate(result,'910001',provider,cache=cache,evidence_client=Evidence())
    assert len(provider.calls)==2
    import pytest
    with pytest.raises(ValueError):research_one_candidate(result,'910003',provider,cache=cache)


def test_streamlit_immediate_matches_no_provider_until_deep_action_save_and_rerun(tmp_path):
    store=LocalGrantStore(tmp_path/'saved.json');provider=Provider()
    with patch('modules.integrated_search.get_grants',side_effect=lambda *a:HITS),\
         patch('modules.integrated_search.fetch_opportunity_details',side_effect=detail),\
         patch('modules.integrated_search.LocalGrantStore',return_value=store),\
         patch('modules.integrated_search.ResearchStore',return_value=ResearchStore(tmp_path/'cache')),\
         patch('modules.integrated_search.configured_provider',return_value=provider) as configured,\
         patch('services.research_engine.OfficialEvidenceClient',return_value=Evidence()):
        at=AppTest.from_string('from modules.search import show_search\nshow_search()').run()
        assert len(at.selectbox)==1 and len(at.text_area)==1 and len(at.number_input)==1 and len(at.date_input)==1
        at.text_area(key='search_project').input(PROJECT)
        at.button(key='search_submit').click().run()
        assert not at.exception
        assert 'Watershed restoration and water quality monitoring' in [s.value for s in at.subheader]
        assert 'Cybersecurity university training' not in [s.value for s in at.subheader]
        configured.assert_not_called();assert not provider.calls
        save=next(b.key for b in at.button if b.key.startswith('screened_save_'))
        at.button(key=save).click().run();assert store.get('Department of Environmental Quality','910001')
        deep=next(b.key for b in at.button if b.key.startswith('screened_deep_'))
        at.button(key=deep).click().run();assert not at.exception and len(provider.calls)==2
        at.run();assert len(provider.calls)==2
        assert any('checks passed' in c.value for c in at.caption)


def test_tribal_only_title_with_uninformative_notes_is_not_a_deq_potential():
    hits=[{'id':'363611','title':'Funding for Indian Tribes and Intertribal Consortia for Water Quality Monitoring',
           'oppStatus':'posted','closeDate':'12/01/2027'}]
    d=details(types=(('25','Others'),),text='See Section 2 of Notice of Funding Opportunity',
              desc='Water quality monitoring and watershed restoration.')
    result=search_potential_matches('Department of Environmental Quality',PROJECT,
        search_fn=lambda *a:hits,details_fn=lambda oid:d,today=date(2026,11,7))
    assert not result['potentials'] and len(result['all_records'])==1
    assert any('Special applicant' in reason for reason in result['all_records'][0]['project_screening_reasons'])


def test_separated_watershed_restoration_language_is_understood_without_strategic_score():
    from services.integration_search import project_activity_fit
    fit=project_activity_fit(PROJECT,'Watershed management planning',
        'Funding for watershed group development, restoration planning and watershed management project planning.')
    assert fit['supported_for_screening'] and len(fit['matches'])>=2


def test_explicit_non_nc_whitelist_and_rd_only_purpose_are_held_out():
    hits=[{'id':'1','title':'Watershed restoration and water quality','oppStatus':'posted','closeDate':'12/01/2027'},
          {'id':'2','title':'Water quality and wetland restoration','oppStatus':'posted','closeDate':'12/01/2027'}]
    def official(oid):
        return details(text='Must be located in one of the following states or territories: Arizona, California, Utah.' if oid=='1' else '',
            desc='Watershed restoration and water quality.' if oid=='1' else 'This research and development opportunity addresses water quality and wetland restoration.')
    result=search_potential_matches('Department of Environmental Quality',PROJECT,search_fn=lambda *a:hits,
                                    details_fn=official,today=date(2026,11,7))
    assert not result['potentials'] and len(result['all_records'])==2
    assert any('eligible-location' in s for s in result['all_records'][0]['project_screening_reasons'])
