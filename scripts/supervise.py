#!/usr/bin/env python3
"""Own process group watchdog: bounded CPU, memory, wall time, and quiet log rotation."""
import os,signal,subprocess,sys,time
from pathlib import Path
import psutil
root=Path(__file__).resolve().parents[1];state=Path('/Volumes/SYYR/Pubster-state')
if not os.path.ismount('/Volumes/SYYR'):sys.exit(0)
os.environ['PUBSTER_STATE']=str(state);os.environ['PYTHONPATH']=str(root/'pipeline');os.environ['TMPDIR']=str(state/'tmp');os.environ['OMP_NUM_THREADS']='1'
try:os.nice(10)
except OSError:pass
log=state/'logs/hourly.log';log.parent.mkdir(exist_ok=True)
if log.exists() and log.stat().st_size>2*1024*1024:
 for n in range(3,0,-1):
  old=log.with_suffix('.log.'+str(n));new=log.with_suffix('.log.'+str(n+1))
  if old.exists():os.replace(old,new)
 os.replace(log,log.with_suffix('.log.1'))
with log.open('ab') as output:
 child=subprocess.Popen([sys.executable,'-m','pubster.cli','run','--once','--no-notify'],cwd=root,stdout=output,stderr=output,start_new_session=True)
 started=time.monotonic();peak=0
 while child.poll() is None:
  time.sleep(.5)
  try:
   parent=psutil.Process(child.pid);processes=[parent]+parent.children(recursive=True);rss=0;cpu=0
   for process in processes:
    try:rss+=process.memory_info().rss;t=process.cpu_times();cpu+=t.user+t.system
    except psutil.NoSuchProcess:pass
   peak=max(peak,rss)
   if rss>768*1024**2 or cpu>90 or time.monotonic()-started>480:
    os.killpg(child.pid,signal.SIGTERM)
    try:child.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL)
    output.write(b'{"state":"RESOURCE_WATCHDOG_STOPPED"}\n');sys.exit(10)
  except psutil.NoSuchProcess:break
 sys.exit(child.wait())
