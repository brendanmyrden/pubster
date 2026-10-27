"""Scope setuptools' artifact discovery to real wheels, ignoring exFAT AppleDouble."""
from pathlib import Path
import setuptools.build_meta
p=Path(setuptools.build_meta.__file__)
s=p.read_text()
old='matching = (f for f in os.listdir(directory) if f.endswith(extension))'
new='matching = (f for f in os.listdir(directory) if not f.startswith("._") and f.endswith(extension))'
if old in s:p.write_text(s.replace(old,new))
elif new not in s:raise RuntimeError('SETUPTOOLS_BUILD_COMPAT_REVIEW_REQUIRED')
print('Local setuptools artifact discovery excludes AppleDouble metadata')
import wheel.wheelfile
for p in [Path(wheel.wheelfile.__file__),Path(setuptools.__file__).parent/'_vendor/wheel/wheelfile.py']:
    if not p.exists():continue
    s=p.read_text()
    old='for name in sorted(filenames):'
    new='for name in sorted(n for n in filenames if not n.startswith("._")):'
    if old in s:p.write_text(s.replace(old,new))
    elif new not in s:raise RuntimeError('WHEEL_BUILD_COMPAT_REVIEW_REQUIRED')
print('Local wheel writer excludes AppleDouble sidecars')
