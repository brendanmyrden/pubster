"""Deterministic conservative scoring; unknown evidence earns zero, not invented credit."""
import datetime, re

DIMENSIONS={'power':20,'usefulness':20,'novelty':15,'composability':15,'evidence':10,'underexposure':10,'sovereignty':10}

def tokens(text):return set(re.findall(r'[a-z0-9_]+',text.lower()))

def concepts(objective,cfg):
    words=tokens(objective)
    return [key for key,value in cfg['intent_concepts'].items() if words & set(value['match'])]

def age_bucket(value):
    try:return int(value[:4])//3
    except (ValueError,TypeError):return None

def underexposure(repo,peers,concept):
    cohort=[p for p in peers if p.get('language')==repo.get('language') and age_bucket(p.get('created_at'))==age_bucket(repo.get('created_at')) and p.get('purpose_concept')==concept and p.get('full_name','').lower()!=repo['full_name'].lower()]
    if len(cohort)<3:return 0,{'status':'INSUFFICIENT_COMPARABLES','comparables':len(cohort)}
    stars=repo.get('stargazers_count',0); lower=sum(p.get('stargazers_count',0)>stars for p in cohort)
    ratio=lower/len(cohort)
    return ratio,{'status':'COHORT_ESTIMATE','comparables':len(cohort),'language':repo.get('language'),'age_bucket':age_bucket(repo.get('created_at')),'purpose_concept':concept,'fraction_more_recognized':ratio,'repositories':[p['full_name'] for p in cohort]}

def score(repo,inspection,cfg,peers,objective,overlap=False,capability=None):
    files=inspection.get('files',[])
    code=[f for f in files if f['kind']=='source' and f.get('read')]
    manifests=[f for f in files if f['kind']=='manifest' and f.get('read')]
    tests=inspection.get('test_paths',[]); benches=inspection.get('benchmark_paths',[])
    matched=concepts(objective,cfg); concept=matched[0] if matched else 'unclassified:'+objective.lower()
    evidence=inspection.get('review_evidence',{})
    # Automated source retrieval is inspection evidence, NOT a successful benchmark or semantic review.
    # Explicit scoped review evidence can elevate mechanism/utility/novelty, never README prose alone.
    support=bool(code)
    values={
      'power':1.0 if evidence.get('benchmark_reproduced') else (0.4 if evidence.get('mechanism_reviewed') and support else 0),
      'usefulness':1.0 if evidence.get('integration_success') else (0.5 if evidence.get('use_case_reviewed') and support else (0.15 if support else 0)),
      'novelty':0.8 if evidence.get('alternative_comparison') and support else 0,
      'composability':0.5 if manifests and support else (0.2 if manifests else 0),
      'evidence':min(1,0.35*bool(code)+0.15*bool(manifests)+0.15*bool(tests)+0.1*bool(benches)+0.25*bool(evidence.get('executed'))),
      'underexposure':0,
      'sovereignty':0.6 if evidence.get('offline_build') else (0.15 if manifests else 0)
    }
    raw,cohort=underexposure(repo,peers,concept)
    # Underexposure is independent of usefulness, but requires examined implementation evidence.
    values['underexposure']=raw if support else 0
    reasons={
      'power':'No independently validated performance/mechanism evidence' if not values['power'] else 'Explicit reviewed mechanism or reproduced benchmark',
      'usefulness':'Integration outcome or reviewed use case; source availability alone receives only preliminary credit',
      'novelty':'Requires an explicit comparison against alternatives; unusual keywords earn no credit',
      'composability':'Pinned manifest and implementation availability; integration remains untested',
      'evidence':'Fetched source/manifest plus located tests/benchmarks; presence is not execution',
      'underexposure':cohort['status']+'; relative recognition within language/age/purpose cohort',
      'sovereignty':'Offline build requires evidence; manifest availability is only preliminary evidence'
    }
    components={k:{'weight':cfg['weights'][k],'fraction':round(values[k],3),'points':round(values[k]*cfg['weights'][k],2),'rationale':reasons[k]} for k in DIMENSIONS}
    return {'score':round(sum(x['points'] for x in components.values()),2),'score_components':components,'scoring_version':cfg['scoring_version'],'underexposure_assessment':cohort,'existing_corpus_overlap':{'repository_present':overlap,'capability_overlap':'UNKNOWN_REQUIRES_COMPARISON'},'ranking':'capability evidence; metadata relevance is eligibility, not value'}

