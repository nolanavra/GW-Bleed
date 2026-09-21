"""Readiness check: never replace human/physical evidence with unit-test success."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent.parent
REQUIRED=('rights','dependency_review','public_source','clean_windows_build','pdf_fidelity','six_machine_validation','security_review','enterprise_deployment','accessibility','three_site_pilot','publisher_signing','support_ready')

def check(record, root=ROOT):
    blockers=[]
    for gate in REQUIRED:
        item=record.get('gates',{}).get(gate,{})
        if item.get('status')!='approved' or not item.get('reviewer') or not item.get('date'):
            blockers.append(f'{gate}: approval missing');continue
        evidence=item.get('evidence',[])
        if not evidence: blockers.append(f'{gate}: evidence missing')
        for name in evidence:
            path=(root/name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file(): blockers.append(f'{gate}: unavailable local evidence {name}')
    return blockers

if __name__=='__main__':
    record=json.loads((ROOT/'release/readiness.json').read_text(encoding='utf-8'))
    blockers=check(record)
    print('\n'.join(blockers) if blockers else 'All recorded release gates have evidence; verify sign-offs before publication.')
    raise SystemExit(1 if blockers else 0)
