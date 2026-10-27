#!/usr/bin/env python3
"""Import latest derived metadata CSV into local OpenRefine; no source changes."""
import json
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request
ROOT=Path(__file__).resolve().parents[1];store=ROOT/'.quality'
report=json.loads((store/'reports/latest.json').read_text());job=report['job_id']
base='http://127.0.0.1:3334'
def get(path):
    with urllib.request.urlopen(base+path,timeout=15) as r:return json.load(r)
name='Pubster metadata review '+job
existing=get('/command/core/get-all-project-metadata')['projects']
project=next((key for key,value in existing.items() if value.get('name')==name),None)
if project is None:
    token=get('/command/core/get-csrf-token')['token']
    result=subprocess.run(['curl','--fail','--silent','--show-error','--max-time','60','-o',str(store/'reports/openrefine-import-response.html'),'-w','%{redirect_url}',
        '-F','project-file=@'+str(store/'jobs'/job/'openrefine-review.csv'),'-F','project-name='+name,
        '-F','format=text/line-based/*sv','-F','options={"separator":",","headerLines":1,"guessCellValueTypes":false}',
        base+'/command/core/create-project-from-upload?csrf_token='+urllib.parse.quote(token)],capture_output=True,text=True,check=True)
    project=urllib.parse.parse_qs(urllib.parse.urlsplit(result.stdout).query)['project'][0]
rows=get('/command/core/get-rows?project='+project+'&start=0&limit=1')
if rows['total']!=report['records']:raise RuntimeError('OPENREFINE_ROW_COUNT_MISMATCH')
proof={'job_id':job,'project_id':project,'rows':rows['total'],'url':base+'/project?project='+project,'api_verified':True,'browser_verified':False}
(store/'reports/openrefine.json').write_text(json.dumps(proof,sort_keys=True)+'\n')
print(json.dumps(proof))
