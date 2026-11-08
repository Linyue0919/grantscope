"""Offline integration: official adapters -> Azure validation -> disk -> Search cards."""
import json
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest
from streamlit.util import calc_md5
from services import discovery
from services.grants_api import get_grants, get_grant_details
from services.semantic_matching import evaluate_semantic_match
from services.grant_store import LocalGrantStore
from tests.test_semantic_matching import CONFIG


AGENCY = 'Department of Environmental Quality'
PROJECT = 'Cybersecurity training'


def open_page(app, url_path):
    """Open a top-navigation page. st.Page callables are keyed by md5(url_path);
    AppTest.switch_page only accepts page files, so set the page hash directly."""
    app._page_hash = calc_md5(url_path)
    return app


def test_full_search_pipeline_and_rendering(monkeypatch):
    monkeypatch.setenv("GRANTSCOPE_LEGACY_SEARCH","1")
    calls = []
    broken = {'5': True}

    def post(url, **kwargs):
        response = Mock()
        if 'search2' in url:
            response.json.return_value = {'errorcode': 0, 'data': {'oppHits': [
                {'id': str(i), 'title': title, 'oppStatus': 'posted', 'closeDate': '11/20/2026'}
                for i, title in [(2, 'Cyber training'), (3, 'Astronomy'),
                                 (4, 'Tribal only'), (5, 'Retry grant'), (6, 'No evidence')]]}}
        elif 'fetchOpportunity' in url:
            identifier = str(kwargs['json']['opportunityId'])
            response.json.return_value = {'errorcode': 0, 'data': {'ost': 'POSTED', 'synopsis': {
                'synopsisDesc': '' if identifier == '6' else 'Official cybersecurity training.' if identifier != '3' else 'Official astronomy research.',
                'applicantEligibilityDesc': 'Eligible applicants are federally recognized tribes and intertribal consortia.' if identifier == '4' else '',
            }}}
        else:
            assert 'funding_purpose_status' in kwargs['json']['messages'][0]['content']
            evidence = json.loads(kwargs['json']['messages'][1]['content'])['official_opportunity_evidence']
            title = evidence['title']
            calls.append(title)
            if title == 'Retry grant' and broken['5']:
                content = '{bad json'
            else:
                score = 5 if title == 'Astronomy' else 85
                content = json.dumps({'semantic_relevance_score': score, 'project_relevance_score': score,
                    'funding_purpose_status': 'Supported' if score >= 60 else 'Conflicting',
                    'funding_purpose_fit': 'Official activities support training.' if score >= 60 else 'Astronomy research does not fund cyber training.',
                    'confidence': 'High', 'matched_goal_ids': [],
                    'relevant_opportunity_evidence': [evidence['description']], 'eligibility_concerns': [],
                    'evidence_grounded_explanation': 'Supported by official activities.',
                    'recommended_next_action': 'Verify applicant rules.'})
            response.json.return_value = {'choices': [{'message': {'content': content}}]}
        return response

    with TemporaryDirectory() as directory, patch('requests.post', side_effect=post):
        cache = discovery.AIRecommendationCache(Path(directory) / 'ai.json')
        evaluator = partial(evaluate_semantic_match, request_post=post)
        def prepare(agency, **kwargs):
            return discovery.prepare_ai_recommendations(agency, **{**kwargs, 'cache': cache,
                'config': CONFIG, 'fetch_grants': get_grants, 'fetch_details': get_grant_details,
                'evaluate': evaluator})
        # Initial seed is irrelevant and absent from the diversified candidate set.
        seed = [{'id': '1', 'title': 'Astronomy', 'oppStatus': 'posted', 'closeDate': '11/20/2026'}]
        result = prepare(AGENCY, project_description=PROJECT, seed_grants=seed, max_new_evaluations=10, batch_size=2)
        assert result['summary']['succeeded'] == 3
        assert result['summary']['failed'] == 2
        assert result['summary']['skipped_ineligible'] == 1
        assert len(result['records']) == 6
        before = len(calls)
        broken['5'] = False
        resumed = prepare(AGENCY, project_description=PROJECT, seed_grants=seed, max_new_evaluations=1)
        assert len(calls) == before + 1
        assert len(resumed['records']) == 6
        assert cache.get(AGENCY, 'other project') is None
        assert cache.get('other agency', PROJECT) is None
        assert cache.get(AGENCY, PROJECT)['records'] == resumed['records']
        store = LocalGrantStore(Path(directory) / 'saved.json')
        with patch('modules.search.AIRecommendationCache', return_value=cache), \
             patch('modules.search.get_grants', return_value=seed), \
             patch('modules.search.prepare_ai_recommendations', side_effect=prepare), \
             patch('modules.search.LocalGrantStore', return_value=store), \
             patch('modules.my_grants.LocalGrantStore', return_value=store):
            app = AppTest.from_file('app.py').run()
            open_page(app, 'browse').run()
            app.checkbox(key='search_foundation_enabled').uncheck().run()
            app.checkbox(key='search_allow_new_ai').check().run()
            app.selectbox(key='search_agency').select(AGENCY)
            app.text_area[0].input(PROJECT)
            app.button(key='search_submit').click().run()
            assert not app.exception
            titles = [item.value for item in app.subheader]
            assert 'Cyber training' in titles
            assert 'Retry grant' in titles
            assert 'Astronomy' not in titles
            assert 'Tribal only' not in titles
            assert any('AI project fit:' in item.value and '85/100' in item.value for item in app.markdown)
            app.button(key=f'bookmark_{AGENCY}::2').click().run()
            assert store.get(AGENCY, '2')['title'] == 'Cyber training'
            open_page(app, 'my-grants').run()
            assert not app.exception
            assert 'Cyber training' in [item.value for item in app.subheader]
            open_page(app, 'browse').run()
            app.checkbox(key='search_foundation_enabled').uncheck().run()
            app.checkbox(key='search_allow_new_ai').check().run()
            app.selectbox(key='search_agency').select(AGENCY)
            app.text_area[0].input(PROJECT).run()
            before = len(calls)
            app.button(key='search_analyze_more').click().run()
            assert not app.exception
            assert len(calls) == before
            app.slider(key='search_minimum_ai_score').set_value(90).run()
            assert not app.exception
            assert 'Cyber training' not in [item.value for item in app.subheader]
            assert len(calls) == before
            app.text_area[0].input('Different project').run()
            assert any('Agency or project changed' in item.value for item in app.info)
            assert 'Cyber training' not in [item.value for item in app.subheader]


