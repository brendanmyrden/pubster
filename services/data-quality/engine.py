"""Read-only source analysis; derived review artifacts never rewrite source records."""
import fcntl
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / '.quality'
VERSION = '1'

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))

def analyze(records):
    import duckdb
    import polars as pl
    import pandera.polars as pa
    import great_expectations as gx
    import dedupe
    import numpy as np
    from datasketch import MinHash, MinHashLSH
    from cleanlab.outlier import OutOfDistribution
    from sklearn.preprocessing import StandardScaler
    if not records or len(records) > 5000:
        raise ValueError('QUALITY_BATCH_LIMIT: require 1..5000 records')
    versions = {x: md.version(x) for x in ['duckdb','polars','pandera','datasketch','dedupe','cleanlab','great_expectations']}
    flat = []
    for r in records:
        body = r['body_markdown']
        flat.append(dict(chunk_id=r['chunk_id'], source_id=r['source_id'], title=r['title'],
            repository=r['origin']['repository'], revision=r['origin']['commit'],
            source_url=r['origin']['canonical_url'], body_sha256=hashlib.sha256(body.encode()).hexdigest(),
            characters=len(body), line_start=r['origin']['line_start'], line_end=r['origin']['line_end'],
            rights=r['rights']['status']))
    # Normalize metadata only. Never mutate bodies, title originals, or source evidence.
    frame = pl.DataFrame(flat).with_columns(
        pl.col('repository').str.to_lowercase().str.strip_chars().alias('repository_key'))
    schema = pa.DataFrameSchema({
        'chunk_id': pa.Column(str, unique=True, checks=pa.Check.str_startswith('sha256:')),
        'source_id': pa.Column(str, checks=pa.Check.str_length(min_value=1)),
        'characters': pa.Column(int, checks=pa.Check.in_range(40,8000)),
        'line_start': pa.Column(int, checks=pa.Check.ge(1)),
        'rights': pa.Column(str, checks=pa.Check.eq('redistribute_approved')),
        'source_url': pa.Column(str, checks=pa.Check.str_startswith('https://github.com/')),
    })
    schema.validate(frame, lazy=True)
    if any(r['origin']['line_end'] < r['origin']['line_start'] for r in records):
        raise ValueError('INVALID_LINE_SPAN')
    context = gx.get_context(mode='ephemeral')
    ds = context.data_sources.add_pandas('pubster')
    asset = ds.add_dataframe_asset('chunks')
    batch = asset.add_batch_definition_whole_dataframe('all').get_batch(batch_parameters={'dataframe':frame.to_pandas()})
    expectations = [gx.expectations.ExpectColumnValuesToBeUnique(column='chunk_id'),
        gx.expectations.ExpectColumnValuesToNotBeNull(column='source_url'),
        gx.expectations.ExpectColumnValuesToBeInSet(column='rights',value_set=['redistribute_approved'])]
    gx_results = [bool(batch.validate(e).success) for e in expectations]
    if not all(gx_results):
        raise ValueError('GREAT_EXPECTATIONS_FAILED')
    con = duckdb.connect(':memory:',config={'threads':1,'memory_limit':'128MB','enable_external_access':False})
    con.register('chunks',frame.to_arrow())
    groups = con.execute('SELECT body_sha256, list(chunk_id ORDER BY chunk_id) FROM chunks GROUP BY body_sha256 HAVING count(*) > 1 ORDER BY body_sha256').fetchall()
    con.close()
    lsh = MinHashLSH(threshold=.8,num_perm=128)
    signatures = {}; token_sets = {}; candidates = []
    byid = {r['chunk_id']:r for r in records}
    matcher = dedupe.Dedupe([dedupe.variables.String('title'),dedupe.variables.Exact('repository')],num_cores=0,in_memory=True)
    for r in sorted(records,key=lambda x:x['chunk_id']):
        tokens = re.findall(r'\w+|[^\w\s]',r['body_markdown'])
        shingles = {' '.join(tokens[i:i+5]) for i in range(max(0,len(tokens)-4))}
        if not shingles: continue
        sig = MinHash(num_perm=128,seed=1)
        sig.update_batch([x.encode() for x in sorted(shingles)])
        for other in sorted(lsh.query(sig)):
            if len(candidates)>=20000: raise ValueError('QUALITY_PAIR_LIMIT')
            prior=token_sets[other]; similarity=len(shingles & prior)/len(shingles | prior)
            if similarity < .8: continue
            a=byid[other]
            pair=({'title':a['title'],'repository':a['origin']['repository'].lower()},
                  {'title':r['title'],'repository':r['origin']['repository'].lower()})
            distances=matcher.data_model.distances([pair])[0].tolist()
            candidates.append({'left':other,'right':r['chunk_id'],'shingle_jaccard':round(similarity,6),
                'dedupe_field_distances':distances,'decision':'review_preserve_both'})
        lsh.insert(r['chunk_id'],sig);signatures[r['chunk_id']]=sig;token_sets[r['chunk_id']]=shingles
    # Structural anomalies are not truth/label judgements. No classifier or paid API.
    anomaly=[]
    if len(records)>=3:
        features=np.array([[len(r['body_markdown']),r['body_markdown'].count('\n'),r['body_markdown'].count('```'),len(r['title'])] for r in records],dtype=float)
        scores=OutOfDistribution(params={'k':min(10,len(records)-1)}).fit_score(features=StandardScaler().fit_transform(features))
        anomaly=[{'chunk_id':r['chunk_id'],'structural_ood_score':round(float(s),8),'decision':'review_only'} for r,s in zip(records,scores) if s < .2]
    report={'engine_version':VERSION,'versions':versions,'records':len(records),'schema_valid':len(records),
        'great_expectations':gx_results,'exact_duplicate_groups':[{'sha256':h,'chunk_ids':ids} for h,ids in groups],
        'near_duplicates':candidates,'structural_anomalies':anomaly,
        'dedupe_mode':'untrained_field_distances_for_review; no learned merge decisions',
        'cleanlab_mode':'structural_outliers; label audit requires reviewed labels and out-of-sample predictions',
        'index':{'datasketch_version':versions['datasketch'],'seed':1,'num_perm':128,'shingle_size':5,'rebuild':'every_new_job'},
        'source_mutations':0,'state':'accepted'}
    return report,frame

