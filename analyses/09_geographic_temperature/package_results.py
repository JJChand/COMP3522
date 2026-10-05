"""Package this analysis directory without modifying any other analysis."""
from pathlib import Path
import argparse,zipfile,hashlib,json
ROOT=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
target=a.output.resolve();target.parent.mkdir(parents=True,exist_ok=True)
if target.is_relative_to(ROOT):raise ValueError('Archive output must be outside the analysis directory')
paths=sorted(p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
manifest={'files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],'note':'Raw full daily pair export is outside the Git repository and not in this archive.'}
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
 for p in paths:z.write(p,ROOT.name+'/'+p.relative_to(ROOT).as_posix())
 z.writestr(ROOT.name+'/delivery_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
with zipfile.ZipFile(target) as z:assert z.testzip() is None
print('Packaged',len(paths)+1,'files; CRC passed;',target.stat().st_size,'bytes.')
