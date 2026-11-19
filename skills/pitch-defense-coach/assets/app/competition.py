"""Freeze the selected training rubric and timing in each new session."""
from pathlib import Path
import json, copy

PROFILES = {
 'sanchuang-regular': {
  'label':'三创赛 · 常规赛（第17届参考）', 'roadshowMinutes':8, 'defenseMinutes':7,
  'ruleWeights':dict(zip(['创新','创意','创业','演讲','文案'],[25,25,25,15,10]))},
 'sanchuang-practical': {
  'label':'三创赛 · 实战赛（第17届参考）', 'roadshowMinutes':8, 'defenseMinutes':7,
  'ruleWeights':dict(zip(['创新','创意','创业准备','创业过程','创业成绩','演讲','文案'],[15,15,10,20,15,15,10]))}
}

def resolve_profile(root, selected=None):
 knowledge=json.loads((Path(root)/'public/knowledge.json').read_text(encoding='utf8'))
 key=selected or knowledge.get('competitionProfile','project')
 if key=='project':
  return {'id':key,'label':'当前项目配置','roadshowMinutes':10,'defenseMinutes':5,'ruleWeights':copy.deepcopy(knowledge['ruleWeights'])}
 if key not in PROFILES:raise ValueError('赛事模式无效')
 result=copy.deepcopy(PROFILES[key]);result['id']=key
 result['ruleWeights']={k:f'第17届参考权重 {v}；反馈非官方评分' for k,v in result['ruleWeights'].items()}
 result['ruleStatus']='第17届通则参考；须核对用户届次、赛段及实战赛专项指南'
 return result
