"""Bounded project workflow and user ranking, independent of Streamlit."""
from datetime import datetime
from zoneinfo import ZoneInfo
from services.search_foundation import build_project_review
from services.research_engine import ResearchState


def opportunity_timing(candidate, evidence=None):
    raw=(evidence or {}).get('status') or (evidence or {}).get('opportunity_status') or candidate.get('oppStatus') or candidate.get('status') or ''
    status=str(raw).upper()
    names={'POSTED':'Posted','FORECASTED':'Forecasted','CLOSED':'Closed','ARCHIVED':'Archived'}
    label=names.get(status,'Status unavailable')
    date=candidate.get('closeDate') or candidate.get('close_date')
    # Prefer refreshed official detail over discovery when provided.
    date=(evidence or {}).get('close_date') or date
    closing=None
    for fmt in ('%m/%d/%Y','%Y-%m-%d','%m-%d-%Y'):
        try:closing=datetime.strptime(str(date)[:10],fmt).date();break
        except ValueError:pass
    past=closing is not None and closing<datetime.now(ZoneInfo('America/New_York')).date()
    readiness=('Not accepting applications' if status in {'CLOSED','ARCHIVED'} or past else
               'Forecast — not currently open' if status=='FORECASTED' else
               'Posted; verify notice and preparation requirements' if status=='POSTED' else 'Current availability needs verification')
    return {'status':label,'close_date':closing.isoformat() if closing else date,'past':past,'readiness':readiness,
            'contradiction':status=='POSTED' and past,
            'accepting_possible':status=='POSTED' and not past}


def record_timing(record):
    evidence=record.get('evidence') or {}
    summary=record.get('official_summary') or {}
    latest=summary if summary and str(record.get('summary_checked_at',''))>str(evidence.get('fetched_at','')) else evidence or summary
    return opportunity_timing(record['candidate'],latest)


def shortlist_review(grants,agency,project,cached=(),limit=2,profile=None,fetch_details=None):
    from services.discovery import diversified_retrieval_queries
    from services.matching import project_relevance
    queries=diversified_retrieval_queries({},project)
    terms=' '.join(queries[:3])
    # Returned summaries are often title-only. Inspect a bounded topic-led pool
    # before spending on deep research; preserve all uninspected candidates.
    scored=sorted(grants,key=lambda g:-(project_relevance(terms,g)[0] or 0))
    details={}
    if fetch_details:
        for g in scored[:12]:
            oid=str(g.get('id') or g.get('opportunity_id') or '')
            if oid.isdecimal() and oid not in details:
                try:details[oid]=fetch_details(oid)
                except Exception:details[oid]={}
    signals=[]
    cached_by_id={str(r['opportunity_id']):r for r in cached}
    for g in grants:
        oid=str(g.get('id') or g.get('opportunity_id'))
        prior=cached_by_id.get(oid)
        if prior:signals.append(prior)
    enriched=[{**g,**({'description':details[str(g.get('id') or g.get('opportunity_id'))]['description']}
                    if details.get(str(g.get('id') or g.get('opportunity_id')),{}).get('description') else {})} for g in grants]
    initial=build_project_review(enriched,agency,terms,signals,budget=0,agency_profile=profile)
    rows=sorted(initial['queue']['pool'],key=lambda r:(
        not opportunity_timing(r['records'][0])['accepting_possible'],
        -(r['priority_score'] if r['priority_score'] is not None else -1),r['identity']))
    eligible=[r for r in rows if r['identity'][1].isdecimal() and
              r['decision']['state']!='CONFIRMED_EXCLUSION' and
              opportunity_timing(r['records'][0])['status'] not in {'Closed','Archived'} and
              not opportunity_timing(r['records'][0])['past']]
    # Mostly promising candidates; one uncertain/diverse lead when space permits.
    chosen=eligible[:limit]
    if limit>1 and len(eligible)>limit:
        first_agency=chosen[0]['records'][0].get('agencyCode')
        diverse=next((r for r in eligible[1:] if r['records'][0].get('agencyCode')!=first_agency and
                      (r['priority_score'] or 0)>=max(1,(chosen[0]['priority_score'] or 0)*.75)),None)
        if diverse:chosen[-1]=diverse
    ids=[r['identity'][1] for r in chosen]
    review=build_project_review(enriched,agency,project,cached,budget=limit,selected_ids=ids,agency_profile=profile)
    # Never silently fill unused slots with an expired/unidentified candidate.
    review['queue']['selected']=[r for r in review['queue']['pool'] if r['identity'][1] in ids]
    for row in review['queue']['pool']:
        row['selected']=row['identity'][1] in ids
        row['selection_reason']='Project-fit shortlist; applicant/purpose uncertainty requires research' if row['selected'] else None
    review['queue']['selected_count']=len(ids)
    return review


