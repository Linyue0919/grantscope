"""Evidence-first Search presentation; experimental precomputed research only."""
import csv
from datetime import datetime, timezone
import hashlib
from io import StringIO
import streamlit as st
from services.search_foundation import build_project_review, load_demo_case
from services.research_engine import (initial_records,request_for_candidate,context_key,run_research,
    ResearchBudget,ResearchStore,AzureSolProvider,ResearchState,protocol_hash,INPUT_TOKEN_BOUND)
from services.grants_api import get_grant_details, GrantsAPIError
from services.research_priority import prioritize_pool,AzureGPT4oPriorityProvider


def save_research_record(store,agency,opportunity_id,updates):
    existing=store.get(agency,opportunity_id) or {}
    old=str(existing.get('notes') or '')
    new=str(updates.get('notes') or '')
    if old and new not in old:
        updates={**updates,'notes':old+'\n\n'+new}
    elif old:
        updates={**updates,'notes':old}
    return store.save(agency,opportunity_id,updates)


def render_demo(store=None):
    with st.expander('Previously researched DEQ example — opportunity 364144',expanded=False):
        st.caption('Experimental GPT-6.1 Sol case study. Previously researched, not freshly generated. Not a general accuracy claim.')
        try:case=load_demo_case()
        except (OSError,ValueError,KeyError):
            st.warning('Previously researched case could not be verified. Live Search remains available.');return
        st.write('**Original project:** '+case['packet']['project'])
        st.write('**Original agency:** '+case['packet']['agency'])
        st.subheader(case['title'])
        d=case['decision']
        st.write('**CONDITIONAL** · Project relevance **45/100** · Strategic relevance **75/100**')
        st.caption('Researched '+case['researched_at']+' · '+case['human_review_status'])
        if st.button('Check current official status (no AI call)',key='research_demo_live_status'):
            try:
                details=get_grant_details('364144')
                st.session_state['research_demo_live_status_result']={'status':details.get('opportunity_status') or 'Unknown',
                    'close_date':details.get('close_date') or 'Unknown','checked_at':datetime.now(timezone.utc).isoformat()}
            except GrantsAPIError:
                st.session_state.pop('research_demo_live_status_result',None)
                st.warning('Live status check failed. Current availability is unverified.')
        live=st.session_state.get('research_demo_live_status_result')
        if live:st.caption(f"Live Grants.gov listed status: {live['status']} · listed closing date: {live['close_date']} · checked {live['checked_at']}. This does not establish application readiness.")
        else:st.caption('Current availability has not been checked in this session. Historical dates below do not establish that this opportunity is open.')
        st.write('**CAN WE APPLY?** Needs review: confirm DEQ is an appropriate/equivalent state agency. State Forester sponsorship and qualifying rural forest land are required; an alternate lead route is unverified.')
        st.write('**SHOULD WE APPLY?** Conditional lead. Monitoring/sensors do not establish the required on-the-ground forest-restoration accomplishment.')
        st.write('**CAN WE ACT IN TIME?** Potentially, with readiness unproven. The historical NOFO requires draft narrative/budget by **December 17, 2026** and final submission by **January 26, 2027, 11:59 p.m. Eastern**. **1:1 nonfederal match** is required for this NC project.')
        st.caption('Timing context: official NOFO PDF pp4,14; applicant p5, match p6, land p7, outcomes p8, equipment p10. Amendment chain remains unverified.')
        st.write(d['decision_rationale'])
        for condition in d['material_conditions']:st.write('• '+condition)
        st.write('**Next verification actions**')
        for action in d['next_actions']:st.write('• '+action)
        with st.expander('Official citations and counterevidence'):
            sources={x['source_id']:x for x in case['packet']['documents']}
            for dimension in case['analysis']['dimensions']:
                st.write('**Dimension '+dimension['dimension']+' — '+dimension['assessment']+'**')
                for claim in dimension['claims']:
                    st.write(claim['kind']+': '+claim['statement'])
                    if claim['source_id']:
                        source=sources[claim['source_id']]
                        st.caption('Source ID: '+claim['source_id'])
                        st.text(claim['quote'])
                        st.link_button('Official source',source['url'])
            for claim in case['analysis']['counterevidence']:st.write('Counterevidence: '+claim['statement'])
        st.link_button('Open official opportunity 364144','https://www.grants.gov/search-results-detail/364144')
        if store is not None and st.button('Save researched DEQ case to My Grants',key='research_demo_save'):
            save_research_record(store,case['packet']['agency'],'364144',{'title':case['title'],'official_url':'https://www.grants.gov/search-results-detail/364144',
                'viability_state':'CONDITIONAL','project_description':case['packet']['project'],'research_depth':'previously researched experimental Sol case',
                'project_relevance':45,'strategic_relevance':75,'researched_at':case['researched_at'],
                'notes':'CONDITIONAL; previously researched GPT-6.1 Sol, project 45/100; strategy 75/100. Not confirmed eligible. Original project: '+case['packet']['project']+' Verify sponsorship, forest land, 1:1 match, route and timing.'})
            st.success('Saved under the original DEQ agency/project scope.')


