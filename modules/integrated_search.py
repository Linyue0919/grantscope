"""Immediate project-screened leads; candidate-specific Sol is an explicit action."""
import json,os,re
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
from modules.profile import get_preferences
from services.agency_directory import AGENCIES
from services.agency_profiles import resolve_agency_name
from services.grants_api import get_grants
from services.opportunity_details import fetch_opportunity_details
from services.integration_search import search_potential_matches,research_one_candidate
from services.official_evidence import OfficialEvidenceClient
from services.research_engine import configured_provider,ResearchStore,fingerprint,ResearchState
from services.grant_store import LocalGrantStore
from modules.search_research import save_research_record
from modules.search_workflow import render_card
from services.search_workflow import display_category
from services.application_effort import assess_effort


def show_search_screening():
    st.header('Find Federal Funding');st.caption('Find fewer grants. Find the right grants. Act sooner.')
    prefs=get_preferences();preferred=resolve_agency_name(prefs.get('agency')) or prefs.get('agency')
    agency=st.selectbox('NC agency',AGENCIES,index=AGENCIES.index(preferred) if preferred in AGENCIES else 0,
                        key='search_agency',accept_new_options=True)
    project=st.text_area('What project are you trying to fund?',key='search_project',placeholder='Describe activities, beneficiaries, location and intended outcomes.').strip()
    amount=st.number_input('Funding needed (USD)',min_value=0.,value=None,key='search_funding')
    today=datetime.now(ZoneInfo('America/New_York')).date()
    threshold=st.date_input('Application deadline on or after',value=today,key='search_earliest_date')
    submit=st.button('Find Matching Grants',type='primary',key='search_submit')
    key='screened_search_'+fingerprint({'agency':agency,'project':project,'amount':amount,'date':str(threshold),'as_of':str(today)})
    if submit:
        if len(re.findall(r'[A-Za-z]+',project))<8:
            st.info('Add the activities, beneficiaries, location and intended outcome. A few sentences are enough.');return
        with st.spinner('Screening live opportunities against your project and official requirements…'):
            try:
                st.session_state[key]=search_potential_matches(
                    agency, project, amount, threshold,
                    search_fn=get_grants, details_fn=fetch_opportunity_details,
                    today=today, notice_fn=OfficialEvidenceClient(max_documents=2).fetch,
                    ai_config=st.secrets, enable_ai=True,
                )
            except Exception:
                st.error('Official opportunity screening could not finish. No matches are being invented.');return
    result=st.session_state.get(key)
    if not result:return
    potentials=result['potentials'];needs_verification=result.get('needs_verification',[]);store=LocalGrantStore()
    st.subheader('Potential Matches')
    st.caption('Project-specific results use the shared Dashboard assessment pipeline, including bounded GPT-4o fit review, official eligibility checks, citation validation, and Application Effort analysis. Results are not legal eligibility determinations.')
    if not potentials:st.info('No sufficiently relevant, open potential matches passed screening. This is a bounded search, not proof that no funding exists.')
    deep=st.session_state.setdefault(key+'_deep',{})
    cache=ResearchStore(os.environ.get('GRANTSCOPE_RESEARCH_CACHE'))
    rejected={oid for oid,r in deep.items() if r.get('state')==ResearchState.RESEARCHED_AND_VALIDATED.value and
              display_category(r) not in {'Reviewed and promising','Conditional — needs verification'}}
    visible=[r for r in potentials if r['id'] not in rejected]
    if rejected:st.info(f'{len(rejected)} screened lead(s) removed from Potential Matches after deep research; findings remain in the audit.')
    for record in visible[:5]:
        oid=record['id'];research=deep.get(oid)
        if research and research.get('state')==ResearchState.RESEARCHED_AND_VALIDATED.value:
            st.caption('Deep research citation and consistency checks passed; eligibility is not legally certified.')
            render_card(research,agency,project,store,key[-16:]);continue
        with st.container(border=True):
            st.subheader(record['title']);st.write('**Potential Match — full research incomplete**')
            st.caption(f"{record['federal_agency']} · Opportunity {oid} · Posted · Closes {record['deadline']['close_date'] or 'No fixed deadline; rolling availability needs verification'}")
            fit=record.get('project_fit', {})
            st.write('**Project Fit:** '+(
                'Supported by official summary activity evidence: '+
                ', '.join(match['activity'] for match in fit.get('matches', []))
                if fit.get('supported_for_screening') else
                'Not established from the official summary; further notice review is required.'
            ))
            relevance=record.get('relevance') or {}
            ai_fit=relevance.get('ai') or {}
            ai_score=ai_fit.get('score')
            strategic_score=relevance.get('fit_score')
            st.write('**Project Fit:** '+(
                f"Shared GPT-4o assessment {ai_score}/100"
                if ai_fit.get('status') == 'ok' and isinstance(ai_score, int)
                else 'Not AI assessed or official evidence was insufficient.'
            ))
            st.write('**Strategic Fit:** '+(
                f"{strategic_score}/100 from verified agency goals"
                if isinstance(strategic_score, int)
                else 'Unavailable; no verified agency goals were supplied.'
            ))
            st.write('**Can we apply?** '+record['eligibility']['summary'])
            activities=', '.join(m['activity'] for m in record['project_fit']['matches'])
            if ai_fit.get('status') == 'ok' and ai_fit.get('explanation'):
                st.write('**Should we apply?** '+ai_fit['explanation'])
            else:
                st.write('**Should we apply?** Official summary contains project activity evidence: '+activities+'. Allowable activities still need NOFO verification.')
            st.write('**Can we act in time?** '+('Rolling intake: confirm funds and current intake; no future closing date is established.' if record.get('rolling_intake') else record['urgency']['label']+'. Intermediate deadlines and preparation time are not yet verified.'))
            st.caption('Official funding: '+record['funding']['display'])
            effort=record.get('effort') or assess_effort(result['details'].get(oid))
            st.write('**Application Effort:** '+effort['label'])
            st.caption(effort['summary'])
            if effort.get('requirements'):
                st.caption('Requirements identified: '+', '.join(item['label'] for item in effort['requirements']))
            if effort.get('not_required'):
                st.caption('Officially not required: '+', '.join(effort['not_required']))
            if not effort.get('requirements') and effort['level'] in {'unknown','insufficient','unclear'}:
                st.caption('Missing information: full announcement requirements are not verified.')
            if record['funding_preference_note']:st.caption(record['funding_preference_note'])
            st.write('**Key concern:** '+(record.get('scope_requirement') or record['eligibility']['reasoning']))
            st.write('**Next action:** Read the controlling notice and confirm legal applicant, geography, activity costs and match before preparing an application.')
            if research:st.warning('Deep research is incomplete: '+str(research.get('reason') or 'Not all checks completed')+'. This has not been verified.')
            with st.expander('Official screening evidence and strategic context'):
                st.write(record['project_fit']['basis']);st.write(record['eligibility']['reasoning'])
                if record['eligibility'].get('quote'):st.text(record['eligibility']['quote'])
                st.text((result['details'].get(oid) or {}).get('description',''))
                if ai_fit.get('evidence'):
                    st.write('**Shared AI evidence validation**')
                    for evidence in ai_fit['evidence']:
                        if evidence.get('quote'):
                            st.text(evidence['quote'])
                        if evidence.get('url'):
                            st.link_button('Official AI evidence source',evidence['url'])
                if record.get('purpose_source'):
                    st.text(record['purpose_source']['quote']);st.link_button('Official notice — screened activity evidence',record['purpose_source']['url'])
                if record.get('rolling_intake'):st.text((result['details'].get(oid) or {}).get('deadline_note',''))
                st.caption('Agency strategic fit is separate from project fit and is a heuristic, not an AI recommendation.')
                for goal in record['relevance'].get('matched_goals',[]):
                    st.text(goal['quote']);st.link_button('Official agency plan',goal['plan_url']+'#page='+str(goal['page']))
                for gap in record['data_gaps']:st.caption(gap)
            st.link_button('Official opportunity',record['source_url'])
            research_label='Retry Deep Research' if research and research.get('state')==ResearchState.RESEARCH_FAILED.value else 'Resume Deep Research' if research else 'Deep Research'
            if st.button(research_label,key='screened_deep_'+oid+'_'+key[-16:],disabled=bool(research and research.get('inflight_stage'))):
                try:
                    with st.spinner('Reading official notices and checking this opportunity…'):
                        run=research_one_candidate(result,oid,configured_provider(st.secrets),cache=cache,
                            retry_failed=bool(research and research.get('state')==ResearchState.RESEARCH_FAILED.value))
                    deep.update(run['records']);st.rerun()
                except Exception:
                    st.warning('Deep research could not start safely. No verified result is being claimed.')
            if st.button('Save to My Grants',key='screened_save_'+oid+'_'+key[-16:]):
                save_research_record(store,agency,oid,{'title':record['title'],'official_url':record['source_url'],
                    'federal_agency':record['federal_agency'],'close_date':record['deadline']['close_date'],
                    'project_description':project,'research_depth':'official-summary screening only',
                    'viability_state':'INSUFFICIENT_EVIDENCE','notes':'Potential Match, not fully researched. Original project: '+project+'. Verify applicant, purpose, geography, match and readiness.'})
                st.success('Saved as an unverified potential match with project context.')
    if needs_verification:
        with st.expander(f'Needs Verification ({len(needs_verification)})'):
            st.caption('These records have project evidence, but current open status, deadline, or another official field could not be verified. They are not confirmed open or eligible.')
            for record in needs_verification[:10]:
                st.write(f"**{record['title']}** · Opportunity {record['id']}")
                st.caption('Project evidence: ' + ', '.join(
                    match['activity'] for match in record['project_fit'].get('matches', [])
                ))
                st.caption('Verification gap: ' + '; '.join(record.get('verification_reasons', [])))
                ai_fit=record.get('relevance', {}).get('ai') or {}
                if ai_fit.get('status') == 'ok':
                    st.caption(f"Shared GPT-4o project assessment: {ai_fit.get('score')}/100; this does not confirm open status or eligibility.")
                st.link_button('Review official opportunity',
                               f"https://www.grants.gov/search-results-detail/{record['id']}")
    with st.expander('Coverage, other candidates and exclusions'):
        foundation=result['foundation'];stats=foundation['stats']
        st.caption(f"{stats['unique_candidates']} unique opportunities retrieved; {stats['details_loaded']} official details checked. Up to eight queries and 100 results per query; coverage is not exhaustive.")
        if len(potentials)>5:st.caption(f'{len(potentials)-5} additional screened leads remain in the audit download.')
        st.download_button('Download screening audit',json.dumps({**result,'deep_research':deep},ensure_ascii=False,default=str),file_name='grantscope-screening-audit.json',mime='application/json')
        st.dataframe([{'ID':r['id'],'Title':r['title'],'Outcome':'Potential Match' if r['potential_match'] else '; '.join(r['project_screening_reasons'])} for r in result['all_records']],hide_index=True)
        for error in foundation['errors'][:5]:st.caption(error)
