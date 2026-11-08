"""Project-first Search on Dashboard's shared matching/evidence foundation.

Search retains a conservative Needs Verification state for project-relevant
records whose official status or deadline is unresolved.
"""
import re
from datetime import date
from services.agency_profiles import get_agency_profile
from services.discovery import diversified_retrieval_queries
from services.match_engine import run_matching,MatchSettings,find_terms,OPEN,parse_date
from services.ai_matching import AzureFitEvaluator, load_ai_config
from services.ai_eligibility import AzureEligibilityEvaluator
from services.eligibility_assessment import INELIGIBLE,LIKELY_INELIGIBLE,NOT_CHECKED
from services.research_engine import (request_for_candidate,context_key,ResearchBudget,
                                     run_research,ResearchState,protocol_hash)
from services.search_foundation import build_project_review

# Activity phrases are transparent retrieval/ranking aids, not eligibility rules.
ACTIVITIES={
 'watershed restoration':['watershed restoration','watershed management','stream restoration','river restoration','watershed','stream habitat','river habitat'],
 'riparian/wetland restoration':['riparian','wetland restoration','habitat restoration','wetland conservation','restoration','restore','wetland'],
 'water quality':['water quality','clean water','water pollution'],
 'monitoring':['water monitoring','quality monitoring','monitoring','assessment'],
 'nutrient/runoff reduction':['nutrient','runoff','nonpoint source','stormwater'],
 'flood resilience':['flood mitigation','flood resilience','flood risk','floodplain'],
 'broadband':['broadband','internet access','digital connectivity'],
 'public health':['public health','disease prevention','health preparedness'],
 'cybersecurity':['cybersecurity','cyber security','information security'],
 'education':['teacher training','classroom','student','k-12'],
}


def positive_project_text(project):
    """Explicitly rejected activities are not positive retrieval/fit requirements."""
    return re.sub(r'\b(?:rather than|instead of|not seeking|not proposing|excluding|not involving)\s+[^.;,]+',
                  ' ',project,flags=re.I)


def project_queries(project):
    text=positive_project_text(project);queries=[]
    if re.search(r'mental.health|behavioral.health',text,re.I):
        queries.extend(['rural mental health','behavioral health services','community mental health','telehealth'])
    if re.search(r'\b(?:road|roads|highway|culvert|bridge|crossings?)\b',text,re.I) and re.search(r'flood|resilien',text,re.I):
        queries.extend(['transportation resilience','culvert replacement','flood mitigation','resilient roads'])
    if re.search(r'broadband|last.mile|fiber|high.speed internet',text,re.I):
        queries.extend(['rural broadband','ReConnect','broadband deployment','broadband infrastructure'])
    return list(dict.fromkeys(queries+diversified_retrieval_queries({},text)))[:4]


