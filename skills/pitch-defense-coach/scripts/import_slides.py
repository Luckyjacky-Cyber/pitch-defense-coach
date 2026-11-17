"""Import full-slide images; never extract individual PPT media as slides."""
from pathlib import Path
import argparse,json,hashlib,re,shutil,uuid

def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--app',required=True);p.add_argument('--images',required=True);p.add_argument('--source');p.add_argument('--order');p.add_argument('--replace',action='store_true');a=p.parse_args()
 app=Path(a.app).resolve();folder=Path(a.images).resolve();manifest=app/'public/deck.json'
 if not manifest.is_file():p.error('不是有效的训练工具目录')
 old=json.loads(manifest.read_text(encoding='utf-8'))
 if old.get('sha256')!='placeholder' and not a.replace:p.error('已有PPT，请核对并使用 --replace；脚本会保留原清单。')
 files=[x for x in folder.iterdir() if x.is_file() and x.suffix.lower() in ['.jpg','.jpeg','.png','.webp']]
 if not files:p.error('没有可导入的逐页图片')
 if a.order:
  names=json.loads(Path(a.order).read_text(encoding='utf-8-sig'))
  if not isinstance(names,list) or any(not isinstance(n,str) for n in names):p.error('顺序文件应为文件名数组')
  mapping={x.name:x for x in files}
  if len(names)!=len(set(names)) or set(names)!=set(mapping):p.error('顺序文件必须恰好包含全部图片且不重复')
  files=[mapping[n] for n in names]
 else:
  nums=[]
  for f in files:
   matches=re.findall(r'\d+',f.stem)
   if len(matches)!=1:p.error('文件名页序不明确，请按01、02命名或使用 --order')
   nums.append((int(matches[0]),f))
  if len({n for n,f in nums})!=len(nums):p.error('页码重复，请提供 --order')
  files=[f for n,f in sorted(nums)]
 source=Path(a.source).resolve() if a.source else None
 if source and not source.is_file():p.error('源文件不存在')
 identity=uuid.uuid4().hex[:12];relative=Path('slides')/identity;destination=app/'public'/relative;destination.mkdir(parents=True)
 slides=[]
 for i,f in enumerate(files,1):
  name=f'{i:02d}{f.suffix.lower()}';shutil.copyfile(f,destination/name)
  slides.append({'page':i,'title':f'第{i}页','image':(relative/name).as_posix(),'suggestedSeconds':round(600/len(files),2),'sha256':digest(f),'originalFilename':f.name})
 result={'source':source.name if source else folder.name,'sha256':digest(source) if source else hashlib.sha256(''.join(x['sha256'] for x in slides).encode()).hexdigest(),'hashScope':'source-file' if source else 'ordered-images','slides':slides}
 if old.get('sha256')!='placeholder':
  archive=app/'deck-history';archive.mkdir(exist_ok=True);shutil.copyfile(manifest,archive/f'{identity}.json')
 temp=manifest.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(manifest)
 print(json.dumps({'pages':len(slides),'source':result['source'],'note':'请重启服务并核对首尾页和顺序；静态图片不保留动画或视频。'},ensure_ascii=False))
if __name__=='__main__':main()
