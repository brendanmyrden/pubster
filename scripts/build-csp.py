from pathlib import Path
from html.parser import HTMLParser
import hashlib,base64,json
root=Path(__file__).resolve().parents[1];hashes=set()
class Scripts(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=False);self.inline=False;self.parts=[]
 def handle_starttag(self,tag,attrs):
  if tag=='script':self.inline='src' not in dict(attrs);self.parts=[]
 def handle_data(self,data):
  if self.inline:self.parts.append(data)
 def handle_endtag(self,tag):
  if tag=='script' and self.inline:
   hashes.add("'sha256-"+base64.b64encode(hashlib.sha256(''.join(self.parts).encode()).digest()).decode()+"'");self.inline=False
for p in (root/'apps/web/out').rglob('*.html'):
 if not p.name.startswith('._'):Scripts().feed(p.read_text())
(root/'apps/edge/src/csp.json').write_text(json.dumps(sorted(hashes))+'\n');print('Generated',len(hashes),'inline-script CSP hashes')
