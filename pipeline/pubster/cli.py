import sys,json,argparse
from . import core

def main():
    if len(sys.argv)>1 and sys.argv[1]=='intelligence':
        from .intelligence.operator import main as intelligence_main
        intelligence_main(sys.argv[2:]);return 0
    p=argparse.ArgumentParser();p.add_argument('command');p.add_argument('action',nargs='?');p.add_argument('--force',action='store_true');p.add_argument('--json',action='store_true');p.add_argument('--once',action='store_true');p.add_argument('--no-notify',action='store_true');p.add_argument('--candidate',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--suite');p.add_argument('--profile');p.add_argument('--limit',type=int,default=2);p.add_argument('--redacted',action='store_true');args=p.parse_args()
    try:
        if args.command=='init':core.init();r={'initialized':True}
        elif args.command=='ingest':
            with core.lock():r=core.ingest(args.force)
        elif args.command in ['export','accept']:
            with core.lock():r=core.export()
        elif args.command=='discover':
            from . import discovery, operations
            with core.lock():
                operations.assert_managed_untouched()
                r=discovery.tick(args.force)
                core.writejson(core.STATE/'state/managed-files.json',operations.managed_snapshot())
        elif args.command=='status':r=core.status()
        elif args.command=='validate':
            db=core.connect();r={'valid':core.validate_records([json.loads(x[0]) for x in db.execute('SELECT record_json FROM chunks')],db)};db.close()
        elif args.command=='search':r=core.search(args.action or '')
        elif args.command=='backup':r=core.backup()
        elif args.command in ['pause','stop']:core.write(core.STATE/'state/paused','paused\n');r={'paused':True}
        elif args.command=='resume':(core.STATE/'state/paused').unlink(missing_ok=True);r={'paused':False}
        elif args.command in ['run','research','evaluate','sync-github','verify-github','doctor','security','scheduler']:
            from . import operations;r=operations.dispatch(args)
        else:raise RuntimeError('COMMAND_NOT_IMPLEMENTED')
        print(json.dumps(r,sort_keys=True));return 0
    except Exception as e:
        code=str(e) if isinstance(e,(RuntimeError,AssertionError)) else type(e).__name__
        print(json.dumps({'error':code[:160]}));return 20
if __name__=='__main__':sys.exit(main())
