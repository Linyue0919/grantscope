"""Conservative source-specific quotation checks, shared only by offline experiments.

NFC composes Unicode characters; compatibility folding, punctuation replacement,
case folding, synonym/fuzzy matching and cross-source rescue are deliberately absent.
Claim entailment still requires independent human review.
"""
import re
import unicodedata


def canonicalize(text):
    return ' '.join(unicodedata.normalize('NFC', text).split())


def citation_checks(value, packet):
    documents = packet['documents']
    sources = {d['source_id']: d['text'] for d in documents}
    if len(sources) != len(documents):
        raise ValueError('Duplicate frozen source identity')
    claims = [c for d in value['dimensions'] for c in d['claims']] + value['counterevidence']
    rows = []
    for i, claim in enumerate(claims):
        src, quote = claim['source_id'], claim['quote']
        normalized = canonicalize(quote)
        result = {'claim_index': i, 'source_id': src, 'raw_quote': quote,
                  'normalized_quote': normalized, 'raw_match': False,
                  'normalized_match': False, 'category': None, 'passed': False}
        if src in sources:
            result['raw_match'] = bool(quote.strip()) and quote in sources[src]
            result['normalized_match'] = bool(normalized) and normalized in canonicalize(sources[src])
        # Uncertainty is not a license to assert eligibility/readiness as fact.
        statement = claim['statement'].strip()
        assertion = re.search(r'\b(?:DEQ|applicant|agency|project|we|you|it)\s+(?:is|are|can|does|will)\s+(?:directly\s+)?(?:eligible|qualif\w*|apply\b|ready\b|allowable|suitable|meet\w*\s+(?:all\s+)?requirements)', statement, re.I)
        explicit_unknown = re.search(r'\b(?:whether|unconfirmed|unknown|not established|not confirmed|needs verification|not proven|not eligible)\b', statement, re.I)
        # 'Eligible total costs' denotes the base of a cost-share calculation,
        # not an assertion that an applicant or activity is eligible. Keep all
        # other eligibility/permission predicates and exact-source checks intact.
        permission_statement = re.sub(r'\beligible total costs\b', 'total costs', statement, flags=re.I)
        material_inference = (claim['kind'] == 'reasoned_inference'
                              and re.search(r'\b(?:(?:is|are|will be|can be)\s+(?:(?:directly|fully|clearly)\s+)?(?:eligible|ready|allowable|suitable|permitted|funded)|can apply|qualif(?:y|ies)|meets requirements)\b', permission_statement, re.I)
                              and not re.search(r'\b(?:may|might|could|whether|unconfirmed|unknown|not|unresolved|conditional|cannot (?:determine|confirm|establish|verify|assess|conclude))\b', statement, re.I))
        if (assertion and not explicit_unknown) or material_inference:
            result['category'] = 'unsupported_material_assertion'
        elif src is None:
            if claim['kind'] == 'unresolved_requirement' and not quote:
                result.update(category='explicit_uncertainty', passed=True)
            else:
                result['category'] = 'unsupported_uncited_inference'
        elif src not in sources:
            result['category'] = 'unknown_source_id'
        elif not normalized:
            result['category'] = 'missing_quotation'
        else:
            result['raw_match'] = quote in sources[src]
            result['normalized_match'] = normalized in canonicalize(sources[src])
            result['passed'] = result['normalized_match']
            result['category'] = ('exact_match' if result['raw_match'] else
                                  'formatting_only' if result['normalized_match'] else 'attributed_source_mismatch')
        rows.append(result)
    return rows
