"""Span coverage metrics and a thin adapter to the unmodified QASPER scorer."""

import re

from .dataset import official_gold
from .vendor.qasper_evaluator import evaluate, get_answers_and_evidence


RETRIEVAL_KEYS = ('EvidenceRecall@1', 'EvidenceRecall@3', 'EvidenceRecall@5',
                  'AllEvidence@5', 'MRR@10')
REFUSAL = '[INSUFFICIENT_EVIDENCE]'


def _spans(rows):
    spans, ids = [], set()
    for row in rows:
        meta = row.get('metadata', row)
        span = tuple(meta[k] for k in ('paper_id', 'paragraph_id', 'start', 'end'))
        if (type(span[2]) is not int or type(span[3]) is not int
                or span[2] < 0 or span[3] <= span[2]):
            raise ValueError('Invalid normalized chunk span')
        cid = row.get('chunk_id')
        if span in spans or (cid is not None and cid in ids):
            raise ValueError('Duplicate chunk ID or exact span; ranks cannot be compressed')
        spans.append(span)
        if cid is not None:
            ids.add(cid)
    return spans


def _groups(question):
    return [r['gold_evidence'] for r in question['references']
            if r.get('valid', True) and not r.get('errors') and r['gold_evidence']]


def _covered(evidence, spans, paper_id):
    cursor = evidence['start']
    for pid, paragraph, start, end in sorted(spans, key=lambda s: s[2]):
        if pid != paper_id or paragraph != evidence['paragraph_id']:
            continue
        if start > cursor:
            return False
        if end > cursor:
            cursor = end
        if cursor >= evidence['end']:
            return True
    return False


def _recall(question, spans):
    groups = _groups(question)
    if not groups:
        raise ValueError('Answerable question has no valid evidence group')
    return max(sum(_covered(e, spans, question['paper_id']) for e in group) / len(group)
               for group in groups)


def retrieval_metrics(question, rows):
    if not question['answerable']:
        return dict.fromkeys(RETRIEVAL_KEYS)
    spans = _spans(rows)
    result = {f'EvidenceRecall@{k}': _recall(question, spans[:k]) for k in (1, 3, 5)}
    result['AllEvidence@5'] = float(result['EvidenceRecall@5'] == 1)
    result['MRR@10'] = next((1 / k for k in range(1, min(10, len(spans)) + 1)
                            if any(_covered(e, spans[:k], question['paper_id'])
                                   for group in _groups(question) for e in group)), 0.0)
    return result


def context_metrics(question, rows):
    if not question['answerable']:
        return {'Context EvidenceRecall': None, 'Context AllEvidence': None}
    recall = _recall(question, _spans(rows))
    return {'Context EvidenceRecall': recall, 'Context AllEvidence': float(recall == 1)}


def _final_body(text):
    # An unclosed think block must not leak reasoning into a scored answer.
    text = re.sub(r'<think\b[^>]*>.*?(?:</think\s*>|$)', '', text,
                  flags=re.I | re.S)
    if 'FINAL ANSWER' in text:
        text = text.rsplit('FINAL ANSWER', 1)[-1]
    return text.strip()