def display_category(record):
    timing=record_timing(record)
    if timing['past'] or timing['status'] in {'Closed','Archived','Forecasted'}:
        return 'Not suitable or not currently open'
    if record.get('classification')=='CONFIRMED_EXCLUSION':return 'Not suitable or confirmed excluded'
    if record.get('state')==ResearchState.RESEARCH_FAILED.value:return 'Research incomplete'
    if record.get('state')!=ResearchState.RESEARCHED_AND_VALIDATED.value:return 'Preliminary match'
    decision=record['decision']
    findings={d['dimension']:d for d in record.get('analysis',{}).get('dimensions',[])}
    claims=[c for d in findings.values() for c in d.get('claims',[])]+record.get('analysis',{}).get('counterevidence',[])
    contradiction=any(c.get('kind')=='disqualifying_contradiction' and c.get('source_id') for c in claims)
    if contradiction or decision.get('can_act_in_time')=='not_open_or_past' or decision['should_apply']=='reject' or any(findings.get(d,{}).get('assessment')=='conflicting' for d in 'CD'):
        return 'Not suitable or confirmed excluded'
    if decision['should_apply']=='insufficient_evidence' or timing['status']!='Posted':return 'Research incomplete'
    if not all(findings.get(d,{}).get('assessment') in {'supported','conditional'} for d in 'ACD'):
        return 'Research incomplete'
    if record.get('classification')=='ACTIONABLE':return 'Reviewed and promising'
    return 'Conditional — needs verification'


def qualified_records(records,review,earliest_date=None):
    allowed={'Reviewed and promising','Conditional — needs verification'}
    return [r for r in rank_results(records,review) if display_category(r) in allowed and
            (not earliest_date or (record_timing(r).get('close_date') or '')>=earliest_date)]


def funding_note(requested,detail):
    if not requested:return None
    from services.grants_api import _amount
    floor=_amount(detail.get('award_floor'));ceiling=_amount(detail.get('award_ceiling'))
    if ceiling is not None and requested>ceiling:
        return f'Requested ${requested:,.0f} exceeds the listed ${ceiling:,.0f} ceiling; potential partial funding only. Verify match and program-specific limits.'
    if floor is not None and requested<floor:
        return f'Requested ${requested:,.0f} is below the listed ${floor:,.0f} minimum; verify permissible scale and scope.'
    return 'Award limits or match are incomplete; verify funding adequacy.' if floor is None or ceiling is None else 'Requested amount is within the listed award range; verify match and activity-specific limits.'


def rank_results(records,review):
    # Queue selection/reasons are deliberately absent from the user ranking key.
    priority={r['identity'][1]:r['priority_score'] or 0 for r in review['queue']['pool']}
    tiers={'Reviewed and promising':0,'Conditional — needs verification':1,'Preliminary match':2,
           'Research incomplete':3,'Not suitable or not currently open':4,'Not suitable or confirmed excluded':5}
    def key(r):
        score=(r.get('decision') or {}).get('project_activity_score')
        findings={d['dimension']:d['assessment'] for d in r.get('analysis',{}).get('dimensions',[])}
        fit={'supported':0,'conditional':1,'unavailable':2,'conflicting':3}
        timing=record_timing(r)
        return (tiers[display_category(r)],fit.get(findings.get('C'),2),fit.get(findings.get('D'),2),
                not timing['accepting_possible'],
                -(score if score is not None else priority.get(r['opportunity_id'],0)),r['opportunity_id'])
    return sorted(records.values(),key=key)