def test_blank_evidence_is_rejected():
    from services.semantic_matching import _validate_result
    import pytest
    raw = {'semantic_relevance_score': 90, 'confidence': 'High', 'matched_goal_ids': [],
           'relevant_opportunity_evidence': [' '], 'eligibility_concerns': [],
           'evidence_grounded_explanation': 'Claim', 'recommended_next_action': 'Check'}
    with pytest.raises(ValueError, match='snippets'):
        _validate_result(raw, None, {'description': 'Official'}, AGENCY, None, PROJECT)


def test_official_cached_leads_and_acceptance_gates():
    """Quotes exist for both 70s; suitability and readiness still govern action."""
    from services.discovery import classify_recommendation
    from services.eligibility import screen_eligibility
    from services.grants_api import plain_official_text
    root = Path(__file__).resolve().parents[1]
    for identifier in ('357554', '347707'):
        official = json.loads((root / 'docs' / 'acceptance-evidence' / f'{identifier}.json').read_text())
        fields = official['fields']
        response = Mock()
        response.json.return_value = {'errorcode': 0, 'data': {
            'ost': official['status'], official['docType']: fields}}
        with patch('requests.post', return_value=response):
            adapted = get_grant_details(identifier)
        assert adapted['opportunity_status'] == official['status']
        if identifier == '347707':
            assert 'deepen connections between the Philippines' in adapted['funding_activity_description']
            assert adapted['close_date'] is None
            assert adapted['estimated_close_date'] == '2023-05-22'
        else:
            assert adapted['close_date'] == '2027-01-25'
            assert 'accepted anytime' in adapted['deadline_note']
        details = {'description': plain_official_text(fields.get('synopsisDesc') or fields.get('forecastDesc')),
                   'eligibility_description': plain_official_text(fields['applicantEligibilityDesc'])}
        screened = screen_eligibility(details, 'Department of Public Schools')
        if identifier == '357554':
            assert screened['status'] == 'Ineligible'
            assert 'education and workforce training' in details['description']
        else:
            assert official['status'] == 'FORECASTED'
            assert fields['estApplicationResponseDateStr'].startswith('2023-05-22')
            assert 'deepen connections between the Philippines' in fields['fundingActivityCategoryDesc']
        record = {'opportunity_id': identifier, 'eligibility_status': screened['status'],
                  'opportunity_status': official['status'], 'close_date': fields.get('responseDateStr', '')}
        high_topic_score = {'status': 'Evaluated', 'project_relevance_score': 70,
                            'evidence_verified': True, 'funding_purpose_status': 'Supported', 'funding_purpose_fit': 'Official activities support this purpose.'}
        assert classify_recommendation(record, high_topic_score, project_description=PROJECT)['classification'] != 'Recommended'


