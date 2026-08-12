"""Summarise the last demo's trace log by agent and surface (like the sibling
packages' _check.py). Run after demo_agenttrace.py."""
import json
from collections import Counter

lines = list(open('trace_logs/traces.jsonl', encoding='utf-8'))
c = Counter(json.loads(l)['agent_name'] for l in lines)
out = ['total events: %d' % len(lines), 'agent_name counts: %s' % dict(c), '', 'per-event:']
for l in lines:
    e = json.loads(l)
    body = e.get('body', {})
    label = body.get('method') or body.get('operation') or body.get('extraction_method') or ''
    step = body.get('step', '')
    out.append(f"  {e['agent_name']:24s} {e['surface']:12s} {label:24s} {step}")
open('_check_out.txt', 'w', encoding='utf-8').write('\n'.join(out))
print('\n'.join(out))
