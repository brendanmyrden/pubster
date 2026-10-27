"""Checksum-verified portable OpenRefine/JRE install within the mounted project."""
import hashlib,json,os,tarfile,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if not os.path.ismount('/Volumes/SYYR') or ROOT!=Path('/Volumes/SYYR/Pubster'):
    raise RuntimeError('SYYR_PROJECT_REQUIRED')
store=ROOT/'.quality';downloads=store/'downloads';downloads.mkdir(parents=True,exist_ok=True)
manifest=json.loads((ROOT/'services/data-quality/tools.lock.json').read_text())
for name,item in manifest.items():
    archive=downloads/item['archive']
    if not archive.exists():
        with urllib.request.urlopen(item['url'],timeout=60) as response, archive.open('wb') as target:
            while data:=response.read(1024*1024):target.write(data)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=item['sha256']:
        raise RuntimeError('INSTALLER_HASH_MISMATCH_'+name)
    destination=store/item['destination']
    if not (destination/item['directory']).exists():
        destination.mkdir(exist_ok=True)
        with tarfile.open(archive) as bundle:bundle.extractall(destination,filter='data')
# AppleDouble files look like corrupt jars to Jetty; preserve outside the classpath.
for p in (store/'tools').rglob('._*'):
    if p.is_file():
        target=store/'appledouble/review-tools'/p.relative_to(store/'tools')
        target.parent.mkdir(parents=True,exist_ok=True);p.rename(target)
print('Portable archives verified; tools remain in '+str(store))
