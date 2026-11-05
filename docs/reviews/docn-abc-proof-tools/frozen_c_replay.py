"""Offline paired SEC extraction/gate replay; never manufactures publications.

Archives the approved base into a temporary directory (not a worktree), freezes
current package sources, declares issuer/date pairs before running either code,
and invokes the same Python environment twice per cell with network blocked.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

BASE = 'f1e846d67bd9d02446956df882650f4eedac3a1b'
CLAIMS = '```financial_claims\n[]\n```'
DATES = {'development_dates':['2026-06-01'], 'holdout_dates':['2026-08-03','2026-10-01']}
INPUTS = {'DOCN':('0001582961','live-05/cache/sec_edgar/CIK0001582961.json'),
          'NVDA':('0001045810','a-second-issuer-nvda/cache/sec_edgar/CIK0001045810.json')}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def write(path,value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')


def manifest(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root/'tradingagents').rglob('*.py')) if '__pycache__' not in p.parts}


def versions(code, files):
    prompts = {k:v for k,v in files.items() if any('/'+part+'/' in k for part in ('analysts','researchers','managers'))}
    schemas = {k:v for k,v in files.items() if Path(k).name in {'financial_evidence.py','schemas.py','evidence_validation.py','sec_edgar.py'}}
    return {'code':code+'+source-sha256:'+digest(files),'prompt':digest(prompts),'schema':digest(schemas)}


def worker(spec_path):
    spec = json.loads(Path(spec_path).read_text())
    attempts, local_probes = [], []
    def forbid_network(event,args):
        if event == 'socket.bind':
            # urllib3 checks IPv6 support by attempting to bind ::1:0 during
            # import. Block that local probe too, but do not call it egress.
            local_probes.append('blocked local socket bind capability probe')
            raise RuntimeError('Socket bind disabled for frozen engineering replay')
        if event in {'socket.connect','socket.getaddrinfo'}:
            attempts.append(event)
            raise RuntimeError('Network disabled for frozen engineering replay')
    sys.addaudithook(forbid_network)
    from tradingagents.agents.evidence_validation import assess_financial_package
    from tradingagents.dataflows.vendors import sec_edgar
    actual_module = str(Path(sec_edgar.__file__).resolve())
    if not actual_module.startswith(str(Path(spec['code_root']).resolve())+os.sep):
        raise RuntimeError('Replay imported the wrong checkout')
    data = json.loads(Path(spec['input_path']).read_text())
    sec_edgar.cik_for = lambda ticker: spec['cik']
    sec_edgar._cached_json = lambda *args: data
    sec_edgar.get_config = lambda: {'data_cache_dir':spec['cache_root']}
    result = {'ticker':spec['ticker'],'as_of':spec['as_of'],'invariant_violations':[],
              'network_attempts':attempts,'blocked_local_probes':local_probes,'model_calls':0}
    try:
        package = sec_edgar.get_financial_evidence(spec['ticker'],spec['as_of'])
        result['status'] = 'available'
        result['accepted_fact_count'] = sum(f.value is not None for f in package.facts)
        for source in package.sources:
            if source.cik != spec['cik'] or str(source.filed_date) > spec['as_of']:
                result['invariant_violations'].append('Source issuer or filing cutoff violated')
        for fact in package.facts:
            if fact.cik != spec['cik'] or str(fact.as_of) != spec['as_of'] or str(fact.period_end) > spec['as_of']:
                result['invariant_violations'].append('Fact issuer, period or analysis cutoff violated')
        result['financial_evidence'] = package.model_dump(mode='json')
        result['gate'] = assess_financial_package(
            {'company_of_interest':spec['ticker'],'trade_date':spec['as_of'],'fundamentals_report':CLAIMS},
            package, disclosure_error='Frozen companyfacts-only replay: filing documents not included.')
    except Exception as exc:
        result['status'] = 'unavailable'
        result['accepted_fact_count'] = 0
        result['error'] = {'type':type(exc).__name__,'message':str(exc)}
    if attempts:
        result['invariant_violations'].append('Network access attempted')
    write(Path(spec['output']),result)


def main():
    root = Path(__file__).resolve().parents[3]
    output = root/'results/docn-abc/c-frozen-replay'
    output.mkdir(parents=True,exist_ok=False)
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='docn-c-frozen-') as temporary:
        temp = Path(temporary)
        baseline, current = temp/'baseline', temp/'current'
        baseline.mkdir()
        current.mkdir()
        archive = subprocess.check_output(['git','archive',BASE],cwd=root)
        with tarfile.open(fileobj=io.BytesIO(archive),mode='r:') as tar:
            tar.extractall(baseline,filter='data')
        before = manifest(root)
        for relative in before:
            target = current/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(root/relative,target)
        if before != manifest(root) or before != manifest(current):
            raise RuntimeError('Current source changed while snapshotting; no replay performed')
        manifests = {'baseline':manifest(baseline),'current':manifest(current)}
        code_versions = {name:versions(BASE if name=='baseline' else head,files) for name,files in manifests.items()}
        for name, files in manifests.items():
            write(output/f'{name}-source-manifest.json',files)
        cache = output/'inputs'/'sec_edgar'
        cache.mkdir(parents=True)
        sources, pairs = {}, []
        for ticker,(cik,relative) in INPUTS.items():
            source = root/'results/docn-abc'/relative
            target = cache/source.name
            shutil.copy2(source,target)
            sources[ticker] = {'cik':cik,'source':str(source.relative_to(root)),
                              'retained_file':str(target.relative_to(output)),
                              'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                              'snapshot_observed_mtime_utc':datetime.fromtimestamp(source.stat().st_mtime,UTC).isoformat()}
            for cutoff in DATES['development_dates']+DATES['holdout_dates']:
                frozen = {'ticker':ticker,'as_of':cutoff,'companyfacts_sha256':sources[ticker]['sha256'],
                          'fundamentals_report':CLAIMS,'filing_documents':None}
                pairs.append({'ticker':ticker,'as_of':cutoff,'frozen_input_sha256':digest(frozen)})
        protocol = {'schema_version':1,'evaluation_mode':'historical',**DATES,'pairs':pairs,
                    'baseline_versions':code_versions['baseline'],'current_versions':code_versions['current'],
                    'declared_at':datetime.now(UTC).isoformat(),'script_sha256':script_hash,
                    'acceptance':'All pairs attempted twice; identical frozen inputs and repeat hashes; zero cutoff violations and network/model calls. Preserve baseline failures as coverage evidence.',
                    'partition_limit':'Partitions declared before this replay, not claimed blind during prior implementation or predictive model training.',
                    'version_basis':'Code includes exact package source manifest; prompt/schema are source fingerprints. No prompt was executed.'}
        write(output/'protocol.json',protocol)  # declaration precedes first execution
        write(output/'sources.json',sources)
        reports = {}
        for name, code_root in [('baseline',baseline),('current',current)]:
            cells = []
            for pair in pairs:
                runs = []
                for repetition in (1,2):
                    stem = f"{name}-{pair['ticker']}-{pair['as_of']}-r{repetition}"
                    target = output/(stem+'.json')
                    spec = {**pair,'versions':code_versions[name],'cik':sources[pair['ticker']]['cik'],
                            'input_path':str(output/sources[pair['ticker']]['retained_file']),
                            'cache_root':str(cache.parent),'code_root':str(code_root),'output':str(target)}
                    spec_path = temp/(stem+'-spec.json')
                    write(spec_path,spec)
                    env = {**os.environ,'PYTHONPATH':str(code_root),'PYTHONDONTWRITEBYTECODE':'1'}
                    command = [sys.executable,str(Path(__file__).resolve()),'--worker',str(spec_path)]
                    done = subprocess.run(command,cwd=code_root,env=env,text=True,capture_output=True,timeout=120)
                    if done.returncode:
                        raise RuntimeError(f'{stem} failed: {done.stderr[-2000:]}')
                    result = json.loads(target.read_text())
                    runs.append(result)
                cells.append({**pair,'versions':code_versions[name],'status':runs[0]['status'],
                              'accepted_fact_count':runs[0]['accepted_fact_count'],
                              'output_sha256':digest(runs[0]),'repeat_output_sha256':digest(runs[1]),
                              'invariant_violations':runs[0]['invariant_violations']+runs[1]['invariant_violations'],
                              'gate_status':(runs[0].get('gate',{}).get('evidence_quality') or {}).get('status'),
                              'error':runs[0].get('error')})
            reports[name] = {'engineering_cells':cells}
            write(output/f'{name}-engineering.json',reports[name])
        # This API evaluates engineering cells separately from real publications.
        sys.path.insert(0,str(root))
        from tradingagents.backtest import compare_frozen_publication_evaluations
        comparison = compare_frozen_publication_evaluations(reports['baseline'],reports['current'],protocol)
        write(output/'comparison.json',comparison)
        receipt = {'protocol_sha256':hashlib.sha256((output/'protocol.json').read_bytes()).hexdigest(),
                   'comparison_status':comparison['status'],'paired_cells':len(pairs),'runs':len(pairs)*4,
                   'network_calls':0,'model_calls':0,'paid_cost_usd':'0',
                   'all_repeats_identical':all(c['output_sha256']==c['repeat_output_sha256'] for r in reports.values() for c in r['engineering_cells']),
                   'all_invariants_pass':all(not c['invariant_violations'] for r in reports.values() for c in r['engineering_cells']),
                   'limitations':['Retained snapshots were retrieved after some cutoffs; source filing/period cutoffs are enforced, but this is not an archived contemporaneous data feed.',
                                  'No filing-document extraction, model research, publication, rating, historical return or profitability evidence is invented. Companyfacts-only gate coverage limits remain visible.',
                                  'This is deterministic engineering replay, not a clean historical investment holdout or performance proof.']}
        write(output/'receipt.json',receipt)
        print(json.dumps(receipt,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker')
    arguments = parser.parse_args()
    worker(arguments.worker) if arguments.worker else main()
