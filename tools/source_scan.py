"""Scan proposed release files for private paths, secret patterns, and old PDF imports."""
import ast
import re
from source_archive import source_files, ROOT
patterns=[re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}'),re.compile(r'AKIA[0-9A-Z]{16}'),re.compile(r'(?i)[A-Z]:[\\/]Users[\\/](?!Public[\\/])[^\s"\']+')]
errors=[]
for path in source_files():
    if path.suffix not in ('.py','.md','.json','.toml','.txt','.yml','.yaml','.ps1','.spec'): continue
    text=path.read_text(encoding='utf-8-sig')
    for number,line in enumerate(text.splitlines(),1):
        if any(pattern.search(line) for pattern in patterns): errors.append(f'{path.relative_to(ROOT)}:{number}: potential secret/private path (value withheld)')
    if path.suffix=='.py':
        tree=ast.parse(text)
        for node in ast.walk(tree):
            names=([x.name for x in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else [])
            if any(n.split('.')[0] in ('pymupdf','fitz') for n in names): errors.append(f'{path.relative_to(ROOT)}:{node.lineno}: prohibited legacy PDF import')
print('\n'.join(errors) if errors else 'Source scan passed. Automated patterns do not replace manual rights/secret review.')
raise SystemExit(bool(errors))
