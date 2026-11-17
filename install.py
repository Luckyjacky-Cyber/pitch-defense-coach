"""Install only the skill; never upload or replace user project files."""
from pathlib import Path
import argparse,os,shutil
def main():
 p=argparse.ArgumentParser();p.add_argument('--skills-dir',help='宿主的skills目录，默认Codex skills目录');a=p.parse_args()
 home=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
 parent=Path(a.skills_dir).expanduser().resolve() if a.skills_dir else home/'skills'
 dest=parent/'pitch-defense-coach';source=Path(__file__).resolve().parent/'skills/pitch-defense-coach'
 if dest.exists():p.error('同名Skill已存在，未覆盖。请先备份或选择另一个skills目录。')
 parent.mkdir(parents=True,exist_ok=True)
 shutil.copytree(source,dest,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 print('已安装：',dest)
 print('请刷新或重新打开会话后使用 $pitch-defense-coach。')
if __name__=='__main__':main()
