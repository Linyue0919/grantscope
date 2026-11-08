import pytest
from research_foundation.citations import canonicalize, citation_checks


def check(quote, text, source='s', statement='An official requirement exists', kind='confirmed_fact'):
    value={'dimensions':[{'claims':[{'source_id':source,'quote':quote,'statement':statement,'kind':kind}]}], 'counterevidence':[]}
    return citation_checks(value, {'documents':[{'source_id':'s','text':text},{'source_id':'other','text':'Wrong source quotation'}]})[0]


def test_safe_normalization_preserves_raw_quote():
    r=check('Café requires $100.\nState applicants only.', 'Cafe\u0301\u00a0requires\r\n$100.   State applicants only.')
    assert r['passed'] and r['category']=='formatting_only'
    assert r['raw_quote'].endswith('only.') and r['normalized_match']
    assert canonicalize('① ½')=='① ½'  # No compatibility folding of numeric characters.


@pytest.mark.parametrize('quote,text', [
    ('Deadline January 27, 2027','Deadline January 26, 2027'),
    ('$300,000 maximum','$100,000 maximum'),
    ('For-profit entities are eligible','For-profit entities are not eligible'),
    ('All state agencies eligible','Only state forestry agencies eligible'),
    ('Restoration allowed','Monitoring allowed'),
])
def test_material_word_changes_never_match(quote,text):
    assert not check(quote,text)['passed']


def test_wrong_source_and_missing_quote_remain_failures():
    assert not check('Wrong source quotation','Unrelated source')['passed']
    assert check('Text','Text',source='unknown')['category']=='unknown_source_id'
    assert check(' ','Text')['category']=='missing_quotation'
    assert check('Exact quotation','Exact quotation')['passed']


def test_unsupported_material_inference_and_explicit_uncertainty():
    assert not check('', 'Text', source=None, statement='DEQ is eligible',kind='reasoned_inference')['passed']
    assert not check('State governments','State governments',statement='DEQ is eligible',kind='reasoned_inference')['passed']
    assert not check('', 'Text', source=None,statement='The project is ready',kind='unresolved_requirement')['passed']
    assert check('', 'Text',source=None,statement='Whether DEQ is eligible remains unknown',kind='unresolved_requirement')['passed']


def test_unqualified_funding_inference_is_blocked_even_with_a_real_quote():
    r=check('Restoration improves water quality','Restoration improves water quality',
            statement='Sensor purchases are allowable',kind='reasoned_inference')
    assert not r['passed'] and r['category']=='unsupported_material_assertion'


def test_cost_share_arithmetic_is_not_an_applicant_eligibility_claim():
    quote='Generally, the cost share for this program is up to 75% federal and 25% non-federal funding.'
    statement='At the general maximum 75% federal share, a $300,000 federal request requires $400,000 in eligible total costs and $100,000 non-federal share. Commitments are absent.'
    assert check(quote,quote,statement=statement,kind='reasoned_inference')['passed']
    assert not check(quote,quote,statement='The project is eligible for $300,000.',kind='reasoned_inference')['passed']
    assert not check(quote,quote,statement='Equipment purchases are allowable as eligible total costs.',kind='reasoned_inference')['passed']
