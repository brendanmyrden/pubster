"""Additive, resumable intelligence ledger. No writes to the corpus database."""
import json, sqlite3, time
from pathlib import Path
from .. import core as c

class Store:
    def __init__(self, path=None):
        self.path=Path(path or c.ROOT/'.quality/intelligence/ledger.sqlite3')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path,timeout=5)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        version=self.db.execute('PRAGMA user_version').fetchone()[0]
        if version>1: raise RuntimeError('NEWER_INTELLIGENCE_SCHEMA')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY,at REAL NOT NULL,path TEXT NOT NULL,state TEXT NOT NULL,bytes INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,at REAL NOT NULL,body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS criteria(version TEXT PRIMARY KEY,digest TEXT NOT NULL,body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS scans(id INTEGER PRIMARY KEY,identity TEXT NOT NULL,mode TEXT NOT NULL,
          started REAL NOT NULL,finished REAL,state TEXT NOT NULL,plan TEXT NOT NULL,cursor INTEGER NOT NULL DEFAULT 0,
          found TEXT NOT NULL DEFAULT '{}',errors TEXT NOT NULL DEFAULT '[]',stats TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS snapshots(repository TEXT NOT NULL,revision TEXT NOT NULL,version TEXT NOT NULL,
          at REAL NOT NULL,body TEXT NOT NULL,PRIMARY KEY(repository,revision,version));
        CREATE TABLE IF NOT EXISTS evaluations(id TEXT PRIMARY KEY,repository TEXT NOT NULL,revision TEXT NOT NULL,version TEXT NOT NULL,at REAL NOT NULL,body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS edges(origin TEXT NOT NULL,source TEXT NOT NULL,target TEXT NOT NULL,
          kind TEXT NOT NULL,hop INTEGER NOT NULL,evidence TEXT NOT NULL,at REAL NOT NULL,
          PRIMARY KEY(origin,source,target,kind));
        CREATE TABLE IF NOT EXISTS frontier(origin TEXT NOT NULL,repository TEXT NOT NULL,hop INTEGER NOT NULL,
          state TEXT NOT NULL DEFAULT 'pending',PRIMARY KEY(origin,repository));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,repository TEXT NOT NULL,revision TEXT NOT NULL,
          at REAL NOT NULL,kind TEXT NOT NULL,actor TEXT NOT NULL,body TEXT NOT NULL);
        PRAGMA user_version=1;
        ''')
    def close(self): self.db.close()
    def meta(self,key,default=None):
        row=self.db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default
    def setmeta(self,key,value):
        with self.db:self.db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',(key,c.canonical(value)))
    def register(self,cfg):
        # All ranking semantics are versioned, not just the seven weights.
        body={k:cfg[k] for k in ['scoring_version','weights','intent_concepts','high_value_threshold']}
        body['ranking_implementation_sha256']=c.digest(Path(__file__).with_name('ranking.py').read_bytes())
        digest=c.digest(c.canonical(body));version=cfg['scoring_version']
        row=self.db.execute('SELECT digest FROM criteria WHERE version=?',(version,)).fetchone()
        if row and row[0]!=digest:raise RuntimeError('SCORING_VERSION_REUSE_FORBIDDEN')
        with self.db:self.db.execute('INSERT OR IGNORE INTO criteria VALUES (?,?,?)',(version,digest,c.canonical(body)))
    def request_start(self,path):
        with self.db:cursor=self.db.execute("INSERT INTO requests(at,path,state) VALUES (?,?,'started')",(time.time(),path))
        return cursor.lastrowid
    def request_end(self,key,state,size=0):
        with self.db:self.db.execute('UPDATE requests SET state=?,bytes=? WHERE id=?',(state,size,key))
    def cached(self,key,ttl):
        row=self.db.execute('SELECT at,body FROM cache WHERE key=?',(key,)).fetchone()
        return json.loads(row['body']) if row and time.time()-row['at']<ttl else None
    def cache(self,key,body):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)',(key,time.time(),c.canonical(body)))
            self.db.execute('DELETE FROM cache WHERE key IN (SELECT key FROM cache ORDER BY at DESC LIMIT -1 OFFSET 128)')
            while self.db.execute('SELECT coalesce(sum(length(body)),0) FROM cache').fetchone()[0]>32000000:
                self.db.execute('DELETE FROM cache WHERE key=(SELECT key FROM cache ORDER BY at LIMIT 1)')
    def begin(self,identity,mode,plan):
        row=self.db.execute("SELECT * FROM scans WHERE identity=? AND state='running' ORDER BY id DESC LIMIT 1",(identity,)).fetchone()
        if row:return dict(row)
        with self.db:
            cur=self.db.execute('INSERT INTO scans(identity,mode,started,state,plan) VALUES (?,?,?,\'running\',?)',(identity,mode,time.time(),c.canonical(plan)))
        return dict(self.db.execute('SELECT * FROM scans WHERE id=?',(cur.lastrowid,)).fetchone())
    def checkpoint(self,scan,cursor,found,errors,stats):
        with self.db:self.db.execute('UPDATE scans SET cursor=?,found=?,errors=?,stats=? WHERE id=?',(cursor,c.canonical(found),c.canonical(errors),c.canonical(stats),scan))
    def finish(self,scan,stats):
        with self.db:self.db.execute("UPDATE scans SET state='complete',finished=?,stats=? WHERE id=?",(time.time(),c.canonical(stats),scan))
    def snapshot(self,repo,revision,version):
        row=self.db.execute('SELECT body FROM snapshots WHERE repository=? AND revision=? AND version=?',(repo.lower(),revision,version)).fetchone()
        return json.loads(row[0]) if row else None
    def evaluation(self,item):
        body=c.canonical(item)
        with self.db:self.db.execute('INSERT OR IGNORE INTO evaluations VALUES (?,?,?,?,?,?)',(c.digest(body),item['canonical_identity'],item.get('revision') or 'unresolved',item['scoring_version'],time.time(),body))
    def save(self,item):
        self.evaluation(item)
        with self.db:self.db.execute('INSERT OR IGNORE INTO snapshots VALUES (?,?,?,?,?)',(item['canonical_identity'],item.get('revision') or 'unresolved:'+str(item['discovered_at']),item['scoring_version'],time.time(),c.canonical(item)))
    def edge(self,origin,source,target,kind,hop,evidence,limit=500,max_hops=3):
        origin,source,target=origin.lower(),source.lower(),target.lower()
        if hop>max_hops or target==source:return
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO edges VALUES (?,?,?,?,?,?,?)',(origin,source,target,kind,hop,c.canonical(evidence),time.time()))
            count=self.db.execute('SELECT count(*) FROM frontier').fetchone()[0]
            if count<limit:self.db.execute('INSERT OR IGNORE INTO frontier(origin,repository,hop) VALUES (?,?,?)',(origin,target,hop))
    def seed(self,name):
        with self.db:self.db.execute('INSERT OR IGNORE INTO frontier(origin,repository,hop) VALUES (?,?,0)',(name.lower(),name.lower()))
    def migrate(self,directory):
        if self.meta('legacy_migrated'):return
        # Immutable copy: old reports/rights decisions are never rewritten by migration.
        dest=self.path.parent/'legacy-v1';dest.mkdir(exist_ok=True)
        for p in sorted(directory.glob('*.json')):
            if p.name.startswith('._'):continue
            data=p.read_bytes();out=dest/(c.digest(data)+'.json')
            if not out.exists():c.write(out,data)
        for p in [c.ROOT/'research/candidate-admission-review.json',c.ROOT/'config/rights-policy.json']:
            if p.exists():c.write(dest/p.name,p.read_bytes())
        self.setmeta('legacy_migrated',{'at':time.time(),'source':str(directory)})
    def review_context(self,repo,revision):
        context={'assessment':{},'capability_findings':[]}
        for row in self.db.execute('SELECT kind,body FROM events WHERE repository=? AND revision=? ORDER BY id',(repo.lower(),revision)):
            body=json.loads(row['body'])
            if row['kind']=='rejected':context={'assessment':{},'capability_findings':[],'recommendation':'reject'}
            elif row['kind'] in ['reviewed','verified','approved']:
                if row['kind']=='reviewed':context.pop('recommendation',None)
                context['assessment'].update(body.get('assessment',{}))
                if 'capability_findings' in body:context['capability_findings']=body['capability_findings']
                if 'recommendation' in body:context['recommendation']=body['recommendation']
        return context
    def stage(self,repo,revision):
        mapping={'reviewed':'Reviewed','verified':'Verified','approved':'Approved','rejected':'Rejected'}
        row=self.db.execute("SELECT kind FROM events WHERE repository=? AND revision=? AND kind IN ('reviewed','verified','approved','rejected') ORDER BY id DESC LIMIT 1",(repo.lower(),revision)).fetchone()
        return mapping[row[0]] if row else 'Scored'
    def event(self,repo,revision,kind,actor,body):
        if kind not in ['reviewed','verified','approved','rejected','prototype','integration','false_positive','capability_introduced','feedback']:
            raise ValueError('Unknown event')
        if not actor or not body.get('rationale'):raise ValueError('Actor and rationale required')
        if not self.db.execute('SELECT 1 FROM snapshots WHERE repository=? AND revision=?',(repo.lower(),revision)).fetchone():raise ValueError('Unknown pinned snapshot')
        stage=self.stage(repo,revision)
        if kind=='verified' and (stage!='Reviewed' or not body.get('evidence')):raise ValueError('Current review and verification evidence required')
        if kind=='approved' and (stage!='Verified' or not body.get('license_review')):raise ValueError('Current verification and license review required')
        if kind in ['prototype','integration'] and body.get('outcome') not in ['success','failure']:raise ValueError('Explicit outcome required')
        with self.db:self.db.execute('INSERT INTO events(repository,revision,at,kind,actor,body) VALUES (?,?,?,?,?,?)',(repo.lower(),revision,time.time(),kind,actor,c.canonical(body)))
        return {'recorded':kind,'corpus_modified':False}
    def metrics(self):
        scans=[json.loads(r[0]) for r in self.db.execute("SELECT stats FROM scans WHERE state='complete'")]
        events=[dict(r) for r in self.db.execute('SELECT * FROM events')]
        bodies=[json.loads(r[0]) for r in self.db.execute('SELECT body FROM snapshots')]
        total=sum(s.get('candidate_count',0) for s in scans)
        integrations=[e for e in events if e['kind']=='integration']
        verified={(e['repository'],e['revision']) for e in events if e['kind']=='verified' and time.time()-e['at']<30*86400}
        thresholds={row['version']:json.loads(row['body']).get('high_value_threshold',60) for row in self.db.execute('SELECT version,body FROM criteria')}
        hidden={(b['canonical_identity'],b.get('revision')) for b in bodies if b.get('score',0)>=thresholds.get(b.get('scoring_version'),60) and b.get('score_components',{}).get('underexposure',{}).get('points',0)>0}
        return {'scans':len(scans),'unique_repositories':len({b['canonical_identity'] for b in bodies}),
          'high_value_per_100_candidates':round(100*sum(s.get('high_value',0) for s in scans)/total,2) if total else None,
          'verified_hidden_gems_last_30_days':len(verified & hidden),'duplicates':sum(s.get('duplicates',0) for s in scans),
          'false_positives':sum(e['kind']=='false_positive' for e in events),'new_capabilities_introduced':sum(e['kind']=='capability_introduced' for e in events),
          'prototypes_completed':sum(e['kind']=='prototype' for e in events),'integration_success_rate':sum(json.loads(e['body']).get('outcome')=='success' for e in integrations)/len(integrations) if integrations else None,
          'network_requests':self.db.execute('SELECT count(*) FROM requests').fetchone()[0],'failed_or_interrupted_requests':self.db.execute("SELECT count(*) FROM requests WHERE state!='complete'").fetchone()[0],'reported_scan_requests':sum(s.get('requests',0) for s in scans),'processing_seconds':round(sum(s.get('seconds',0) for s in scans),2),
          'model_calls':0,'paid_api_calls':0,'cost_note':'Request counts and runtime measured; monetary infrastructure cost not estimated',
          'pending_scans':self.db.execute("SELECT count(*) FROM scans WHERE state='running'").fetchone()[0]}
