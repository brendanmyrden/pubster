"""Preserve exFAT metadata outside importlib's distribution-discovery directory."""
from pathlib import Path
import sysconfig
root=Path(sysconfig.get_paths()['purelib'])
project=Path(__file__).resolve().parents[1]
if not root.is_relative_to(project/'.quality'):raise RuntimeError('PROJECT_ENV_REQUIRED')
out=project/'.quality/appledouble/python-site-packages';out.mkdir(parents=True,exist_ok=True)
for p in root.glob('._*'):
    if p.is_file():p.rename(out/p.name)
