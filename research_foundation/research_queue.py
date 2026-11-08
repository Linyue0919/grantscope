"""Deterministic bounded research allocation; no candidate deletion or semantic veto."""
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class QueueConfig:
    budget: int = 10
    user: int = 2
    uncertainty: int = 2
    diversity: int = 2
    recall_audit: int = 1
    priority: int = 3
    low_rank_fraction: float = .25
    seed: int = 20261107


def identity(candidate):
    value = candidate.get('opportunity_id', candidate.get('id'))
    if isinstance(value, bool) or value is None or not str(value).strip():
        raise ValueError('Stable opportunity identity is required')
    value = str(value).strip()
    if value.isdecimal():
        value = str(int(value))
    namespace = str(candidate.get('source') or 'grants.gov').strip().lower()
    if not namespace:
        raise ValueError('Stable source namespace required')
    return namespace, value


def build_queue(candidates, config=QueueConfig()):
    quotas = {k: getattr(config, k) for k in ('user', 'uncertainty', 'diversity', 'recall_audit', 'priority')}
    if (any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in [config.budget, *quotas.values()])
            or not 0 < config.low_rank_fraction <= 1):
        raise ValueError('Nonnegative integer budget/quotas and a positive fraction <=1 are required')
    pool = {}
    for raw in candidates:
        key = identity(raw)
        score = raw.get('priority_score')
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float))
                                  or not math.isfinite(score) or not 0 <= score <= 100):
            raise ValueError('Priority score must be null or finite 0..100')
        row = pool.setdefault(key, {'identity': key, 'records': [], 'priority_score': None,
                                    'uncertain': False, 'user_selected': False, 'groups': set(), 'gate_states': set()})
        row['records'].append(deepcopy(raw))
        if score is not None:
            row['priority_score'] = max(score, row['priority_score'] if row['priority_score'] is not None else score)
        row['uncertain'] |= bool(raw.get('uncertain', score is None))
        row['user_selected'] |= bool(raw.get('user_selected'))
        row['groups'].add((str(raw.get('agency') or 'unknown'), str(raw.get('program_type') or 'unknown')))
        state = raw.get('gate_state') or 'INSUFFICIENT_EVIDENCE'
        row['gate_states'].add(str(getattr(state, 'value', state)))
    ordered = sorted(pool)
    priority = sorted(ordered, key=lambda k: (-(pool[k]['priority_score'] if pool[k]['priority_score'] is not None else -1), k))
    scored = sorted((k for k in ordered if pool[k]['priority_score'] is not None),
                    key=lambda k: (pool[k]['priority_score'], k))
    low = scored[:max(1, math.ceil(len(scored) * config.low_rank_fraction))] if len(scored) > 1 else []
    random.Random(config.seed).shuffle(low)
    for row in pool.values():
        row['uncertain'] |= len(row['groups']) > 1 or len(row['gate_states']) > 1 or bool(row['gate_states'] & {'CONDITIONAL', 'INSUFFICIENT_EVIDENCE'})
    lanes = {'user': [k for k in ordered if pool[k]['user_selected']],
             'uncertainty': [k for k in ordered if pool[k]['uncertain']],
             'diversity': ordered[:], 'recall_audit': low, 'priority': priority}
    selected, reasons, used = [], {}, Counter()
    groups = Counter()
    # Explicit user overrides reserve their allocated slots before automatic lanes.
    for key in lanes['user'][:min(quotas['user'], config.budget)]:
        selected.append(key); reasons[key] = 'user'; used['user'] += 1
        groups.update(pool[key]['groups'])
    # Round-robin protects multiple entry paths. Small budgets cannot guarantee
    # all five paths; expose any unmet quotas rather than pretend full coverage.
    while len(selected) < min(config.budget, len(pool)):
        progress = False
        for lane in quotas:
            if used[lane] >= quotas[lane] or len(selected) >= config.budget:
                continue
            available = [k for k in lanes[lane] if k not in reasons]
            if not available:
                continue
            if lane == 'diversity':
                key = min(available, key=lambda k: (min(groups[g] for g in pool[k]['groups']), k))
            else:
                key = available[0]
            selected.append(key); reasons[key] = lane; used[lane] += 1; progress = True
            groups.update(pool[key]['groups'])
        if not progress:
            break  # Explicit quotas may intentionally leave budget unused.
    rows = []
    for key in ordered:
        row = pool[key]
        row['groups'] = sorted(row['groups']); row['gate_states'] = sorted(row['gate_states'])
        row.update(selected=key in reasons, selection_reason=reasons.get(key),
                   eligible_paths=[lane for lane, ids in lanes.items() if key in ids],
                   not_selected_reason=None if key in reasons else 'Budget/lane quota exhausted; retained for later research',
                   deep_research_complete=False)
        rows.append(row)
    return {'pool': rows, 'selected': [next(r for r in rows if r['identity'] == k) for k in selected],
            'not_selected': [r for r in rows if not r['selected']],
            'budget': config.budget, 'selected_count': len(selected),
            'unfilled_lane_slots': {k: quotas[k]-used[k] for k in quotas}, 'seed': config.seed}
