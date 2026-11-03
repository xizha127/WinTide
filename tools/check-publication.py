#!/usr/bin/env python3
"""Inspect exactly the Git index; ignore rules alone cannot prevent forced secret staging."""
import pathlib,re,subprocess,sys
root=pathlib.Path(__file__).resolve().parents[1]
files=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
allowed={'README.md','LICENSE','THIRD_PARTY.md','components.lock.json','setup.sh','.gitignore','.gitattributes'}
folders={'docs','examples','patches','guest','tools','tests','licenses','.github'}
bad=[]
for f in filter(None,files):
 p=pathlib.PurePosixPath(f)
 if f not in allowed and p.parts[0] not in folders:bad.append((f,'unapproved publication path'));continue
 if any(re.search(r'(^local|secret|credential|password|\.env|backup)',part,re.I) for part in p.parts):bad.append((f,'local/sensitive filename'));continue
 if p.suffix.lower() in {'.exe','.dll','.sys','.cer','.cat','.iso','.img','.qcow2','.fd','.bcd','.reg','.log','.jsonl','.png','.ppm','.zip','.pem','.key','.pfx','.conf'}:bad.append((f,'generated or sensitive file type'));continue
 content=subprocess.check_output(['git','show',':'+f],cwd=root)
 if b'\0' in content:bad.append((f,'binary data'));continue
 text=content.decode('utf-8')
 patterns=[(r'/' + r'home/(?!USER(?:/|\b)|user(?:/|\b))[^/\s\"\']+/','personal absolute home path'),(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY','private key'),(r'\bgh[pousr]_[A-Za-z0-9]{20,}\b','GitHub credential'),(r'\bgithub_pat_[A-Za-z0-9_]{20,}\b','GitHub credential'),(r'(?im)^\s*RDP_PASS\s*=\s*[\"\'][^\"\'\n]+[\"\']','embedded RDP password')]
 for pattern,reason in patterns:
  if re.search(pattern,text):bad.append((f,reason))
for f,reason in bad:print(f'{f}: {reason}',file=sys.stderr)
if bad:sys.exit(1)
print('Publication check passed for',len(list(filter(None,files))),'tracked text files.')
