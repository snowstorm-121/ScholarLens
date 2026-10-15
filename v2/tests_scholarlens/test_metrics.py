from copy import deepcopy

import pytest

from scholarlens.metrics import aggregate, context_metrics, generation_metrics, retrieval_metrics


def question(answerable=True):
    evidence = [{'paragraph_id': x, 'start': n, 'end': n + 10}
                for x, n in [('a', 0), ('b', 20)]] if answerable else []
    answer = {'unanswerable': not answerable, 'extractive_spans': ['result'] if answerable else [],
              'free_form_answer': '', 'yes_no': None,
              'evidence': ['original a', 'original b'] if answerable else []}
    return {'question_id': 'q', 'paper_id': 'p', 'question': '?', 'answerable': answerable,
            'references': [{'valid': True, 'errors': [], 'annotation_id': 'ann',
                            'answer': answer, 'gold_evidence': evidence}]}


def chunk(pid, start, end, cid=None):
    return {'chunk_id': cid or f'{pid}-{start}-{end}', 'source_label': pid,
            'text': 'abcdefghij'[start:end] if pid == 'a' else 'klmnopqrst',
            'metadata': {'paper_id': 'p', 'paragraph_id': pid, 'start': start, 'end': end}}


def test_manual_ab_and_overlap_union():
    q = question()
    rows = [chunk('a', 0, 10), chunk('z', 30, 40), chunk('b', 20, 30)]
    m = retrieval_metrics(q, rows)
    assert m['EvidenceRecall@1'] == .5 and m['EvidenceRecall@3'] == 1
    assert m['AllEvidence@5'] == 1 and m['MRR@10'] == 1
    split = [chunk('a', 0, 6), chunk('a', 4, 10)]
    assert retrieval_metrics(q, split)['MRR@10'] == .5
    assert context_metrics(q, split)['Context EvidenceRecall'] == .5
    assert retrieval_metrics(q, [chunk('a', 0, 4), chunk('a', 5, 10)])['MRR@10'] == 0


def test_alternative_groups_paper_binding_and_duplicates():
    q = question()
    alt = deepcopy(q['references'][0])
    alt['gold_evidence'] = [{'paragraph_id': 'c', 'start': 40, 'end': 50}]
    q['references'].append(alt)
    assert retrieval_metrics(q, [chunk('c', 40, 50)])['AllEvidence@5'] == 1
    wrong = chunk('a', 0, 10)
    wrong['metadata']['paper_id'] = 'wrong'
    assert retrieval_metrics(q, [wrong])['MRR@10'] == 0
    with pytest.raises(ValueError, match='Duplicate'):
        retrieval_metrics(q, [chunk('a', 0, 10), chunk('a', 0, 10, 'other')])
    with pytest.raises(ValueError, match='Duplicate'):
        retrieval_metrics(q, [chunk('a', 0, 5, 'same'), chunk('a', 5, 10, 'same')])


def prediction():
    row = chunk('a', 0, 10)
    cite = {'number': 1, 'valid': True, 'chunk_id': row['chunk_id'], 'source_label': 'a',
            'paper_id': 'p', 'paragraph_id': 'a', 'start': 0, 'end': 3, 'text': 'abc'}
    blocks = {'a': {'paper_id': 'p', 'start': 0, 'end': 10, 'text': 'abcdefghij',
                    'original_text': 'original a'}}
    return {'answer': 'result【1】', 'status': 'ok', 'error': None,
            'citations': [cite], 'context_chunks': [row]}, blocks


def test_official_f1_used_citations_and_context_distinction():
    pred, blocks = prediction()
    m = generation_metrics(question(), pred, blocks)
    assert m['Answer F1'] == 1 and m['Evidence F1'] == pytest.approx(2/3)
    assert m['predicted_evidence'] == ['original a']
    assert m['citations_valid'] == 1
    pred['answer'] = 'result'
    assert generation_metrics(question(), pred, blocks)['predicted_evidence'] == []
    pred['answer'] = 'CITATION【1】\nFINAL ANSWER\nresult'
    assert generation_metrics(question(), pred, blocks)['predicted_evidence'] == []
    pred['citations'][0]['text'] = 'forged'
    assert generation_metrics(question(), pred, blocks)['citations_valid'] == 0
    pred, blocks = prediction()
    pred['context_chunks'][0].update(text='abc')
    pred['context_chunks'][0]['metadata']['end'] = 3
    assert context_metrics(question(), pred['context_chunks'])['Context EvidenceRecall'] == 0
    assert generation_metrics(question(), pred, blocks)['predicted_evidence'] == ['original a']
    pred['context_chunks'].append(deepcopy(pred['context_chunks'][0]))
    m = generation_metrics(question(), pred, blocks)
    assert m['Answer F1'] == m['Evidence F1'] == 0
    assert 'Duplicate' in m['metric_error']


