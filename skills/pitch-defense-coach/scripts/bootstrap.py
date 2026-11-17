"""Create an isolated app without modifying an existing project."""
from pathlib import Path
import argparse,shutil,json

def main():
 p=argparse.ArgumentParser();p.add_argument('--target',required=True);a=p.parse_args()
 skill=Path(__file__).resolve().parents[1];target=Path(a.target).expanduser().resolve()
 if target.exists():p.error('目标已存在；请选择新的目录，避免覆盖已有材料和练习记录。')
 shutil.copytree(skill/'assets/app',target)
 (target/'COACH.md').write_text('此目录为独立训练实例。请使用 pitch-defense-coach Skill 的 references/coach-protocol.md。\n数据保存在 data/，不要上传GitHub。\n',encoding='utf-8')
 print(json.dumps({'app':str(target),'start':'python server.py --port 8769','url':'http://127.0.0.1:8769/','status':'已创建；尚未导入项目材料或安装可选模型'},ensure_ascii=False))
if __name__=='__main__':main()