def project_activity_fit(project,title,description):
    positive=positive_project_text(project)
    groups=dict(ACTIVITIES)
    groups.update({
        'flood resilience':['flood','flood mitigation','flood resilience','flood protection','floodplain','resilient'],
        'roads/culverts':['road','highway','culvert','bridge','crossing','transportation','drainage'],
        'mental/behavioral health':['mental health','behavioral health','behavioral-health','mental illness'],
        'health service delivery':['health services','service delivery','healthcare','telehealth','clinic','crisis services'],
        'digital inclusion':['digital inclusion','digital equity','digital literacy'],
        'broadband':['broadband','internet access','high-speed internet','high speed internet','last-mile','fiber network'],
    })
    requested={k:v for k,v in groups.items() if find_terms(positive,v)}
    water_context=bool(re.search(r'water|riparian|wetland|watershed|habitat|forest',positive,re.I))
    if not water_context:
        requested.pop('riparian/wetland restoration',None);requested.pop('monitoring',None)
    matches=[];title_hits=[]
    for key,terms in requested.items():
        found=find_terms(title+' '+description,terms)
        if found:matches.append({'activity':key,'terms':found})
        if find_terms(title,terms):title_hits.append(key)
    if not requested:
        stop=set('the and for with from north carolina agency department project government residents communities funding seeks would specific require verification intended implementation'.split())
        terms=list(dict.fromkeys(w for w in re.findall(r'[a-z]{5,}',positive.lower()) if w not in stop))
        found=find_terms(title+' '+description[:2000],terms)
        matches=[{'activity':t,'terms':[t]} for t in found];title_hits=find_terms(title,terms)
    matched={m['activity'] for m in matches}
    appropriate=bool(description) and (len(matches)>=2 or len(requested)==1 and bool(title_hits) and requested and next(iter(requested)) not in {'riparian/wetland restoration','monitoring'})
    if 'mental/behavioral health' in requested and 'mental/behavioral health' not in matched:appropriate=False
    if 'roads/culverts' in requested and 'roads/culverts' not in matched:appropriate=False
    if 'broadband' in requested:
        # A specific network purpose in the official summary is useful even for
        # program-brand titles such as ReConnect. Generic digital topics are not.
        appropriate=bool(description) and 'broadband' in matched
    return {'supported_for_screening':bool(appropriate),'matches':matches,'title_matches':title_hits,
            'rank':len(title_hits)*3+len(matches),'basis':'Project activity phrase evidence; not AI suitability or verified allowable activities'}


def project_profile(agency):
    return get_agency_profile(agency)


