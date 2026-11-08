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


def test_search_uses_dashboard_ai_assessment_pipeline_when_enabled():
    class Fit:
        def __init__(self, config):
            self.calls = []
        def __call__(self, record, profile, details):
            self.calls.append(record["id"])
            return {"status": "ok", "score": 88, "explanation": "Official fit evidence supports the project.",
                    "goal_ids": ["deq-1"],
                    "evidence": [{"source_id": "D", "quote": details["description"]}]}

    class Eligibility:
        def __init__(self, config):
            self.calls = []
        def __call__(self, record, profile, details):
            self.calls.append(record["id"])
            return {"status": "ok", "verdict": "likely_eligible", "reasoning": "State governments are listed.",
                    "quote": "State governments may apply.", "to_verify": []}

    with patch("services.integration_search.AzureFitEvaluator", Fit), \
         patch("services.integration_search.AzureEligibilityEvaluator", Eligibility):
        result = search_potential_matches(
            "Department of Environmental Quality", PROJECT,
            search_fn=lambda *args: HITS,
            details_fn=detail,
            today=date(2026, 11, 7),
            ai_config={"AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
                       "AZURE_OPENAI_API_KEY": "test"},
            enable_ai=True,
        )
    assessed = result["all_records"][0]
    assert assessed["relevance"]["ai"]["status"] == "ok"
    assert assessed["relevance"]["ai"]["score"] == 88
    assert "effort" in assessed


def test_search_ai_failure_keeps_evidence_and_does_not_invent_fit():
    class FailingFit:
        def __init__(self, config):
            pass
        def __call__(self, record, profile, details):
            return {"status": "error", "errors": ["timeout"]}

    with patch("services.integration_search.AzureFitEvaluator", FailingFit), \
         patch("services.integration_search.AzureEligibilityEvaluator", return_value=lambda *args: {"status":"skipped","errors":[]}):
        result = search_potential_matches(
            "Department of Environmental Quality", PROJECT,
            search_fn=lambda *args: HITS,
            details_fn=detail,
            today=date(2026, 11, 7),
            ai_config={"AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
                       "AZURE_OPENAI_API_KEY": "test"},
            enable_ai=True,
        )
    assessed = result["all_records"][0]
    assert assessed["relevance"]["ai"]["status"] == "error"
    assert assessed["relevance"]["ai"].get("score") is None
    assert assessed["effort"]["level"] in {"unknown", "insufficient", "unclear", "fewer_found", "moderate", "higher"}


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


def test_road_work_does_not_match_ecological_restore_or_general_assessment():
    from services.integration_search import project_activity_fit
    project='Upgrade flood-prone roads and undersized culverts in North Carolina to restore drainage; flood-risk assessments require verification.'
    assert not project_activity_fit(project,'Easement Restoration and Stewardship','Wetland restoration, monitoring and assessment of easement conditions.')['supported_for_screening']
    assert project_activity_fit(project,'Resilient transportation crossings','Flood mitigation through replacement of road culverts and bridge drainage.')['supported_for_screening']


def test_negated_trials_are_not_positive_project_requirements_and_mental_topic_is_required():
    from services.integration_search import project_activity_fit,positive_project_text,project_queries
    project='Expand rural mental health service delivery and telehealth clinics in North Carolina rather than clinical trials.'
    assert 'clinical trials' not in positive_project_text(project)
    assert project_queries(project)[0]=='rural mental health'
    assert not project_activity_fit(project,'Cancer screening services','Cancer screening and preventive health services for clinical staff.')['supported_for_screening']
    hits=[{'id':'1','title':'Pilot Mental Health Implementation Trials (R01 Clinical Trial Required)','oppStatus':'posted','closeDate':'12/01/2027'}]
    result=search_potential_matches('Department of Health and Human Services',project,search_fn=lambda *a:hits,
        details_fn=lambda oid:details(desc='Mental health services implementation research.'),today=date(2026,11,7))
    assert not result['potentials']
    assert any('Research/clinical-study' in s for s in result['all_records'][0]['project_screening_reasons'])


def test_description_supported_broadband_brand_title_is_not_rejected():
    from services.integration_search import project_activity_fit
    project='Construct rural broadband fiber infrastructure and support digital inclusion for unserved North Carolina households.'
    assert project_activity_fit(project,'ReConnect Program','Provides funding for construction of rural broadband infrastructure and internet access.')['supported_for_screening']
    assert not project_activity_fit(project,'National Digital Newspaper Program','Digitize newspapers and improve digital archives.')['supported_for_screening']


def test_uninspected_detail_cap_is_not_called_confirmed_ineligibility_or_irrelevance():
    hits=[{'id':str(i),'title':'Water quality watershed restoration','oppStatus':'posted','closeDate':'12/01/2027'} for i in range(3)]
    result=search_potential_matches('Department of Environmental Quality',PROJECT,search_fn=lambda *a:hits,
        details_fn=lambda oid:details(desc='Water quality and watershed restoration.'),today=date(2026,11,7),detail_limit=1)
    unseen=[r for r in result['all_records'] if not r['details_loaded']]
    assert len(unseen)==2
    assert all(any('detail-shortlist cap' in s for s in r['project_screening_reasons']) for r in unseen)
    assert all('Insufficient specific project-activity evidence' not in r['project_screening_reasons'] for r in unseen)