def test_high_score_does_not_override_purpose_or_readiness():
    from services.discovery import classify_recommendation
    record = {'opportunity_id': '2', 'eligibility_status': 'Needs Review',
              'opportunity_status': 'Posted', 'close_date': '2027-01-25'}
    semantic = {'status': 'Evaluated', 'project_relevance_score': 95, 'evidence_verified': True,
                'funding_purpose_status': 'Supported', 'funding_purpose_fit': 'Official activities support this purpose.'}
    assert classify_recommendation(record, semantic, project_description=PROJECT)['classification'] == 'Recommended'
    for status in ('Conflicting', 'Unclear', None):
        assert classify_recommendation(record, {**semantic, 'funding_purpose_status': status}, project_description=PROJECT)['classification'] == 'Needs Evidence Review'
    for status, closing in [('Closed', '2027-01-25'), ('Archived', '2027-01-25'), ('Forecasted', '2027-01-25'), ('Unknown', '2027-01-25'), ('Posted', '2023-05-22'), ('Posted', '')]:
        assert classify_recommendation({**record, 'opportunity_status': status, 'close_date': closing}, semantic, project_description=PROJECT)['classification'] != 'Recommended'
    assert classify_recommendation(record, {**semantic, 'eligibility_concerns': ['University lead needed']}, project_description=PROJECT)['classification'] != 'Recommended'


def test_unrestricted_deadline_and_unavailable_strategic_goals():
    from modules.search import filter_by_deadline
    from services.semantic_matching import _validate_result
    from datetime import date
    grants = [{'id': 'long', 'closeDate': '2027-01-25'}, {'id': 'past', 'closeDate': '2023-05-22'}, {'id': 'missing'}]
    assert [r['id'] for r in filter_by_deadline(grants, None, today=date(2026, 11, 7))[0]] == ['long']
    assert filter_by_deadline(grants, 30, today=date(2026, 11, 7))[0] == []
    raw = {'semantic_relevance_score': 90, 'strategic_relevance_score': 99, 'confidence': 'High',
           'matched_goal_ids': [], 'relevant_opportunity_evidence': ['Official'], 'eligibility_concerns': [],
           'evidence_grounded_explanation': 'Claim', 'recommended_next_action': 'Check'}
    assert _validate_result(raw, None, {'description': 'Official'}, AGENCY, None, PROJECT)['strategic_relevance_score'] is None