def render_project_review(grants,agency,project,cached_records,budget,store,agency_profile=None):
    st.subheader('Project research and application viability')
    st.caption('All discovered/cached candidates are retained below. Cached GPT-4o relevance may prioritize research; it cannot establish eligibility or remove a low-scored opportunity. No model calls occur until an explicit paid research action.')
    scope=hashlib.sha256((agency+'\0'+project).encode()).hexdigest()[:16]
    options=sorted({str(g['id']) for g in grants if g.get('id') is not None}|{str(r['opportunity_id']) for r in cached_records})
    chosen=st.multiselect('Prioritize specific opportunities for research',options,key='research_choices_'+scope)
    factory=lambda grant:request_for_candidate(agency,project,grant,profile=agency_profile)
    priority_key='priority_'+context_key(factory({'id':'scope','title':'scope'}))
    priority_results=st.session_state.get(priority_key,{})
    historical_key='dynamic_research_'+context_key(factory({'id':'scope','title':'scope'}))
    try:
        historical=st.session_state.get(historical_key) or ResearchStore().load(historical_key.split('dynamic_research_',1)[1])
    except (ValueError,OSError):historical={}
    present={str(g.get('id') or g.get('opportunity_id')) for g in grants}
    grants=list(grants)+[r['candidate'] for oid,r in historical.items() if oid not in present and r.get('candidate')]
    triage_by_id={str(r['opportunity_id']):r for r in cached_records}
    for oid,value in priority_results.items():
        triage_by_id[oid]={**triage_by_id.get(oid,{}),'opportunity_id':oid,'semantic':{'status':'Prioritized','project_relevance_score':value['priority_score']}}
    triage_records=list(triage_by_id.values())
    review=build_project_review(grants,agency,project,triage_records,budget,chosen,agency_profile=agency_profile)
    queue=review['queue'];selected={r['identity']:r for r in queue['selected']}
    with st.expander('Optional GPT-4o research prioritization (paid)',expanded=False):
        st.caption('Triage only: no candidate is excluded and no eligibility decision is made. Existing successful priorities are reused; low scores remain eligible for uncertainty, user and recall-audit queue paths.')
        priority_limit=int(st.number_input('Maximum triage calls',min_value=1,max_value=20,value=5,key='priority_limit_'+scope))
        priority_usd=float(st.number_input('Maximum triage reference USD',min_value=0.0,max_value=20.0,value=1.0,key='priority_usd_'+scope))
        priority_consent=st.checkbox('I authorize bounded paid GPT-4o prioritization',value=False,key='priority_consent_'+scope)
        if st.button('Prioritize queued candidates with GPT-4o (paid)',key='priority_run_'+scope,disabled=not priority_consent or not queue['selected']):
            try:
                triage=prioritize_pool(review,factory,AzureGPT4oPriorityProvider(st.secrets),priority_limit,priority_usd,previous=priority_results)
                st.session_state[priority_key]=triage['priorities']
                st.session_state[priority_key+'_errors']=triage['errors']
                st.rerun()
            except (ValueError,KeyError,OSError):st.error('Triage could not start safely; no priority was invented.')
        for error in st.session_state.get(priority_key+'_errors',[]):st.warning(error)
    research_records=initial_records(review)
    state_key='dynamic_research_'+context_key(factory({'id':'scope','title':'scope'}))
    cache=ResearchStore()
    try:previous=st.session_state.get(state_key) or cache.load(state_key.split('dynamic_research_',1)[1])
    except (OSError,ValueError):previous={};st.warning('Research cache unavailable; no result will be invented.')
    for oid,record in previous.items():
        if (oid in research_records and record.get('protocol_hash')==protocol_hash()
                and record.get('context_key')==state_key.split('dynamic_research_',1)[1]):
            research_records[oid]={**record,'cache_reused':True}
    with st.expander('Experimental deep research — selected opportunities',expanded=False):
        st.caption('GPT-6.1 Sol researches each selected grant independently from original context and official documents. It does not receive GPT-4o judgments. Citation checks are not human eligibility certification. Missing full notices block research; amendment gaps remain explicit.')
        limit=int(st.number_input('Maximum opportunities this action',min_value=1,max_value=20,value=3,key='dynamic_research_limit_'+scope))
        dollars=float(st.number_input('Maximum estimated USD this action',min_value=0.0,max_value=20.0,value=5.0,step=1.0,key='dynamic_research_usd_'+scope))
        retry=st.checkbox('Explicitly retry previously failed paths (may incur charges)',value=False,key='dynamic_research_retry_'+scope)
        consent=st.checkbox('I authorize this bounded paid deep-research action',value=False,key='dynamic_research_consent_'+scope)
        st.caption('Reference-rate reservation: at most $1.21 per two-stage Sol brief with 175k conservative input bound; subscription tariffs may differ. No automatic retries.')
        if st.button('Research queued opportunities with Sol (paid)',key='dynamic_research_run_'+scope,disabled=not consent or not queue['selected']):
            try:
                provider=AzureSolProvider(st.secrets)
                def persist(records):
                    st.session_state[state_key]=records
                    cache.save(state_key.split('dynamic_research_',1)[1],records)
                with st.spinner('Retrieving official documents and researching the bounded queue...'):
                    run=run_research(review,factory,provider,budget=ResearchBudget(limit,limit*2,dollars),previous=previous,on_update=persist,retry_failed=retry)
                research_records=run['records']
                if run['aborted']:st.error('Research stopped: '+run['aborted']+'. No retry was made.')
                st.caption('Counts by current research state (milestone history retained): '+str(run['summary'])+' · reserved call slots: '+str(run['budget']['used_calls']))
            except (ValueError,OSError,KeyError):st.error('Research could not start or persist safely. No result is being claimed.')
    completed=sum(r.get('state')==ResearchState.RESEARCHED_AND_VALIDATED.value for r in research_records.values())
    st.write(f"**{review['candidate_count']} retained opportunities · {queue['selected_count']} queued · {completed} researched and validated**")
    st.caption('Queue reasons: user choice, uncertainty, agency/program diversity, low-ranked recall audit, cached relevance priority. Selection is a plan, not a completed evaluation. Program diversity depends on returned metadata.')
    display_rows=sorted(queue['pool'],key=lambda r:(not r['selected'],-(r['priority_score'] if r['priority_score'] is not None else -1),r['identity']))
    st.caption('Queued opportunities appear first; all others remain available through the table, export and candidate pages. Keyword aids are never AI recommendations.')
    summary=[]
    for row in display_rows:
        raw=row['records'][0]
        summary.append({'ID':row['identity'][1],'Title':raw.get('title') or 'Untitled',
            'Research state':research_records[row['identity'][1]]['state'],
            'Viability':research_records[row['identity'][1]].get('classification',row['decision']['state']),'GPT-4o priority (not viability)':row['records'][0].get('cached_ai_score'),
            'Priority basis':row['records'][0].get('priority_origin'),
            'Queue reason':row['selection_reason'] or 'Pending — budget/lane capacity',
            'Research depth':research_records[row['identity'][1]].get('research_depth','preliminary')})
    st.dataframe(summary,width="stretch",hide_index=True)
    buffer=StringIO()
    if summary:
        writer=csv.DictWriter(buffer,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)
    st.download_button('Export entire retained pool',buffer.getvalue(),file_name='grantscope-retained-candidates.csv',mime='text/csv')
    if not summary:
        st.info('No opportunities were retrieved. This is a discovery result, not a confirmed eligibility exclusion. Try broader project terms.');return
    pages=max(1,(len(summary)+9)//10)
    page=st.number_input('Candidate page',min_value=1,max_value=pages,value=1,step=1,key='research_page_'+scope)
    for row in display_rows[(int(page)-1)*10:int(page)*10]:
        grant=row['records'][0];oid=row['identity'][1];decision=row['decision'];gate=decision['gate_result']
        deep=research_records[oid]
        if deep.get('state')==ResearchState.RESEARCHED_AND_VALIDATED.value:
            render_dynamic_result(deep,agency,project,store,scope)
            continue
        with st.container(border=True):
            st.subheader(grant.get('title') or 'Untitled opportunity')
            display_state=deep.get('classification',decision['state'])
            st.write(f"**ID {oid} · {display_state}**")
            if deep.get('preliminary_gates'):
                st.caption('Reviewed official exclusion; no deep-model call was required.')
                with st.expander('Source-supported exclusion audit'):
                    for item in deep['preliminary_gates']['audit']:
                        for finding in item['submitted_findings']:
                            st.text(finding['reason'])
                            for citation in finding['citations']:
                                st.text(citation['quote'])
                                for source in item['sources']:
                                    if source['source_id']==citation['source_id']:st.link_button('Official restriction source',source['url'])
            st.caption('Research state: '+deep['state']+' · '+str(deep.get('reason') or ''))
            if deep.get('prior_versions'):
                with st.expander('Prior research versions (audit; not current findings)'):
                    for version in deep['prior_versions']:
                        st.write({'state':version.get('state'),'researched_at':version.get('researched_at'),'classification':version.get('classification'),'input_key':version.get('input_key')})
            st.caption('Discovery / preliminary gates only. Not fully researched. Queue: '+(row['selection_reason'] or 'Pending; retained for later research'))
            st.write('**CAN WE APPLY?** '+('Confirmed restriction applies to the reviewed route; see gate audit.' if display_state=='CONFIRMED_EXCLUSION' else 'Verified for the evaluated application route; see scope and gate audit.' if decision['state']=='ACTIONABLE' else 'Unknown until applicant, exception and partnership conditions are verified.'))
            score=grant.get('cached_ai_score')
            st.write('**SHOULD WE APPLY?** GPT-4o priority (not eligibility): '+(str(score)+'/100' if score is not None else 'unavailable')+'. Funding-purpose suitability and counterevidence require verification. Strategic relevance is not inferred from this score.')
            st.write('**CAN WE ACT IN TIME?** Listed date: '+str(grant.get('closeDate') or 'Unknown')+'. Verify current status, intermediate deadlines, match, sponsorship and preparation requirements.')
            if row.get('official_screen_note'):
                st.caption('Earlier direct-applicant screening note (exceptions/routes still require review): '+str(row['official_screen_note']))
            official=row.get('official_details') or {}
            if official.get('eligibility_description'):
                with st.expander('Available official applicant detail (not the full NOFO)'):
                    st.text(official['eligibility_description'])
                    st.link_button('Official detail source',official.get('detail_source_url') or f'https://www.grants.gov/search-results-detail/{oid}')
            st.write('**Next action:** Review the current official notice and confirm the unresolved requirements before deciding whether to apply.')
            with st.expander('Gate audit and unresolved conditions'):
                for item in gate.gates:st.write(item['gate']+': '+item['state']+' — '+item['reason'])
                for item in gate.audit:
                    for finding in item['submitted_findings']:
                        for citation in finding.citations:
                            st.text(citation.quote)
                            for source in item['sources']:
                                if source.source_id==citation.source_id:st.link_button('Official restriction source',source.url)
            if oid.isdecimal():st.link_button('Official opportunity',f'https://www.grants.gov/search-results-detail/{oid}')
            else:st.caption('Official identity unresolved; no opportunity link or deep-research claim is being invented.')
            if st.button('Save to My Grants',key='research_save_'+scope+'_'+oid,disabled=not oid.isdecimal()):
                save_research_record(store,agency,oid,{'title':grant.get('title') or 'Untitled','official_url':f'https://www.grants.gov/search-results-detail/{oid}',
                    'close_date':grant.get('closeDate'),'viability_state':decision['state'],
                    'research_depth':'preliminary','project_description':project,'notes':decision['state']+'; preliminary only, not fully researched. Original project: '+project+'. Verify official requirements.'})
                st.success('Saved to My Grants with preliminary research status.')


def render_dynamic_result(record,agency,project,store,scope):
    oid=record['opportunity_id'];result=record['shared_result'];decision=record['decision']
    with st.container(border=True):
        st.subheader(record['candidate'].get('title') or 'Researched opportunity')
        st.write('**ID '+oid+' · '+record['classification']+' · RESEARCHED_AND_VALIDATED**')
        st.caption('Experimental Sol; source-specific citations and consistency checked, not independently adjudicated. '+str(record.get('researched_at','')))
        if record.get('cache_reused'):st.caption('Previously researched result reused; inspect research time and evidence freshness before acting.')
        st.write('**CAN WE APPLY?** '+result['can_apply'])
        st.write('**SHOULD WE APPLY?** '+result['should_apply'])
        st.write('**CAN WE ACT IN TIME?** '+result['can_act_in_time'])
        from services.preparation_time import preparation_estimate
        prep=preparation_estimate(record)
        st.write('**Application preparation:** '+prep['summary'])
        st.caption('Confidence: '+prep['confidence']+' · '+(prep['timing'] if prep['available'] else prep['reason']))
        if prep['available']:st.caption('Assumes dedicated staff, parallel drafting/budget work and timely external responses; not an official processing-time standard.')
        st.write('**Project relevance:** '+str(decision['project_activity_score'])+'/100 · **Strategic relevance:** '+(str(decision['strategic_score'])+'/100' if decision['strategic_score'] is not None else 'Unavailable'))
        st.text(decision['decision_rationale'])
        st.caption('Model-proposed viability: '+record['model_viability']+' · Final engine classification: '+record['classification'])
        st.caption('Final gate policy: '+record['final_gate_policy'])
        st.write('**Unresolved conditions**')
        for condition in result['unresolved_requirements']:st.text(condition)
        st.write('**Next actions**')
        for action in result['next_actions']:st.text(action)
        with st.expander('Official sources, evidence and counterevidence'):
            sources={s['source_id']:s for s in record.get('source_documents',record['evidence']['sources'])}
            claims=[c for d in record['analysis']['dimensions'] for c in d['claims']]+record['analysis']['counterevidence']+decision['decision_claims']
            for claim in claims:
                st.text(claim['kind']+': '+claim['statement'])
                if claim['source_id']:
                    source=sources.get(claim['source_id'])
                    st.text(claim['quote'])
                    if source and source.get('url'):st.link_button('Source — '+claim['source_id'],source['url'])
                    elif source:st.caption('User-provided project context; not an official grant requirement')
            st.json(record['evidence']['coverage'])
        st.link_button('Official opportunity',f'https://www.grants.gov/search-results-detail/{oid}')
        if st.button('Save to My Grants',key='dynamic_save_'+scope+'_'+oid):
            save_research_record(store,agency,oid,{'title':record['candidate'].get('title'),'official_url':f'https://www.grants.gov/search-results-detail/{oid}',
                'notes':record['classification']+'; experimental researched result, human review pending. Original project: '+project+' Next actions: '+'; '.join(result['next_actions'])})
            st.success('Saved research context and next actions.')