def integration(language,manifest_paths):
    if 'Package.swift' in manifest_paths:return 'Evaluate a commit-pinned SwiftPM dependency; inspect platform/version constraints and transitive rights.'
    if language in ['C','C++','Objective-C','Objective-C++']:return 'Prototype a C ABI/module map or Objective-C bridge; check ownership and ABI constraints.'
    if language in ['Rust','Zig','Assembly']:return 'Prototype a C ABI static library or isolated CLI; verify Apple target support and calling conventions.'
    return 'Consider an isolated CLI/service or transferable algorithm; Swift/Apple compatibility is unverified.'

def candidate(repo,inspection,cfg,peers,objective,mode,overlap=False):
    name=repo['full_name'];revision=inspection.get('revision');files=inspection.get('files',[])
    code=[f for f in files if f['kind']=='source' and f.get('read')]
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    purpose=repo.get('description') or 'Purpose needs source review'
    result={'repository':name,'canonical_identity':name.lower(),'url':repo.get('html_url','https://github.com/'+name),'revision':revision,
      'discovered_at':now,'mode':mode,'language':repo.get('language'),'license':(repo.get('license') or {}).get('spdx_id','UNKNOWN'),
      'stars':repo.get('stargazers_count',0),'forks':repo.get('forks_count',0),'created_at':repo.get('created_at'),'pushed_at':repo.get('pushed_at'),
      'last_meaningful_update':{'status':'UNKNOWN','latest_commit_at':inspection.get('commit_at'),'note':'Push/commit timestamps do not prove a meaningful code change.'},
      'actual_purpose':{'text':purpose,'status':'Claimed'},'key_implementation_techniques':inspection.get('symbols',[]),
      'power_assessment':'Unproven until mechanisms or benchmarks receive independent review.',
      'differentiation':'Compare this pinned implementation with alternatives before claiming novelty.',
      'build_opportunities':[{'text':objective,'status':'Speculative'}],
      'swift_integration':integration(repo.get('language'),[f['path'] for f in files if f['kind']=='manifest']),
      'source_files':files,'test_paths':inspection.get('test_paths',[]),'benchmark_paths':inspection.get('benchmark_paths',[]),
      'evidence_status':'Source-supported' if code else 'Claimed','evidence_scope':'Pinned file retrieval and structural observations only; no code execution or independent performance verification.',
      'maintenance_risk':{'archived':bool(repo.get('archived')),'last_push':repo.get('pushed_at'),'assessment':'Archived: maintenance risk, not rejection' if repo.get('archived') else 'Unreviewed'},
      'security_risk':'NOT_AUDITED','license_compatibility':'UNREVIEWED','integration_effort':'UNKNOWN','evidence_confidence':'LOW' if code else 'VERY_LOW',
      'rights':'UNREVIEWED','security':'NOT_AUDITED','compatibility':'UNVERIFIED','stage':'Scored' if revision else 'Discovered',
      'recommendation':'investigate','limitations':['No benchmark executed','No automatic corpus admission','Dependency versions and license restrictions require review'],
      'unresolved_questions':['Does the implementation satisfy the target use case?','What differentiates it from known alternatives?','Can it build and run on the required Apple platform?'],
      'inspection':inspection,'capabilities':[]}
    result.update(score(repo,inspection,cfg,peers,objective,overlap))
    for f in code:
        cap={'id':name.lower()+':'+f['path'],'name':f['path'],'revision':revision,'source_url':f['url'],'status':'Source-supported',
          'scope':'Implementation file, not yet a semantically verified capability','symbols':f.get('symbols',[]),'recommendation':'investigate'}
        # Repository-wide manifests/benchmarks do not establish this individual implementation's power.
        scoped={'files':[f],'revision':revision}
        cap.update(score(repo,scoped,cfg,peers,objective,overlap,capability=f['path']))
        result['capabilities'].append(cap)
    return result
