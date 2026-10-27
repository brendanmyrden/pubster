"""Autoresearch-style proposals via OpenClaw's tool-free, existing-auth CLI.
No upstream training code is run and no model output is executed as code.
"""
import datetime
import json
import math
import subprocess
import time
from pathlib import Path
from zoneinfo import ZoneInfo
from . import core as c

MODEL='openai/gpt-6-astra'
STATE=c.ROOT/'.quality/autoresearch'

def cli_json(args, timeout=120):
    result=subprocess.run(['openclaw',*args],cwd=c.ROOT,text=True,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if result.returncode:raise RuntimeError('OPENCLAW_REQUEST_FAILED')
    if len(result.stdout)>2*1024*1024:raise RuntimeError('OPENCLAW_RESPONSE_TOO_LARGE')
    try:return json.loads(result.stdout)
    except ValueError:raise RuntimeError('OPENCLAW_INVALID_ENVELOPE') from None

def host_guard():
    guard=c.readjson(STATE/'host-guard.json')
    if not guard or c.digest(Path(guard['path']).read_bytes())!=guard['sha256']:
        raise RuntimeError('OPENCLAW_CONFIG_CHANGED_REVIEW_REQUIRED')

def require_oauth(status):
    provider=next((x for x in status.get('auth',{}).get('providers',[]) if x.get('provider')=='openai'),{})
    profiles=provider.get('profiles',{})
    if (provider.get('effective',{}).get('kind')!='profiles' or profiles.get('oauth',0)<1
        or profiles.get('apiKey',0)!=0 or profiles.get('token',0)!=0):
        raise RuntimeError('EXISTING_OPENAI_OAUTH_REQUIRED')

def parse_proposal(envelope, baseline, seen):
    if envelope.get('ok') is not True or envelope.get('provider')!='openai' or envelope.get('model')!=MODEL.split('/',1)[1]:
        raise RuntimeError('MODEL_ATTRIBUTION_MISMATCH')
    text=''.join(x.get('text') or '' for x in envelope.get('outputs',[]))
    if len(text)>3000:raise RuntimeError('PROPOSAL_TOO_LARGE')
    try:proposal=json.loads(text)
    except ValueError:raise RuntimeError('PROPOSAL_JSON_REQUIRED') from None
    if not isinstance(proposal,dict) or set(proposal)!={'title_weight','hypothesis'}:
        raise RuntimeError('PROPOSAL_SCHEMA_INVALID')
    weight=proposal['title_weight'];reason=proposal['hypothesis']
    if type(weight) not in (int,float) or not math.isfinite(weight) or not .25<=weight<=16 or weight*4!=int(weight*4):
        raise RuntimeError('PROPOSAL_WEIGHT_INVALID')
    if weight==baseline or weight in seen:raise RuntimeError('PROPOSAL_ALREADY_TESTED')
    if not isinstance(reason,str) or not 1<=len(reason)<=500:raise RuntimeError('PROPOSAL_HYPOTHESIS_INVALID')
    return proposal

def reserve_call():
    today=datetime.datetime.now(ZoneInfo('America/Toronto')).date().isoformat()
    ledger=c.readjson(STATE/'calls.json',{})
    if ledger.get('date')==today and ledger.get('calls',0)>=1:return False
    # Reserve before contacting OpenClaw: failures, timeouts and rate limits consume the slot.
    c.writejson(STATE/'calls.json',{'date':today,'calls':1})
    return True

def frozen_evaluator():
    manifest=c.readjson(c.STATE/'evaluator/manifest.json',{})
    if not manifest:raise RuntimeError('EVALUATOR_NOT_FROZEN')
    for name,expected in manifest.items():
        if c.digest((c.STATE/'evaluator'/name).read_bytes())!=expected:raise RuntimeError('EVALUATOR_CHANGED')
    return c.digest(c.canonical(manifest))

def run(dry=False):
    from .operations import evaluate
    if not c.readjson(c.ROOT/'config/autoresearch.json',{}).get('enabled'):
        return {'state':'AUTORESEARCH_DISABLED','model_calls':0}
    with c.lock('autoresearch'):
        if (c.STATE/'state/paused').exists():return {'state':'SKIPPED_PAUSED','model_calls':0}
        if (STATE/'paused').exists():return {'state':'AUTORESEARCH_PAUSED','model_calls':0}
        host_guard();evaluator=frozen_evaluator()
        cid=c.status()['corpus_id'];baseline=c.readjson(c.STATE/'state/retrieval.json',{'title_weight':2})['title_weight']
        history=c.rows(c.ROOT/'research/results.jsonl') if (c.ROOT/'research/results.jsonl').exists() else []
        corpus_history=[x for x in history if x.get('corpus_id')==cid]
        seen={x['candidate_weight'] for x in corpus_history if 'candidate_weight' in x}
        if all(w/4 in seen or w/4==baseline for w in range(1,65)):
            return {'state':'NO_ELIGIBLE_HYPOTHESIS','model_calls':0}
        if dry:return {'state':'DRY_RUN','model':MODEL,'max_proposals_daily':1,'scope':'title_weight only','model_calls':0}
        if not reserve_call():return {'state':'DAILY_LIMIT','model_calls':0}
        started=time.monotonic();result={'mode':'openclaw-autoresearch','corpus_id':cid,'baseline_weight':baseline,'model':MODEL,'model_calls':0,'state':'FAILED'}
        try:
            require_oauth(cli_json(['infer','model','auth','status','--agent','main','--json']))
            host_guard()
            base=evaluate(baseline);dev=evaluate(baseline,'dev')
            if base['queries']<20:raise RuntimeError('EVALUATION_TOO_SMALL')
            # Aggregates only: no corpus body, source URL, credentials, test cases or expected answers.
            summary={'baseline_weight':baseline,'baseline_mrr':base['mrr'],'dev_mrr':dev['mrr'],
                'previous_trials':[{'weight':x.get('candidate_weight'),'mrr':x.get('candidate_mrr'),'state':x['state']} for x in corpus_history[-64:]],
                'excluded_weights':sorted(seen)}
            prompt=(c.ROOT/'research/program.md').read_text()+'\nNumeric experiment context:\n'+c.canonical(summary)
            if len(prompt)>12000:raise RuntimeError('PROMPT_LIMIT')
            result['model_calls']=1
            response=cli_json(['infer','model','run','--agent','main','--model',MODEL,'--local','--thinking','low','--prompt',prompt,'--json'],120)
            host_guard();proposal=parse_proposal(response,baseline,seen)
            weight=proposal['title_weight'];trial=evaluate(weight);trialdev=evaluate(weight,'dev')
            if frozen_evaluator()!=evaluator or c.status()['corpus_id']!=cid:raise RuntimeError('EXPERIMENT_INPUTS_CHANGED')
            if c.readjson(c.STATE/'state/retrieval.json',{'title_weight':2})['title_weight']!=baseline:raise RuntimeError('BASELINE_CHANGED')
            elapsed=time.monotonic()-started
            retained=(elapsed<300 and trial['mrr']>base['mrr'] and trialdev['mrr']>=dev['mrr']
                and all(x>=y for x,y in zip(trial['scores'],base['scores'])))
            result.update(state='RETAINED' if retained else 'REJECTED',candidate_weight=weight,
                hypothesis=proposal['hypothesis'],baseline_mrr=base['mrr'],candidate_mrr=trial['mrr'],
                dev_mrr=trialdev['mrr'],evaluator_digest=evaluator)
            if retained:
                c.writejson(c.STATE/'state/retrieval.json',{'title_weight':weight})
                c.writejson(c.ROOT/'config/retrieval.json',{'title_weight':weight})
        except Exception as error:
            # Error classes only, no provider stderr or credential-bearing diagnostics in Git.
            result['error']=str(error) if isinstance(error,RuntimeError) else type(error).__name__
        result['duration_seconds']=round(time.monotonic()-started,3)
        history.append(result)
        c.write(c.ROOT/'research/results.jsonl',''.join(c.canonical(x)+'\n' for x in history[-100:]))
        c.writejson(STATE/'last-run.json',result);c.writejson(c.STATE/'state/research-status.json',result)
        return result