def test_refusal_failures_mixed_and_thinking():
    q = question(False)
    assert all(v is None for v in retrieval_metrics(q, []).values())
    good = generation_metrics(q, {'answer': '[INSUFFICIENT_EVIDENCE]'}, {})
    assert good['Answer F1'] == good['Evidence F1'] == 1
    for pred in (None, {'answer': '[INSUFFICIENT_EVIDENCE]', 'status': 'error'},
                 {'answer': '<think>secret answer', 'status': 'ok'}):
        m = generation_metrics(q, pred, {})
        assert m['Answer F1'] == m['Evidence F1'] == 0
        assert m['unanswerable_system_error'] == 1
    mixed = generation_metrics(q, {'answer': '[INSUFFICIENT_EVIDENCE] result', 'status': 'invalid_output'}, {})
    assert mixed['unanswerable_wrong_answer'] == 1
    pred, blocks = prediction()
    pred['answer'] = '<think>secret</think>FINAL ANSWER\nresult【1】'
    assert generation_metrics(question(), pred, blocks)['Answer F1'] == 1


def test_aggregate_retains_failure_denominator_and_null_rates():
    rows = [{'answerable': True, 'metrics': {'EvidenceRecall@1': 1}, 'seconds': 2},
            {'answerable': True, 'status': 'error', 'error': 'failed', 'metrics': {}},
            {'answerable': False, 'metrics': {}}]
    m = aggregate(rows, 'retrieval')
    assert m['EvidenceRecall@1'] == .5 and m['system_errors'] == 1
    assert aggregate(rows, 'generation')['Citation traceability'] is None


@pytest.mark.parametrize('status,error,answer,category', [
    ('ok', None, '[INSUFFICIENT_EVIDENCE]', 'correct_refusal'),
    ('invalid_output', None, '[INSUFFICIENT_EVIDENCE]', 'wrong_answer'),
    ('invalid_output', None, 'some substantive answer', 'wrong_answer'),
    ('error', {'type': 'timeout'}, '', 'system_error'),
    ('missing', None, '', 'system_error'),
])
def test_unanswerable_categories_are_exhaustive_exclusive(status, error, answer, category):
    result = generation_metrics(question(False), {'status': status, 'error': error, 'answer': answer}, {})
    categories = ['correct_refusal', 'wrong_answer', 'system_error']
    assert sum(result['unanswerable_' + k] for k in categories) == 1
    assert result['unanswerable_' + category] == 1


def test_reference_groups_cannot_be_mixed_and_mrr_first_paragraph_not_group():
    q = question()
    alt = deepcopy(q['references'][0])
    alt['gold_evidence'] = [{'paragraph_id': 'c', 'start': 40, 'end': 50},
                            {'paragraph_id': 'd', 'start': 60, 'end': 70}]
    q['references'].append(alt)
    result = retrieval_metrics(q, [chunk('a', 0, 10), chunk('c', 40, 50)])
    assert result['EvidenceRecall@3'] == .5
    assert result['AllEvidence@5'] == 0 and result['MRR@10'] == 1


def test_format_compliance_and_generation_aggregate_denominators():
    pred, blocks = prediction()
    pred['citation_errors'] = ['invalid_protocol']
    m = generation_metrics(question(), pred, blocks)
    assert m['citation_eligible'] == 1 and m['citation_compliant'] == 0
    assert m['citations_valid'] == 1  # Location and formatting are distinct.
    rows = []
    for answerable, output in [(False, '[INSUFFICIENT_EVIDENCE]'), (False, 'result'),
                               (False, ''), (True, '[INSUFFICIENT_EVIDENCE]')]:
        rows.append({'answerable': answerable,
                     'metrics': generation_metrics(question(answerable), {'answer': output}, {})})
    summary = aggregate(rows, 'generation')
    assert summary['Correct refusal rate'] == pytest.approx(1/3)
    assert summary['Wrong-answer rate'] == pytest.approx(1/3)
    assert summary['Unanswerable system error rate'] == pytest.approx(1/3)
    assert summary['Wrong refusal rate'] == 1
    assert summary['System error rate'] == .25
    assert 'MRR@10' in summary


def test_raw_open_thinking_cannot_be_rescued_by_qa_extracted_answer():
    pred = {'raw_output': '<think>FINAL ANSWER\nresult', 'answer': 'result',
            'status': 'invalid_output', 'citations': [], 'context_chunks': []}
    m = generation_metrics(question(), pred, {})
    assert m['Answer F1'] == 0
    assert m['metric_error'] == 'empty_scored_answer'


@pytest.mark.parametrize('raw,status', [
    ('CITATION LIST\nCITATION【99】\nFINAL ANSWER\nresult', 'ok'),
    ('invalid prefix\nFINAL ANSWER\nresult', 'invalid_output'),
    ('<think>FINAL ANSWER\nsecret【99】</think>FINAL ANSWER\nresult', 'invalid_output'),
])
def test_raw_protocol_cleanup_precedes_answer_and_used_citation_extraction(raw, status):
    pred, blocks = prediction()
    pred.update(raw_output=raw, answer='wrong extracted answer【1】', status=status)
    result = generation_metrics(question(), pred, blocks)
    assert result['Answer F1'] == 1
    assert result['predicted_evidence'] == []


@pytest.mark.parametrize('raw', ['', '[INSUFFICIENT_EVIDENCE]'])
def test_refusal_raw_or_empty_raw_fallback(raw):
    result = generation_metrics(question(False), {
        'raw_output': raw, 'answer': '[INSUFFICIENT_EVIDENCE]',
        'status': 'insufficient_evidence'}, {})
    assert result['unanswerable_correct_refusal'] == 1
