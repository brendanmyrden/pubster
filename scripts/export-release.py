#!/usr/bin/env python3
"""Publish one bounded immutable export bundle to the verified PRIVATE repository."""
import gzip,hashlib,io,json,os,subprocess,tarfile,tempfile,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];STATE=Path('/Volumes/SYYR/Pubster-state')
def cmd(args,timeout=90):
 r=subprocess.run(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 if r.returncode:raise RuntimeError('RELEASE_COMMAND_FAILED')
 return r.stdout
repo=json.loads((ROOT/'config/git-remote.json').read_text())['repo']
assert json.loads(cmd(['gh','repo','view',repo,'--json','visibility']))['visibility']=='PRIVATE'
m=json.loads((ROOT/'corpus/manifests/current.json').read_text());cid=m['corpus_id'];directory=STATE/'exports'/cid;tag='corpus-'+cid[:16]
record=STATE/'state/release-status.json'
if record.exists() and json.loads(record.read_text()).get('corpus_id')==cid:print('{"release":"unchanged"}');raise SystemExit(0)
paths=[a['path'] for a in m['artifacts']]+['manifest.json','SHA256SUMS'];assert sum((directory/p).stat().st_size for p in paths)<25*1024**2
for a in m['artifacts']:assert hashlib.sha256((directory/a['path']).read_bytes()).hexdigest()==a['sha256']
archive=STATE/'staging'/('pubster-'+cid[:16]+'.tar.gz');archive.parent.mkdir(exist_ok=True)
with archive.open('wb') as f:
 with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as z:
  with tarfile.open(fileobj=z,mode='w') as tar:
   for name in sorted(paths):
    data=(directory/name).read_bytes();info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0;tar.addfile(info,io.BytesIO(data))
budgetfile=STATE/'state/release-budget.json';today=datetime.date.today().isoformat();budget=json.loads(budgetfile.read_text()) if budgetfile.exists() else {}
used=budget.get('bytes',0) if budget.get('date')==today else 0
reserved=archive.stat().st_size*2+4096
if used+reserved>250*1024**2:raise RuntimeError('RELEASE_TRANSFER_BUDGET')
budgetfile.write_text(json.dumps({'date':today,'bytes':used+reserved})+'\n')
digest=hashlib.sha256(archive.read_bytes()).hexdigest();checksum=archive.with_suffix('.tar.gz.sha256');checksum.write_text(digest+'  '+archive.name+'\n')
# Resolve before create; never overwrite a content-addressed release.
probe=subprocess.run(['gh','release','view',tag,'--repo',repo,'--json','tagName'],cwd=ROOT,capture_output=True)
if probe.returncode:
 if b'release not found' not in probe.stderr.lower():raise RuntimeError('RELEASE_LOOKUP_FAILED')
 notes=STATE/'staging/release-notes.md';notes.write_text('Validated private corpus snapshot.\n\nCorpus: '+cid+'\n\n'+str(m['accepted_record_counts_by_kind']['reference'])+' source excerpts; original licenses and source provenance included. No credentials, live database, or model weights.\n')
 cmd(['gh','release','create',tag,'--repo',repo,'--target','main','--title','Pubster corpus '+cid[:12],'--notes-file',str(notes),str(archive),str(checksum)])
with tempfile.TemporaryDirectory(dir=STATE/'tmp') as temp:
 cmd(['gh','release','download',tag,'--repo',repo,'--pattern',archive.name,'--dir',temp])
 assert hashlib.sha256((Path(temp)/archive.name).read_bytes()).hexdigest()==digest
result={'corpus_id':cid,'tag':tag,'sha256':digest,'bytes':archive.stat().st_size,'verified_download':True,'url':'https://github.com/'+repo+'/releases/tag/'+tag}
record.write_text(json.dumps(result,sort_keys=True)+'\n');print(json.dumps(result,sort_keys=True))
