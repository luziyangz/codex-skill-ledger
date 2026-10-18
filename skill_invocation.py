"""Read supported Codex invocation policy as data; never execute skill instructions."""
from pathlib import Path
import re

def read_policy(skill_file):
    skill=Path(skill_file);metadata=skill.parent/'agents'/'openai.yaml'
    result={'skill_path':str(skill),'metadata_path':str(metadata),'allow_implicit':None,'basis':''}
    if not skill.is_file():result['basis']='技能文件不在此位置，无法核实。';return result
    if not metadata.exists():
        result.update(allow_implicit=True,basis='没有 agents/openai.yaml；按 Codex 默认规则允许自动匹配。');return result
    try:text=metadata.read_text(encoding='utf-8-sig')
    except (OSError,UnicodeError):result['basis']='无法读取调用策略文件。';return result
    if '\t' in text:result['basis']='配置含制表符，需核对 YAML。';return result
    lines=text.splitlines();headers=[]
    for index,line in enumerate(lines):
        if re.match(r'^policy\s*:',line):headers.append(index)
    if len(headers)>1:result['basis']='存在重复 policy 字段，需核对。';return result
    if not headers:
        if re.search(r'allow_implicit_invocation|(?m:^\s*(?:<<\s*:|[\'\"]policy[\'\"]\s*:))',text) or text.lstrip().startswith(('{','[')):
            result['basis']='配置结构无法可靠核实，建议手动选择技能。';return result
        if text.strip() and not re.search(r'(?m)^\w[\w-]*\s*:',text):result['basis']='无法识别配置结构。';return result
        result.update(allow_implicit=True,basis='未设置 policy.allow_implicit_invocation；默认允许自动匹配。');return result
    start=headers[0];tail=lines[start].split(':',1)[1].split('#',1)[0].strip()
    if tail:
        match=re.fullmatch(r'\{\s*allow_implicit_invocation\s*:\s*(true|false)\s*\}',tail,re.I)
        if not match:result['basis']='policy 使用复杂或引用结构，建议手动核对。';return result
        value=match.group(1).lower()=='true'
    else:
        block=[]
        for line in lines[start+1:]:
            if line.strip() and not line.lstrip().startswith('#') and len(line)==len(line.lstrip()):break
            block.append(line)
        policy='\n'.join(block)
        indents=[len(line)-len(line.lstrip()) for line in block if line.strip() and not line.lstrip().startswith('#')]
        indent=min(indents) if indents else 2
        matches=re.findall(r'(?m)^ {'+str(indent)+r'}allow_implicit_invocation\s*:\s*(.*?)\s*$',policy)
        if not matches:
            if re.search(r'[&*{}]|allow_implicit_invocation',policy):result['basis']='策略结构不能可靠核实。';return result
            result.update(allow_implicit=True,basis='policy 中未设置自动匹配开关；默认允许自动匹配。');return result
        if len(matches)!=1:result['basis']='自动匹配字段重复，需核对。';return result
        scalar=matches[0].split('#',1)[0].strip().lower()
        if scalar not in ('true','false'):result['basis']='自动匹配开关不是可核实的布尔值。';return result
        value=scalar=='true'
    result.update(allow_implicit=value,basis='policy.allow_implicit_invocation = '+str(value).lower())
    return result

def invocation_info(row,frontmatter_reader=None):
    candidates=[Path(p) for p in row.get('paths',[]) if Path(p).is_file()]
    scope='current' if row.get('installed') else 'backup'
    if not row.get('installed'):
        candidates=[]
        archived=row.get('archive_paths',[])
        if isinstance(archived,str):archived=[archived] if archived else []
        for path in list(archived)+row.get('recovery_paths',[]):
            p=Path(path);p=p if p.name=='SKILL.md' else p/'SKILL.md'
            if p.is_file():candidates.append(p)
    # Linked copies of the same physical directory have the same policy.
    seen=set();copies=[];description=''
    for skill in candidates:
        try:identity=str(skill.resolve(strict=True)).casefold()
        except OSError:continue
        if identity in seen:continue
        seen.add(identity);candidate_description=''
        if frontmatter_reader:
            try:
                declared,candidate_description,_=frontmatter_reader(skill)
                if row.get('name') and declared!=row.get('skill_name',row['name']).split(':',1)[-1]:continue
            except (OSError,ValueError,UnicodeError):continue
        copies.append(read_policy(skill))
        if not description:description=candidate_description
    values={entry['allow_implicit'] for entry in copies}
    if not copies or None in values:
        mode='unknown';label='策略待核对';summary='尚不能核实自动匹配策略，建议从技能菜单手动选择。'
    elif len(values)>1:
        mode='mixed';label='多份策略不同';summary='不同副本的自动匹配配置不一致；建议手动选择具体版本。'
    elif values=={False}:
        mode='manual';label='仅手动调用';summary='该技能明确关闭自动匹配，需要先从技能菜单选择。'
    else:
        mode='auto_manual';label='自动匹配 + 手动';summary='相关任务可由 Codex 自动选择，也可以手动指定；不保证每次自动触发。'
    if scope=='backup':summary='以下来自恢复备份，重新安装后需复核。'+summary
    if not copies:scope='none'
    return {'mode':mode,'label':label,'summary':summary,'scope':scope,'copies':copies,'trigger':row.get('purpose',''),'description':description}
