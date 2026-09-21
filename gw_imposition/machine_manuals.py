"""Bundled source documents and reviewed context, independent of editable profiles.

Page references use PDF page numbers. A manual association is not physical approval.
Unconfirmed aliases never supply machine limits or instructions.
"""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

MANUAL_ROOT = Path(__file__).parent / 'resources' / 'manuals'


@lru_cache(maxsize=1)
def catalog():
    return json.loads((MANUAL_ROOT / 'catalog.json').read_text(encoding='utf-8'))


def documents_for(machine_id):
    return tuple(d for d in catalog()['documents'] if machine_id in d['machine_ids'])


def manual_path(document_id, *, verify=False):
    document = next(d for d in catalog()['documents'] if d['id'] == document_id)
    path = MANUAL_ROOT / document['filename']
    if path.parent.resolve() != MANUAL_ROOT.resolve():
        raise ValueError('Invalid bundled manual path.')
    if not path.is_file():
        raise ValueError('The bundled manual is missing. Repair the installation.')
    if verify and hashlib.sha256(path.read_bytes()).hexdigest() != document['sha256']:
        raise ValueError('The bundled manual differs from the catalog. Repair the installation.')
    return path


def machine_context(machine_id, topic='general'):
    documents = documents_for(machine_id)
    if not documents:
        return ('Manual-to-model mapping is pending confirmation. Current settings are provisional; '
                'see Machine specs for the bundled manual library. No manual limits have been inferred from a filename.')
    lines = []
    for doc in documents:
        for note in doc.get('notes', []):
            if topic == 'general' or topic in note['topics']:
                pages = ', '.join(str(p) for p in note['pages'])
                lines.append(f"{note['text']} Source: {doc['filename']}, PDF page(s) {pages}.")
    if not lines:
        lines.append('Bundled reference: ' + '; '.join(d['filename'] for d in documents) +
                     '. This specific control or setting has not yet been verified against the manual.')
    return '\n'.join(lines)


def contextual_tooltip(machine_id, text, topic='general'):
    return text + '\n\n' + machine_context(machine_id, topic)