def generation_metrics(question, prediction, paragraphs):
    prediction = prediction or {}
    text = prediction.get('raw_output') or prediction.get('answer', '')
    final_text = _final_body(text)
    clean = re.sub(r'【\d+】', '', final_text).strip()
    used = {int(n) for n in re.findall(r'【(\d+)】', final_text)}
    citations = prediction.get('citations', [])
    context = prediction.get('context_chunks', [])
    metric_error = None
    try:
        _spans(context)
        numbers = [c['number'] for c in citations]
        if len(numbers) != len(set(numbers)):
            raise ValueError('Duplicate citation number')
    except (ValueError, KeyError) as exc:
        metric_error = str(exc)
    if not clean and metric_error is None:
        metric_error = 'empty_scored_answer'
    failed = (not clean or prediction.get('error') is not None or metric_error is not None
              or prediction.get('status') in ('error', 'failed', 'missing'))
    refusal = (clean == REFUSAL and prediction.get('status') != 'invalid_output'
               and not prediction.get('citation_errors'))
    valid, evidence = [], []
    for cite in citations:
        matches = [r for r in context if r.get('chunk_id') == cite.get('chunk_id')
                   and r.get('source_label') == cite.get('source_label')]
        block = paragraphs.get(cite.get('paragraph_id'))
        traced = False
        if cite.get('valid') and len(matches) == 1 and block:
            row, meta = matches[0], matches[0]['metadata']
            start, end = cite.get('start', -1), cite.get('end', -1)
            traced = (cite.get('paper_id') == meta['paper_id'] == block['paper_id'] == question['paper_id']
                      and cite.get('paragraph_id') == meta['paragraph_id']
                      and meta['start'] <= start < end <= meta['end']
                      and block['start'] <= start < end <= block['end']
                      and row['text'][start-meta['start']:end-meta['start']] == cite.get('text')
                      and block['text'][start-block['start']:end-block['start']] == cite.get('text'))
        valid.append(traced)
        if traced and cite['number'] in used and block['original_text'] not in evidence:
            evidence.append(block['original_text'])
    canonical = 'Unanswerable' if refusal else clean
    gold = official_gold([question], {question['paper_id']: {'title': ''}})
    scored = evaluate(get_answers_and_evidence(gold, True), {} if failed else {
        question['question_id']: {'answer': canonical, 'evidence': evidence}})
    eligible = bool(clean and not refusal and not failed)
    format_errors = {'invalid_protocol', 'unparsed_citation_definition', 'duplicate_citation_number',
                     'answer_has_no_citations', 'empty_final_answer', 'unexpected_thinking_text'}
    citation_format_ok = not (format_errors & set(prediction.get('citation_errors', [])))
    no_answer = not question['answerable']
    return {'Answer F1': scored['Answer F1'], 'Evidence F1': scored['Evidence F1'],
            'citation_eligible': int(eligible),
            'citation_compliant': int(eligible and bool(citations) and citation_format_ok),
            'citations_parsed': len(citations), 'citations_valid': sum(valid),
            'unanswerable_correct_refusal': int(no_answer and refusal and not failed),
            'unanswerable_wrong_answer': int(no_answer and not refusal and not failed),
            'unanswerable_system_error': int(no_answer and failed),
            'answerable_refusal': int(question['answerable'] and refusal and not failed),
            'predicted_answer': canonical, 'predicted_evidence': evidence,
            'metric_error': metric_error}


def aggregate(rows, stage):
    """Aggregate every expected row; caller must retain missing/failed rows."""
    if stage not in ('retrieval', 'generation'):
        raise ValueError('stage must be retrieval or generation')
    answerable = [r for r in rows if r['answerable']]
    keys = RETRIEVAL_KEYS if stage == 'retrieval' else RETRIEVAL_KEYS + (
        'Answer F1', 'Evidence F1', 'Context EvidenceRecall', 'Context AllEvidence')
    result = {'questions': len(rows), 'answerable': len(answerable),
              'system_errors': sum(bool(r.get('error')) or r.get('status') in
                                   ('error', 'failed', 'missing') or
                                   bool(r.get('metrics', {}).get('metric_error')) for r in rows),
              'mean_seconds': sum(r.get('seconds', 0) or 0 for r in rows) / len(rows) if rows else None}
    result['System error rate'] = result['system_errors'] / len(rows) if rows else None
    for key in keys:
        pool = answerable if key in RETRIEVAL_KEYS or key.startswith('Context ') else rows
        result[key] = sum(r.get('metrics', {}).get(key, 0) or 0 for r in pool) / len(pool) if pool else None
    if stage == 'generation':
        for key in ('citation_eligible', 'citation_compliant', 'citations_parsed', 'citations_valid',
                    'unanswerable_correct_refusal', 'unanswerable_wrong_answer',
                    'unanswerable_system_error', 'answerable_refusal'):
            result[key] = sum(r.get('metrics', {}).get(key, 0) for r in rows)
        for name, numerator, denominator in (
                ('Citation compliance', 'citation_compliant', 'citation_eligible'),
                ('Citation traceability', 'citations_valid', 'citations_parsed')):
            result[name] = result[numerator] / result[denominator] if result[denominator] else None
        result['unanswerable'] = len(rows) - len(answerable)
        for name, numerator, denominator in (
                ('Correct refusal rate', 'unanswerable_correct_refusal', 'unanswerable'),
                ('Wrong-answer rate', 'unanswerable_wrong_answer', 'unanswerable'),
                ('Unanswerable system error rate', 'unanswerable_system_error', 'unanswerable'),
                ('Wrong refusal rate', 'answerable_refusal', 'answerable')):
            result[name] = result[numerator] / result[denominator] if result[denominator] else None
    return result
