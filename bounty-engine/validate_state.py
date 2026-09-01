import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
state = json.loads((ROOT / 'state.json').read_text(encoding='utf-8'))

required = {'engine','cycle','state','active_bounty','realized_value_usd','submitted','accepted','paid','human_gates'}
missing = required - state.keys()
assert not missing, f'missing state keys: {sorted(missing)}'
assert isinstance(state['cycle'], int) and state['cycle'] >= 0
assert isinstance(state['realized_value_usd'], (int,float)) and state['realized_value_usd'] >= 0
for k in ('submitted','accepted','paid','human_gates'):
    assert isinstance(state[k], int) and state[k] >= 0, f'{k} must be non-negative integer'
assert state['paid'] <= state['accepted'] <= state['submitted'], 'paid <= accepted <= submitted invariant violated'
if state['state'] == 'IDLE':
    assert state['active_bounty'] is None, 'IDLE cannot have active_bounty'

ledger = ROOT / 'ledger.ndjson'
for i, raw in enumerate(ledger.read_text(encoding='utf-8').splitlines(), 1):
    if not raw.strip():
        continue
    row = json.loads(raw)
    rv = row.get('realized_value_usd', 0)
    assert isinstance(rv, (int,float)) and rv >= 0, f'line {i}: invalid realized_value_usd'
    if row.get('paid') is True:
        assert row.get('accepted') is True, f'line {i}: paid without accepted'
        assert row.get('submitted') is True, f'line {i}: paid without submitted'
    if row.get('accepted') is True:
        assert row.get('submitted') is True, f'line {i}: accepted without submitted'

print('BOUNTY_ENGINE state/ledger validation: OK')