def test_rolling_broadband_permission_requires_official_notice_evidence_and_no_future_date_claim():
    project='Deploy rural broadband infrastructure and fiber internet access for North Carolina communities.'
    hit={'id':'346815','title':'Public Works Program','oppStatus':'posted'}
    d=details(desc='Construction of infrastructure for economic development.')
    d.update(opportunity_status='POSTED',deadline_note='There are no application submission deadlines. Applications are accepted on an ongoing basis.')
    notice={'coverage':{'primary_notice_ingested':True},'sources':[{'source_id':'notice','kind':'official_document',
        'version':'v1','url':'https://example.gov/notice','text':'Supported activities include expansion or enhancement of public facilities with higher quality fiber optic cables and telecommunications infrastructure and broadband infrastructure deployment.'}]}
    kwargs=dict(search_fn=lambda *a:[hit],details_fn=lambda oid:d,today=date(2026,11,7))
    no_notice=search_potential_matches('Department of Information Technology',project,**kwargs)
    assert not no_notice['potentials']
    yes=search_potential_matches('Department of Information Technology',project,notice_fn=lambda oid:notice,**kwargs)
    assert len(yes['potentials'])==1 and yes['potentials'][0]['rolling_intake']
    assert yes['potentials'][0]['purpose_source']['quote'] in notice['sources'][0]['text']
    future=search_potential_matches('Department of Information Technology',project,earliest=date(2027,1,1),notice_fn=lambda oid:notice,**kwargs)
    assert not future['potentials']
    assert any('future selected threshold' in r for r in future['all_records'][0]['project_screening_reasons'])


def test_failed_research_retries_only_on_explicit_action(tmp_path):
    result=screen();cache=ResearchStore(tmp_path/'cache')
    bad=Provider()
    bad.complete=lambda *a,**kw:{'error':'Synthetic completed validation failure','request_sent':False,'fatal':False}
    failed=research_one_candidate(result,'910001',bad,cache=cache,evidence_client=Evidence())
    assert failed['records']['910001']['state']=='RESEARCH_FAILED'
    good=Provider()
    held=research_one_candidate(result,'910001',good,cache=cache,evidence_client=Evidence())
    assert not good.calls and held['records']['910001']['retry_requires_explicit_action']
    retried=research_one_candidate(result,'910001',good,cache=cache,evidence_client=Evidence(),retry_failed=True)
    assert len(good.calls)==2 and retried['records']['910001']['state']=='RESEARCHED_AND_VALIDATED'


def test_streamlit_failed_deep_action_can_be_explicitly_retried_without_autocalls(tmp_path):
    provider=Provider();complete=provider.complete;fail=[True]
    def once(*args,**kwargs):
        if fail[0]:
            fail[0]=False
            return {'error':'Synthetic completed validation failure','request_sent':False,'fatal':False}
        return complete(*args,**kwargs)
    provider.complete=once
    with patch('modules.integrated_search.get_grants',side_effect=lambda *a:HITS),\
         patch('modules.integrated_search.fetch_opportunity_details',side_effect=detail),\
         patch('modules.integrated_search.LocalGrantStore',return_value=LocalGrantStore(tmp_path/'saved.json')),\
         patch('modules.integrated_search.ResearchStore',return_value=ResearchStore(tmp_path/'cache')),\
         patch('modules.integrated_search.configured_provider',return_value=provider) as configured,\
         patch('services.research_engine.OfficialEvidenceClient',return_value=Evidence()):
        at=AppTest.from_string('from modules.integrated_search import show_search_screening\nshow_search_screening()').run()
        at.selectbox(key='search_agency').select('Department of Environmental Quality')
        at.text_area(key='search_project').input(PROJECT)
        at.button(key='search_submit').click().run()
        key=next(b.key for b in at.button if b.key and b.key.startswith('screened_deep_910001_'))
        at.button(key=key).click().run()
        assert not at.exception and at.button(key=key).label=='Retry Deep Research'
        assert not at.button(key=key).disabled and configured.call_count==1
        at.run();assert configured.call_count==1
        at.button(key=key).click().run()
        assert not at.exception and configured.call_count==2 and len(provider.calls)==2


def test_rural_community_services_do_not_match_prison_or_juvenile_justice_only_programs():
    project=('Expand opioid overdose prevention and substance use disorder treatment '
             'in underserved rural North Carolina communities with naloxone, '
             'peer recovery and referrals to evidence-based treatment.')
    hits=[
        {'id':'364043','title':'Residential Substance Abuse Treatment for State Prisoners',
         'oppStatus':'posted','closeDate':'11/20/2026'},
        {'id':'364040','title':'Expanding Youth Access to Community-Based Treatment',
         'oppStatus':'posted','closeDate':'11/16/2026'},
    ]
    descriptions={
        '364043':'Provide substance use treatment for state prisoners in jails and throughout the reentry process.',
        '364040':'Provide community-based treatment for youth involved in the juvenile justice system.',
    }
    result=search_potential_matches(
        'Department of Health and Human Services',project,
        today=date(2026,11,8),search_fn=lambda *args:hits,
        details_fn=lambda oid:details(types=(('00','State governments'),),desc=descriptions[oid]))
    assert not result['potentials']
    records={r['id']:r for r in result['all_records']}
    assert 'incarcerated or reentry' in ' '.join(records['364043']['project_screening_reasons'])
    assert 'juvenile-justice' in ' '.join(records['364040']['project_screening_reasons'])


def test_prison_population_is_not_excluded_when_explicitly_in_project():
    project='Provide substance use treatment for state prisoners in jails and reentry.'
    hit={'id':'364043','title':'Residential Substance Abuse Treatment for State Prisoners',
         'oppStatus':'posted','closeDate':'11/20/2026'}
    result=search_potential_matches(
        'Department of Health and Human Services',project,
        today=date(2026,11,8),search_fn=lambda *args:[hit],
        details_fn=lambda oid:details(types=(('00','State governments'),),
            desc='Provide substance use treatment for state prisoners in jails.'))
    assert not any('incarcerated or reentry' in reason
                   for reason in result['all_records'][0]['project_screening_reasons'])