def search_potential_matches(agency,project,amount=None,earliest=None,*,search_fn,details_fn,
                             today=None,detail_limit=80,notice_fn=None,notice_limit=2,
                             ai_config=None, enable_ai=False, ai_limit=12):
    today=today or date.today();profile=project_profile(agency);details={}
    queries=project_queries(project)
    config=load_ai_config(ai_config) if enable_ai else None
    fit_ai=AzureFitEvaluator(config) if config else None
    eligibility_ai=AzureEligibilityEvaluator(config) if config else None
    result=run_matching(profile,MatchSettings(min_days_left=None,min_award=None,
        include_unknown_deadline=True,detail_limit=detail_limit,max_queries=8,
        ai_limit=ai_limit,ai_eligibility_limit=ai_limit,include_unknown_ai=enable_ai),
        search_fn=search_fn,details_fn=details_fn,today=today,extra_keywords=queries,details_cache=details,
        candidate_ranker=lambda h:project_activity_fit(project,h.get('title',''),h.get('description',''))['rank'],
        prefer_official_deadlines=True,ai_evaluator=fit_ai,
        eligibility_evaluator=eligibility_ai)
    all_records=result['all_records'];potentials=[]
    threshold=parse_date(earliest) if earliest else today
    notice_checks=0
    for record in all_records:
        oid=record['id'];detail=details.get(oid) or {}
        fit=project_activity_fit(project,record['title'],detail.get('description') or '')
        rolling=(str(detail.get('opportunity_status','')).lower()=='posted' and not record['deadline']['close_date'] and
                 bool(re.search(r'no application (?:submission )?deadlines|rolling basis|ongoing basis',detail.get('deadline_note',''),re.I)))
        record['rolling_intake']=bool(rolling)
        # Target the observed synopsis gap: a rolling infrastructure program can
        # permit broadband only in its NOFO, not its generic Grants.gov synopsis.
        if (rolling and not fit['supported_for_screening'] and re.search(r'broadband|fiber',project,re.I)
                and re.search(r'infrastructure|public facilities',detail.get('description',''),re.I)
                and record['eligibility']['status'] not in {INELIGIBLE,LIKELY_INELIGIBLE,NOT_CHECKED}
                and notice_fn and notice_checks<notice_limit):
            notice_checks+=1
            try:
                notice=notice_fn(oid)
                if notice['coverage']['primary_notice_ingested']:
                    for source in notice['sources']:
                        if source.get('kind')!='official_document':continue
                        match=re.search(r'expansion or enhancement[\s\S]{0,400}?broadband infrastructure deployment[.]?',source['text'],re.I)
                        if match and not re.search(r'not (?:fund|allow|eligible)|prohibited',source['text'][max(0,match.start()-100):match.start()],re.I):
                            record['purpose_source']={'source_id':source['source_id'],'url':source['url'],'quote':match.group(),
                                'version':source['version'],'scope':'Official notice excerpt screening only; not Sol verified'}
                            fit=project_activity_fit(project,record['title'],detail.get('description','')+' '+match.group())
                            break
            except Exception:record['notice_screening_gap']='Official notice screening was unavailable; purpose remains unassessed'

        record['project_fit']=fit;record['potential_match']=False;record['project_screening_reasons']=[]
        reasons=record['project_screening_reasons']
        if record['deadline']['status']!=OPEN and not rolling:reasons.append('Not verified as currently open with a closing date')
        if rolling and threshold and threshold>today:reasons.append('Rolling intake has no fixed closing date; the future selected threshold cannot be verified')
        closing=parse_date(record['deadline']['close_date'])
        if closing and threshold and closing<threshold:reasons.append('Closing date is before the selected threshold')
        if not detail:
            failed=any(f'Details for {oid} failed:' in error for error in result['errors'])
            reasons.append('Official details retrieval failed; eligibility and project fit remain unassessed' if failed else 'Official details not inspected: detail-shortlist cap; eligibility and project fit remain unassessed')
        elif record['eligibility']['status']==INELIGIBLE:
            reasons.append('Confirmed direct-applicant restriction; no supported alternative route established')
        elif record['eligibility']['status']==LIKELY_INELIGIBLE:
            reasons.append('Likely direct-applicant restriction (interpretation); alternative route unverified')
        if detail and not fit['supported_for_screening']:reasons.append('Insufficient specific project-activity evidence')
        # Regional restrictions are a project-fit hold, not a fabricated legal exclusion.
        restricted_title=re.search(r'\b(?:for (?:indian )?tribes|for indian tribes|tribal (?:governments|organizations)|intertribal consortia|affiliated partner|fellowship|for universities)\b',record['title'],re.I)
        if restricted_title:reasons.append('Special applicant or affiliation route is not established for the selected agency')
        regions=record['eligibility'].get('region_flags',[])
        if any(region not in project.lower() for region in regions):reasons.append('Regional program scope does not support this NC project')
        scope=(detail.get('eligibility_text','')+' '+detail.get('description','')[:2000]).lower()
        if any(x in scope for x in ['western states','western united states','17 western']) and not any(x in project.lower() for x in ['western united states','western states']):
            reasons.append('Western-state program geography requires a supported NC route')
        whitelist=re.search(r'(?:one of the following states or territories|following states or territories|following states)\s*:\s*([^.]*)',detail.get('eligibility_text',''),re.I)
        if whitelist and ('north carolina' in project.lower() or re.search(r'\bNC\b',project)) and 'north carolina' not in whitelist.group(1).lower():
            reasons.append('Official eligible-location list does not include the proposed North Carolina location')
        if re.search(r'research and development|basic and applied research|research proposals',detail.get('description','')[:800],re.I) and not re.search(r'research and development|experimental|prototype|novel|research study',positive_project_text(project),re.I):
            reasons.append('Research/development purpose is not established by the proposed implementation project')
        research_intent=bool(re.search(r'research and development|research study|clinical trial|experimental|prototype',positive_project_text(project),re.I))
        if not research_intent and (re.search(r'clinical trial|services research|\b(?:R|U|P)[0-9]{2}\b',record['title'],re.I) or
            re.search(r'(?:purpose|objective).{0,180}(?:support|fund|conduct).{0,50}research',detail.get('description','')[:1200],re.I)):
            reasons.append('Research/clinical-study funding purpose does not support the proposed service delivery or implementation scope')
        sentences=re.split(r'(?<=[.!?])\s+(?=[A-Z])',detail.get('description',''))
        record['scope_requirement']=next((text for text in sentences if re.search(r'eligible lands|must be conducted|lands protected through|required|must be sponsored',text,re.I)),None)
        if rolling:record['scope_requirement']='Rolling intake is subject to funds and notice changes, not a confirmed future closing date. Verify current availability, location conditions and eligible project costs.'
        record['funding_preference_note']=None
        floor,ceiling=detail.get('award_floor'),detail.get('award_ceiling')
        if amount and ceiling is not None and amount>ceiling:record['funding_preference_note']='Requested amount exceeds the reported ceiling; partial funding only, if permitted.'
        elif amount and floor is not None and amount<floor:record['funding_preference_note']='Requested amount is below the reported floor; scope/award requirements need review.'
        elif amount and ceiling is None:record['funding_preference_note']='Award ceiling unavailable; funding adequacy is unresolved.'
        record['potential_match']=not reasons
        if not reasons:potentials.append(record)
    potentials.sort(key=lambda r:(-r['project_fit']['rank'],r['eligibility']['status']!='likely_eligible',
                                  bool(r['funding_preference_note']),r['deadline']['close_date'],r['id']))
    needs_verification=[];forecasted=[]
    for record in all_records:
        if record in potentials or not record.get('details_loaded'):
            continue
        if record['eligibility']['status'] == INELIGIBLE:
            continue
        reasons=record.get('project_screening_reasons', [])
        if record['deadline']['status'] == 'forecasted' and record.get('project_fit', {}).get('supported_for_screening'):
            record['forecast_reasons']=reasons
            forecasted.append(record)
            continue
        verification_gap=any(
            phrase in reason for reason in reasons
            for phrase in (
                'Not verified as currently open',
                'Posted, but no closing date',
                'Official details retrieval failed',
            )
        )
        if record.get('project_fit', {}).get('supported_for_screening') and verification_gap:
            record['verification_reasons']=reasons
            needs_verification.append(record)
    needs_verification.sort(key=lambda r:(-r['project_fit']['rank'],r['id']))
    forecasted.sort(key=lambda r:(-r['project_fit']['rank'],r['id']))
    return {'potentials':potentials,'needs_verification':needs_verification,'forecasted':forecasted,
            'all_records':all_records,'details':details,'foundation':result,
            'agency':agency,'project':project,'amount':amount,'earliest':str(earliest) if earliest else None,
            'screening_only':True,'notice_screening_checks':notice_checks}


def research_one_candidate(screening,oid,provider,*,cache,evidence_client=None,on_update=None,retry_failed=False):
    candidate=next((r for r in screening['potentials'] if r['id']==str(oid)),None)
    if not candidate:raise ValueError('Only a screened potential match can be researched from this action')
    profile={'applicant_identity':screening['agency'],'applicant_category':'NC state government agency (user-selected)',
        'geography':['North Carolina'],'funding_needed_usd':screening['amount'],'earliest_closing_date':screening['earliest']}
    factory=lambda g:request_for_candidate(screening['agency'],screening['project'],g,profile=profile)
    hit={'id':oid,'title':candidate['title'],'agencyName':candidate['federal_agency'],
         'oppStatus':'POSTED','closeDate':candidate['deadline']['close_date']}
    scope=context_key(factory(hit));previous=cache.load(scope)
    review=build_project_review([hit],screening['agency'],screening['project'],budget=1,selected_ids=[oid],agency_profile=profile)
    def persist(records):
        cache.save(scope,records)
        if on_update:on_update(records)
    run=run_research(review,factory,provider,budget=ResearchBudget(1,2,2.),previous=previous,
                     evidence_client=evidence_client,on_update=persist,retry_failed=retry_failed)
    return run
