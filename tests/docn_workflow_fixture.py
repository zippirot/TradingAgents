"""Hash-checked public source projections for the workflow gap proof."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parent / 'fixtures/docn_2026_11_07'


def source_bytes(name):
    expected = json.loads((ROOT / 'manifest.json').read_text())['source_files'][name]
    raw = (ROOT / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected['sha256'], name
    decoded = gzip.decompress(raw)
    assert hashlib.sha256(decoded).hexdigest() == expected['decoded_sha256'], name
    return decoded


def source_json(name):
    return json.loads(source_bytes(name))


def source_state():
    return {'company_of_interest': 'DOCN', 'trade_date': '2026-11-07', 'asset_type': 'stock',
            'financial_evidence': source_json('cfae95e9-financial.json.gz'),
            'filing_evidence': source_json('cfae95e9-bounded.json.gz'),
            'evidence_acquisition': {'status': 'ready', 'ticker': 'DOCN', 'as_of': '2026-11-07',
                                     'source_checks': [{'code': 'source_integrity', 'status': 'pass'}]}}