def run_adaptive_research(grants,agency,project,provider,*,profile=None,previous=None,
                          fetch_details=None,evidence_client=None,on_update=None,
                          triage=None,max_candidates=12,max_calls=24,max_usd=18.,summary_limit=48):
    """Replace failed/unsuitable leads in batches; the Sol contract stays unchanged.

    Safeguards are not coverage claims. Low AI priorities remain in the audit pool
    and receive uncertainty/audit slots before diminishing-return stopping.
    """
    from services.research_engine import (run_research,ResearchBudget,initial_records,
        request_for_candidate,context_key,protocol_hash,ResearchAbort,fingerprint)
    profile=profile or {};factory=lambda g:request_for_candidate(agency,project,g,profile=profile)
    scope=context_key(factory({'id':'scope','title':'scope'}))
    review=build_project_review(grants,agency,project,budget=0,agency_profile=profile)
    records=initial_records(review);previous=previous or {};summaries={};errors=[];aborted=None
    for oid,old in previous.items():
        if oid in records and old.get('context_key')==scope and old.get('protocol_hash')==protocol_hash():
            records[oid]=dict(old)
    def persist():
        if on_update:on_update(records)
    # Inspect a broad topic-led pool, plus overlooked tail candidates. No deletions.
    rows=sorted(review['queue']['pool'],key=lambda r:-(r['priority_score'] or 0))
    ids=[r['identity'][1] for r in rows[:max(0,summary_limit-4)]]
    ids+= [r['identity'][1] for r in rows[-4:] if r['identity'][1] not in ids]
    for oid in ids[:summary_limit]:
        if not oid.isdecimal():continue
        try:
            detail=fetch_details(oid) if fetch_details else {}
            summaries[oid]=detail
            record=records[oid];record['official_summary']=detail
            record['summary_checked_at']=datetime.now(ZoneInfo('UTC')).isoformat()
            record['funding_note']=funding_note(profile.get('funding_needed_usd'),detail)
            record.update(context_key=scope,protocol_hash=protocol_hash())
            g=record['candidate']
            for key,value in [('oppStatus',detail.get('opportunity_status')),('closeDate',detail.get('close_date') or detail.get('estimated_close_date')),
                              ('description',detail.get('description'))]:
                if value:g[key]=value
        except Exception:errors.append('One official summary was unavailable')
    persist()
    available=[oid for oid in summaries if opportunity_timing(records[oid]['candidate'],summaries[oid])['status'] not in {'Closed','Archived','Forecasted'}
               and not opportunity_timing(records[oid]['candidate'],summaries[oid])['past']]
    earliest=profile.get('earliest_closing_date')
    available=[oid for oid in available if not earliest or not opportunity_timing(records[oid]['candidate'],summaries[oid])['close_date']
               or opportunity_timing(records[oid]['candidate'],summaries[oid])['close_date']>=earliest]
    # Summary-only AI understands activities and restrictions; never certifies exclusion.
    if triage:
        for start in range(0,len(available),8):
            batch=available[start:start+8];pending=[]
            for oid in batch:
                key=fingerprint({'summary':summaries[oid],'context':scope})
                if records[oid].get('triage_key')==key and records[oid].get('triage'):continue
                if records[oid].get('triage_inflight'):
                    aborted='Previous priority request completion is ambiguous';break
                records[oid]['triage_inflight']=True;pending.append((factory(records[oid]['candidate']),summaries[oid]))
            if aborted:break
            if not pending:continue
            persist()
            try:
                output=triage(pending)
                for request,detail in pending:
                    oid=request.opportunity.opportunity_id
                    records[oid].update(triage=output['priorities'][oid],triage_key=fingerprint({'summary':detail,'context':scope}),
                        triage_telemetry={k:v for k,v in output.items() if k!='priorities'})
                    records[oid].pop('triage_inflight',None)
            except ResearchAbort as exc:aborted=str(exc);persist();break
            except ValueError:
                for req,_ in pending:records[req.opportunity.opportunity_id].pop('triage_inflight',None)
                errors.append('Summary prioritization failed validation; deterministic and uncertainty paths retained')
            persist()
    budget=ResearchBudget(max_candidates,max_calls,max_usd);attempted=[];audit=0;dry_batches=0
    def priority(oid):
        from services.matching import project_relevance
        return records[oid].get('triage',{}).get('priority_score',project_relevance(project,records[oid]['candidate'],summaries[oid])[0] or 0)
    pending=sorted(available,key=lambda oid:(-priority(oid),oid));reason='Candidate pool exhausted'
    while pending and not aborted:
        if len(attempted)>=max_candidates or budget.used_calls>=max_calls:
            reason='Internal coverage safeguard reached; unexamined candidates remain';break
        useful=qualified_records(records,review,earliest)
        if len(useful)>=5 and not any(priority(oid)>=65 for oid in pending):
            reason='Five qualified leads; higher-priority pool covered';break
        if len(attempted)>=6 and audit>=2 and dry_batches>=2 and all(priority(oid)<40 for oid in pending):
            reason='Diminishing returns after promising pool and overlooked-candidate audit';break
        batch=pending[:min(2,max_candidates-len(attempted))]
        if len(attempted)%4==2 and len(pending)>2:
            batch[-1]=next((oid for oid in reversed(pending) if records[oid].get('triage',{}).get('uncertain',True)),pending[-1]);audit+=1
        for oid in batch:pending.remove(oid)
        batch_review=build_project_review([r['candidate'] for r in records.values()],agency,project,
            budget=len(batch),selected_ids=batch,agency_profile=profile)
        batch_review['queue']['selected']=[r for r in batch_review['queue']['pool'] if r['identity'][1] in batch]
        old_records=dict(records)
        def update(value):
            for oid,r in value.items():
                if oid in batch:
                    records[oid]={**r,**{k:v for k,v in old_records[oid].items() if k in
                        {'official_summary','summary_checked_at','funding_note','triage','triage_key','triage_telemetry'}}}
            persist()
        result=run_research(batch_review,factory,provider,budget=budget,evidence_client=evidence_client,
                            previous=records,on_update=update)
        attempted.extend(batch)
        now=len(qualified_records(records,review,earliest));dry_batches=dry_batches+1 if now==len(useful) else 0
        if result['aborted']:aborted=result['aborted'];reason='Provider stopped safely';break
        if budget.used_calls>=max_calls or budget.reserved_usd>=max_usd:
            reason='Internal coverage safeguard reached; unexamined candidates remain';break
    if aborted:reason='Provider stopped safely'
    persist()
    incomplete=sum(r.get('state')=='RESEARCH_FAILED' for r in records.values())
    return {'records':records,'review':review,'aborted':aborted,'errors':errors,'coverage':{
        'retrieved':len(records),'summaries_checked':len(summaries),'attempted_ids':attempted,
        'pending':len(pending)+len(records)-len(summaries),'summary_screened_out':len(summaries)-len(available),'stop_reason':reason,'incomplete':incomplete,
        'triage_is_not_eligibility':True},'budget':vars(budget)}
