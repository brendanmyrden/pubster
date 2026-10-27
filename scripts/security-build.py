from pathlib import Path
import json
root=Path(__file__).resolve().parents[1];out=root/'apps/web/out'
records=[json.loads(line) for line in (root/'corpus/curated/chunks.jsonl').read_text().splitlines()]
secrets=json.loads((Path.home()/'.local/share/pubster/secrets/password-verifier.json').read_text())
markers=[r['chunk_id'].encode() for r in records]+[secrets[x].encode() for x in ['key_b64','salt_b64']]
count=0
for p in out.rglob('*'):
 if p.is_file() and not p.name.startswith('._'):
  data=p.read_bytes();assert not any(x in data for x in markers),p;assert b'/Users/' not in data,p;count+=1
print(json.dumps({'public_build_files_scanned':count,'corpus_and_verifier_markers':'absent'}))
