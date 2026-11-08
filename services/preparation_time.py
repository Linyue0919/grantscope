"""Conservative planning allowances from citation-checked NOFO requirements.

Ranges are uncalibrated staff-planning assumptions, NOT official processing times.
Nothing here changes research, eligibility, quotation validation or cached decisions.
"""
import re
from datetime import date,datetime
from zoneinfo import ZoneInfo
from research_foundation.citations import citation_checks

PATTERNS={
    'proposal':r'\b(?:proposal|project narrative|application narrative)\b',
    'budget':r'\b(?:budget|budget justification)\b',
    'partners':r'\b(?:partners?|partnership|collaborat\w*|sponsor\w*|letters? of (?:support|commitment))\b',
    'match':r'\b(?:match\w*|cost.shar\w*|non.federal share)\b',
    'approvals':r'\b(?:approvals?|authoriz\w*|permits?|signatures?|signing official|signed forms)\b',
    'registrations':r'\b(?:registr\w*|SAM\.?gov|eRA Commons|unique entity identifier|UEI)\b',
    'intermediate deadlines':r'\b(?:letter of intent|intent to apply|pre.application|draft.{0,35}(?:due|deadline|submit\w*)|intermediate deadline|preliminary.{0,25}(?:due|deadline))\b',
}
# Parallel workstreams plus a final review/submission buffer, in calendar days.
ALLOWANCES={'proposal':(14,28),'budget':(7,14),'partners':(14,42),
            'match':(14,42),'approvals':(7,28),'registrations':(21,42)}
MONTHS='January February March April May June July August September October November December'.split()
DATE_PATTERN=r'\b(?:'+'|'.join(MONTHS)+r')\s+\d{1,2},?\s+20\d{2}\b|\b20\d{2}-\d{2}-\d{2}\b'


def _dates(text):
    result=[]
    for match in re.finditer(DATE_PATTERN,text,re.I):
        raw=match.group().replace(',','')
        for fmt in ('%B %d %Y','%Y-%m-%d'):
            try:result.append(datetime.strptime(raw,fmt).date());break
            except ValueError:pass
    return result


def preparation_estimate(record,today=None):
    """Fail closed when prerequisite coverage or intermediate timing is unknown."""
    today=today or datetime.now(ZoneInfo('America/New_York')).date()
    unknown={'available':False,'range':None,'confidence':'Low','assumptions':[],
             'summary':'Cannot estimate reliably.','timing':'Time remaining cannot be assessed reliably.',
             'evidence':[]}
    evidence=record.get('evidence',{})
    if record.get('state')!='RESEARCHED_AND_VALIDATED' or not evidence.get('coverage',{}).get('primary_notice_ingested'):
        return {**unknown,'reason':'Full-notice research has not been validated.'}
    analysis=record.get('analysis')
    documents=record.get('source_documents') or evidence.get('sources',[])
    try:
        if not analysis or not all(row['passed'] for row in citation_checks(analysis,{'documents':documents})):
            return {**unknown,'reason':'Requirement citations could not be verified.'}
    except (ValueError,KeyError,TypeError):return {**unknown,'reason':'Requirement citations could not be verified.'}
    notice_ids={s['source_id'] for s in evidence.get('sources',[]) if s.get('kind')=='official_document'}
    claims=[c for d in analysis['dimensions'] for c in d['claims']]+analysis['counterevidence']
    claims=[c for c in claims if c['source_id'] in notice_ids and c['kind']=='confirmed_fact']
    covered={key:[c for c in claims if re.search(pattern,c['quote'],re.I)] for key,pattern in PATTERNS.items()}
    missing=[key for key,values in covered.items() if not values]
    if missing:return {**unknown,'reason':'NOFO evidence does not establish '+', '.join(missing)+'.'}
    # A mention does not establish a mandatory prerequisite; require explicit
    # requirement/waiver wording before converting a quote to a planning driver.
    waived={};durations=[]
    for key,values in covered.items():
        clauses=[part for c in values for part in re.split(r'(?<=[.;])\s+',c['quote']) if re.search(PATTERNS[key],part,re.I)]
        waived[key]=all(re.search(r'\b(?:not required|no .{0,45}required|no intermediate deadline|optional)\b',part,re.I) for part in clauses)
        if not waived[key] and not any(re.search(r'\b(?:must|required|shall|requires|mandatory)\b',part,re.I) for part in clauses):
            return {**unknown,'reason':f'Whether {key} is required remains unclear.'}
        if key in ALLOWANCES and not waived[key]:durations.append(ALLOWANCES[key])
    intermediate=[]
    if not waived['intermediate deadlines']:
        for c in covered['intermediate deadlines']:
            dates=_dates(c['quote'])
            if len(dates)!=1:return {**unknown,'reason':'Intermediate deadlines need an unambiguous date and year.'}
            intermediate.extend(dates)
    # Respect explicit official registration lead times, without inventing one.
    for c in covered['registrations']:
        for n,business,unit in re.findall(r'\b(\d+)\s+(business\s+)?(weeks?|days?)\b',c['quote'],re.I):
            days=int(n)*(7 if unit.lower().startswith('week') else 1)
            if business and unit.lower().startswith('day'):days=((int(n)+4)//5)*7
            if days>0:durations.append((days,days+14))
    if not durations:return {**unknown,'reason':'Application preparation requirements are not established.'}
    lo=max(x[0] for x in durations)+7;hi=max(x[1] for x in durations)+14
    low_weeks=(lo+6)//7;high_weeks=(hi+6)//7
    from services.search_workflow import record_timing
    timing=record_timing(record);closing=timing.get('close_date')
    try:closing=date.fromisoformat(str(closing)[:10])
    except ValueError:closing=None
    # Final closing date must also occur in a source-checked notice quotation.
    if not closing or not any(closing in _dates(c['quote']) for c in claims):
        return {**unknown,'reason':'Final deadline lacks an unambiguous, source-checked NOFO date.'}
    controlling=min([closing]+intermediate);remaining=(controlling-today).days
    if timing['status']!='Posted':status='Not currently verified as accepting applications.'
    elif remaining<0:status='A required deadline has passed; an extension or reopening must be verified.'
    elif remaining<low_weeks*7:status='Less time remains than the planning range; timely preparation is unlikely under these assumptions.'
    elif remaining<high_weeks*7:status='Tight: only the shorter end of the planning range fits.'
    else:status='The planning range fits before the controlling deadline, subject to these assumptions.'
    return {'available':True,'range':[low_weeks,high_weeks],'confidence':'Low',
        'summary':f'{low_weeks}–{high_weeks} calendar weeks (planning estimate, not a guarantee).',
        'assumptions':['Dedicated staff; proposal and budget work in parallel.',
            'Required partners, match, approvals and registrations start now; external delays may exceed this range.',
            'Ranges use planning allowances, not official processing-time standards; amendment completeness and agency readiness need verification.'],
        'timing':status,'controlling_deadline':controlling.isoformat(),'days_remaining':remaining,
        'evidence':list({(c['source_id'],c['quote']):c for values in covered.values() for c in values}.values())}