def run(input_path):
    input_path=Path(input_path).resolve()
    if not input_path.is_relative_to(ROOT):raise ValueError('INPUT_MUST_BE_IN_PROJECT')
    if input_path.stat().st_size>40*1024*1024:raise ValueError('QUALITY_INPUT_SIZE_LIMIT')
    raw=input_path.read_bytes()
    if len(raw)>40*1024*1024: raise ValueError('QUALITY_INPUT_SIZE_LIMIT')
    records=[json.loads(line) for line in raw.splitlines() if line]
    version_fingerprint={x:md.version(x) for x in ['duckdb','polars','pandera','datasketch','dedupe','cleanlab','great_expectations']}
    job=hashlib.sha256(raw+Path(__file__).read_bytes()+canonical(version_fingerprint).encode()).hexdigest()
    folder=STORE/'jobs'/job;folder.mkdir(parents=True,exist_ok=True)
    result=folder/'report.json'
    if result.exists():
        saved=json.loads(result.read_text())
        if saved.get('state')=='accepted':
            (STORE/'reports/latest.json').write_text(canonical(saved)+'\n')
            return saved
    try:
        report,frame=analyze(records)
        frame.write_parquet(folder/'normalized-metadata.parquet')
        frame.write_csv(folder/'openrefine-review.csv')
        report['job_id']=job
        result.write_text(canonical(report)+'\n')
        (STORE/'reports/latest.json').write_text(canonical(report)+'\n')
        return report
    except Exception as e:
        quarantine=STORE/'quarantine'/job;quarantine.mkdir(parents=True,exist_ok=True)
        (quarantine/'original.jsonl').write_bytes(raw)
        (quarantine/'failure.json').write_text(canonical({'state':'quarantined','error':type(e).__name__,'detail':str(e)[:2000]})+'\n')
        raise

if __name__=='__main__':
    try:
        lock=(STORE/'worker.lock').open('a')
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        report=run(sys.argv[1]);print(canonical({'state':report['state'],'records':report['records'],'job_id':report['job_id']}))
    except Exception as e:
        print(canonical({'state':'failed','error':type(e).__name__,'detail':str(e)[:500]}));sys.exit(1)
