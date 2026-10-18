"""Local skill inventory, event ledger and user-confirmed management. Stdlib only."""
import argparse
from collections import defaultdict
from contextlib import contextmanager
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import sys
import time
import tomllib
import webbrowser
import skill_scope

HERE=Path(__file__).resolve().parent
if __name__=='__main__':sys.modules.setdefault('skill_ledger',sys.modules[__name__])
LOCAL_TZ=timezone(timedelta(hours=8))
FIELDS=['名称','所属项目 / 范围','状态','用途','调用方式','使用方法','技能来源','版本','副本数','文件路径']
HISTORY_FIELDS=['事件时间','时间类型','操作','技能名称','所属项目 / 范围','说明','记录依据']

def now(): return datetime.now(LOCAL_TZ).isoformat(timespec='seconds')
def read_json(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def key_path(p): return os.path.normcase(os.path.abspath(str(p))).replace('\\','/')
def atomic_write(path,text):
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(text,encoding='utf-8',newline='')
    os.replace(temporary,path)

@contextmanager
def locked(base,filename='ledger.lock'):
    data=base/'.data';data.mkdir(exist_ok=True)
    with (data/filename).open('a+b') as f:
        if f.tell()==0: f.write(b'0');f.flush()
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            try: msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError: raise RuntimeError('另一个更新正在进行，请稍后重试。')
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try: yield
        finally:
            if os.name=='nt':
                f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(f,fcntl.LOCK_UN)

def frontmatter(path):
    text=path.read_text(encoding='utf-8-sig')
    match=re.match(r'\A---\s*\n(.*?)\n---(?:\s*\n|$)',text,re.S)
    if not match: raise ValueError('缺少 YAML frontmatter')
    head=match.group(1)
    n=re.search(r'(?m)^name:\s*([^\n]+)',head)
    if not n: raise ValueError('缺少技能名称')
    name=n.group(1).strip().strip('\"\'')
    desc=re.search(r'(?ms)^description:[ \t]*(.*?)(?=\n[A-Za-z][\w-]*:|\Z)',head)
    description=desc.group(1).strip() if desc else ''
    if description.startswith(('|','>')): description=description.split('\n',1)[-1]
    description=re.sub(r'\s+',' ',description).strip().strip('\"\'')
    return name,description,hashlib.sha256(text.encode('utf-8')).hexdigest()

def skill_paths(root):
    """Follow skill-directory links, but visit each canonical directory once per root."""
    result=[];pending=[root];seen=set()
    while pending:
        current=pending.pop()
        resolved=key_path(current.resolve(strict=True))
        if resolved in seen: continue
        seen.add(resolved)
        for p in sorted(current.iterdir(),key=lambda p:p.name):
            if p.name in ('.git','node_modules','__pycache__'): continue
            if p.is_symlink() and not p.exists(): continue
            if p.is_dir(): pending.append(p)
            elif p.name=='SKILL.md': result.append(p)
    return result

def version_key(path):
    return tuple(int(n) for n in re.findall(r'\d+',path.name)),path.name

def scan(settings,reference):
    errors=[];files=[]
    cfg_path=Path(settings['codex_config'])
    config=tomllib.loads(cfg_path.read_text(encoding='utf-8-sig')) if cfg_path.exists() else {}
    if not cfg_path.exists() and settings.get('codex_config_required', True):
        raise RuntimeError(f'Codex 配置不可访问：{cfg_path}')
    overrides={key_path(e['path']):e.get('enabled',True) for e in config.get('skills',{}).get('config',[])}
    known_plugins=set(settings.get('known_plugins',[]))
    for entry in settings['skill_roots']:
        root=Path(entry['path'])
        if not root.exists():
            if entry.get('required',True): raise RuntimeError(f'技能目录不可访问，停止更新以避免误报移除：{root}')
            continue
        for p in skill_paths(root): files.append((p,entry['label'],'','',False))
    cache=Path(settings['plugin_cache'])
    if not cache.is_dir() and settings.get('plugin_cache_required', True):
        raise RuntimeError(f'插件缓存目录不可访问：{cache}')
    for market in sorted(cache.iterdir()) if cache.is_dir() else []:
        if not market.is_dir(): continue
        for plugin in sorted(market.iterdir()):
            if not plugin.is_dir() or plugin.name.startswith('plugin-backup-'): continue
            versions=[p for p in plugin.iterdir() if p.is_dir() and (p/'.codex-plugin'/'plugin.json').is_file()]
            if not versions: continue
            version=max(versions,key=version_key)
            manifest=read_json(version/'.codex-plugin'/'plugin.json')
            declared=manifest.get('skills')
            if not declared: continue
            declared=[declared] if isinstance(declared,str) else declared
            if not isinstance(declared,list): raise RuntimeError(f'插件 skills 声明无法识别：{plugin.name}')
            plugin_id=plugin.name+'@'+market.name
            plugin_cfg=config.get('plugins',{}).get(plugin_id,{})
            disabled=plugin_cfg.get('enabled') is False
            registered=plugin.name in known_plugins or plugin_cfg.get('enabled') is True
            origin=plugin_id
            for relative in declared:
                if not isinstance(relative,str): raise RuntimeError(f'插件技能路径无法识别：{plugin.name}')
                location=version/relative
                if not location.resolve().is_relative_to(version.resolve()):
                    raise RuntimeError(f'插件技能路径越出包目录：{plugin.name}')
                if not location.exists(): raise RuntimeError(f'插件技能目录缺失，停止更新：{location}')
                paths=[location] if location.is_file() else skill_paths(location)
                for p in paths:
                    if p.name=='SKILL.md': files.append((p,origin,plugin.name,version.name,disabled or not registered))
    grouped=defaultdict(list)
    for path,origin,plugin,version,inactive in files:
        try: name,description,checksum=frontmatter(path)
        except (OSError,UnicodeError,ValueError) as e:
            errors.append(f'{path}: {e}');continue
        override=overrides.get(key_path(path),overrides.get(key_path(path.parent)))
        if override is False: state='配置停用'
        elif plugin:
            plugin_disabled=config.get('plugins',{}).get(origin,{}).get('enabled') is False
            state='配置停用' if plugin_disabled else ('缓存待核对' if inactive else '已登记')
        else: state='已登记'
        skill_name=plugin+':'+name if plugin else name
        scope=skill_scope.scope_for(path,settings) if not plugin else {'scope_id':'global','scope_label':'全局技能','scope_path':'','scope_kind':'global'}
        identity=skill_scope.identity(skill_name,scope)
        grouped[identity].append({'skill_name':skill_name,**scope,'path':str(path),'origin':origin,'version':version,'state':state,'hash':checksum,'description':description})
    if errors:
        raise RuntimeError('扫描未完整完成，未写入变更记录。\n'+'\n'.join(errors[:8]))
    result={}
    for identity,copies in grouped.items():
        copies.sort(key=lambda c:c['path'])
        states={c['state'] for c in copies}
        state='已登记' if '已登记' in states else ('配置停用' if '配置停用' in states else '缓存待核对')
        ref=reference.get(copies[0]['skill_name'],{})
        result[identity]={'name':identity,**{k:copies[0][k] for k in ('skill_name','scope_id','scope_label','scope_path','scope_kind')},'state':state,'purpose':ref.get('purpose') or copies[0]['description'],
            'origin':' ; '.join(sorted({c['origin'] for c in copies})),'version':' ; '.join(sorted({c['version'] for c in copies if c['version']})),
            'paths':[c['path'] for c in copies],'copies':len(copies),
            'fingerprint':hashlib.sha256(json.dumps([(c['path'],c['hash'],c['state']) for c in copies],ensure_ascii=False).encode()).hexdigest()}
    return result

def changes(previous,current,stamp):
    events=[]
    for name in sorted(previous.keys()|current.keys()):
        old,new=previous.get(name),current.get(name)
        if old is None:
            action='新增';detail='首次检测到；状态：'+new['state']
        elif new is None:
            action='移除';detail='本次扫描不再发现原有技能定义；此前状态：'+old['state']
        elif all(old.get(k)==new.get(k) for k in ('state','version','paths','purpose','copies')) and (old.get('origin')==new.get('origin') or old.get('_scope_migrated')) and (old.get('fingerprint')==new.get('fingerprint') or old.get('_scope_migrated')): continue
        else:
            notes=[]
            if old['state']!=new['state']: notes.append('状态：'+old['state']+' → '+new['state'])
            if old['version']!=new['version']: notes.append('版本：'+old['version']+' → '+new['version'])
            if old['paths']!=new['paths']: notes.append('路径或副本数量变化')
            if old['fingerprint']!=new['fingerprint'] and not notes: notes.append('SKILL.md 内容变化')
            if not notes: notes.append('说明或登记信息变化')
            action='新增' if old['state']=='缓存待核对' and new['state']!='缓存待核对' else ('停用' if old['state']!='配置停用' and new['state']=='配置停用' else ('启用' if old['state']=='配置停用' and new['state']=='已登记' else '变更'))
            detail='；'.join(notes)
        events.append({'time':stamp,'action':action,'name':name,'detail':detail,'evidence':'本机文件及配置对比','skill':new or old,'time_kind':'detected','detected_at':stamp})
    return events

def safe_cell(value):
    value=str(value)
    return "'"+value if value[:1] in '=+-@\t\r\n' else value

def write_csv(path,fields,rows):
    stream=io.StringIO(newline='');writer=csv.writer(stream);writer.writerow(fields)
    writer.writerows([[safe_cell(c) for c in row] for row in rows])
    atomic_write(path,'\ufeff'+stream.getvalue())

def operation_log(events,reference):
    """Keep observation times distinct from known operation times and imported records."""
    projected=[]
    for index,event in enumerate(events):
        raw=event.copy();evidence=raw.get('evidence','');action=raw['action']
        if raw.get('occurred_at'):
            kind='operation';caption='操作时间';stamp=raw['occurred_at']
        elif raw.get('time_kind')=='imported' or evidence.startswith('历史导入'):
            kind='recorded';caption='记录时间';stamp=raw['time']
        else:
            kind='detected';caption='检测时间';stamp=raw.get('detected_at',raw['time'])
        label=({'新增':'发现新增','移除':'发现移除','启用':'检测到启用','停用':'检测到停用','变更':'检测到变更'}.get(action,action) if kind=='detected' else ('卸载' if action=='归档' else action))
        detail=raw.get('detail','').replace('已登记','已启用').replace('配置停用','已停用')
        if kind=='recorded':
            detail={'归档':'已移出技能目录，文件保留用于恢复。','卸载':'已确认卸载。','停用':'已关闭该技能的启用配置。'}.get(action,detail)
        elif action=='新增':
            if '缓存待核对' in raw.get('detail',''):
                label='确认安装';detail='首次确认该技能已安装；此前仅识别到缓存，实际安装时间未确认。'
            else:detail='首次检测到该技能文件；实际安装时间未确认。'
        elif action=='移除':detail='本次检查不再发现原技能文件；未确认具体移除方式。'
        identity=hashlib.sha256(json.dumps([index,raw['name'],raw['time'],action],ensure_ascii=False).encode()).hexdigest()[:20]
        projected.append({**raw,'id':identity,'time':stamp,'recorded_at':raw['time'],'time_kind':kind,'time_label':caption,'action_label':label,
            'category':reference.get(raw['name'],{}).get('category','未分类'),'description':detail})
    return projected

def registry(ledger,reference):
    """Present current skills and known removed skills without treating caches as installs."""
    snapshot=ledger['snapshot']; latest={}; metadata={}
    known={name for name,row in snapshot.items() if row['state']!='缓存待核对'}
    for event in ledger['events']:
        if event.get('skill',{}).get('state')=='缓存待核对':continue
        name=event['name'];latest[name]=event
        if event.get('skill'):
            metadata[name]=event['skill']
            if event['skill']['state']!='缓存待核对':known.add(name)
        if event['action'] in ('安装','归档','卸载','停用','启用'):known.add(name)
    result=[]
    for name in sorted(known):
        current=snapshot.get(name);last=latest.get(name,{})
        ref=reference.get(skill_scope.canonical(name),{})
        if current and current['state']!='缓存待核对':
            status='已停用' if current['state']=='配置停用' else '已启用'
            item=current
        else:
            action=last.get('action')
            if action=='归档':status='已归档'
            elif action=='卸载':status='已卸载'
            elif action=='移除':status='已移除'
            else:status='未发现'
            item=metadata.get(name,{})
        origin=item.get('origin') or ref.get('origin','')
        if ':' in name:
            source={'chatcut':'ChatCut','google-drive':'Google Drive','pages':'Pages','heygen':'HeyGen','data-analytics':'Data','sites':'Sites','visualize':'Visualize','work-pets':'Pets','vercel':'Vercel','github':'GitHub','slack':'Slack','hyperframes':'HyperFrames','documents':'Word 文档','pdf':'PDF','presentations':'演示文稿','spreadsheets':'电子表格','template-creator':'模板创建器','computer-use':'电脑操作'}.get(name.split(':',1)[0],name.split(':',1)[0])
        elif any('/.system/' in p.replace('\\','/') for p in item.get('paths',ref.get('paths',[]))):source='Codex 内置'
        else:source='本地技能'
        related=[e for e in ledger['events'] if e['name']==name and e.get('skill',{}).get('state')!='缓存待核对']
        installed=[e for e in related if e['action'] in ('安装','新增') and e.get('occurred_at')]
        discovered=[e for e in related if e['action']=='新增' and not e.get('occurred_at')]
        lifecycle={'installed_at':installed[-1]['occurred_at'] if installed else '',
            'first_detected_at':discovered[0].get('detected_at',discovered[0]['time']) if discovered else '',
            'present_at_baseline':bool(current and current['state']!='缓存待核对' and not installed and not discovered)}
        result.append({'name':name,'category':ref.get('category','未分类'),'status':status,
            'purpose':item.get('purpose') or ref.get('purpose',''),'source':source,'origin':origin,
            'version':item.get('version',''),'paths':item.get('paths') or ref.get('paths',[]),
            'copies':item.get('copies',0),'archive_paths':ref.get('archive_paths',''),'recovery_paths':[r['backup'] for r in last.get('recovery',[])],
            'changed':last.get('time',''),'last_action':last.get('action',''),'lifecycle':lifecycle})
    return result

USAGE_EXAMPLES={
    'to-spec':'把以下讨论整理成可执行的规格说明，列出范围、约束和验收条件：\n【讨论记录或需求素材】',
    'edit-article':'重组并精简下面的文章草稿，先说明修改思路：\n【文章草稿和修改目标】',
    'writing-beats':'把以下素材组织成有节奏和铺垫的文章结构：\n【素材、主题和目标读者】',
    'writing-fragments':'从以下资料中挖掘适合写作的片段和观点：\n【原始资料和写作主题】',
    'copy-editing':'润色下面这段文案，保持原意，并说明关键修改：\n【粘贴文案】',
    'brand-storytelling':'根据以下背景整理品牌定位与品牌故事：\n【品牌、受众、产品和优势】',
    'imagegen':'生成一张图片：\n【画面内容、风格、尺寸和用途】',
    'openai-docs':'核对 Codex 的以下功能怎么使用，并给出官方依据：\n【具体问题】',
    'skill-creator':'把以下工作流程整理成可复用技能：\n【触发场景、步骤和输出要求】',
    'skill-installer':'查找以下技能的可靠安装来源，先展示安装方案：\n【技能名称或 GitHub 地址】',
    'find-skills':'查找适合以下任务的技能，先比较用途与安装来源：\n【任务描述】',
    'douyin':'获取这个抖音链接的视频信息并下载视频：\n【抖音分享链接】',
    'douyin-video':'提取这个抖音视频的语音文案：\n【抖音分享链接】',
    'xiaohongshu':'搜索并分析以下主题的小红书笔记：\n【主题、时间范围和分析目标】',
    'xiaohongshu-note-analyzer':'审核这篇小红书笔记，给出标题和正文修改建议：\n【标题、正文和配图说明】',
    'obsidian-vault':'在我的 Obsidian 笔记库中整理以下主题的笔记与双向链接：\n【笔记库位置和主题】',
    'khazix-writer':'根据以下素材撰写公众号文章：\n【素材、主题、读者和篇幅】',
    'writing-shape':'把以下笔记组织成文章，先讨论开头和结构：\n【原始素材】',
    'video-marketing':'为以下产品设计短视频脚本和开头：\n【产品、受众、平台和时长】',
    'chatcut:asset-import':'把以下本地视频导入指定 ChatCut 项目：\n【项目名称和素材文件路径】',
    'chatcut:talking-head-guide':'剪辑这段口播，去除重复和多余停顿：\n【项目或视频素材及剪辑要求】',
    'chatcut:transcription':'转写这段视频并整理字幕：\n【项目或音视频素材】',
    'chatcut:voice':'根据以下文字制作配音，先确认声音和语速：\n【配音文案和声音要求】',
    'chatcut:music':'为以下视频制作配乐，先确认纯音乐或带人声：\n【视频用途、时长和音乐风格】',
    'chatcut:export':'导出指定 ChatCut 项目，先核对成片与导出参数：\n【项目名称、分辨率和格式】',
    'chatcut:video-gen':'生成一个视频片段：\n【画面、动作、风格、时长和比例】',
    'google-drive:google-drive':'在已连接的 Google Drive 中查找以下资料并整理摘要：\n【关键词或文件链接】',
    'google-drive:google-docs':'根据以下资料创建或修改 Google 文档：\n【资料、文档链接或新文档要求】',
    'google-drive:google-sheets':'分析这个 Google 表格，说明指标口径与结果：\n【表格链接、工作表和分析问题】',
    'google-drive:google-slides':'沿用这个 Google 幻灯片的风格修改内容：\n【演示文稿链接和修改要求】',
    'google-drive:google-drive-comments':'根据以下问题草拟文档评论，先展示草稿：\n【文档链接、位置和评论要求】',
    'github:gh-fix-ci':'排查这个 PR 的失败检查，说明原因和修复方案：\n【仓库或 PR 链接】',
    'github:gh-address-comments':'整理这个 PR 的审查意见，并逐条处理可修复的问题：\n【PR 链接】',
    'github:yeet':'检查当前改动是否适合提交，先展示拟提交范围和草稿 PR 内容。',
    'documents:documents':'根据以下内容制作 Word 文档：\n【内容、版式要求和保存位置】',
    'pdf:pdf':'读取这个 PDF 并按要求整理内容：\n【本地 PDF 路径和具体任务】',
    'presentations:Presentations':'制作一份演示文稿：\n【主题、受众、页数和参考材料】',
    'spreadsheets:Spreadsheets':'分析这份本地表格并整理结果：\n【Excel 或 CSV 路径及分析问题】',
    'spreadsheets:excel-live-control':'操作当前打开的 Excel 工作簿，先核对连接与目标区域：\n【工作簿名称和操作要求】',
    'sites:sites':'制作一个网站，先确认页面和内容：\n【网站用途、受众、页面和风格】',
    'plugin-management:plugin-management':'查找适合以下用途的插件，比较功能、权限和依赖：\n【任务需求】',
    'computer-use:computer-use':'在我的电脑上完成以下应用操作，先确认目标窗口：\n【应用名称和操作任务】',
    'heygen:heygen-workflows':'制作一段数字人口播视频，先确认人物和声音：\n【文案、时长、比例和素材】',
    'slack:slack-outgoing-message':'起草以下 Slack 消息，先展示草稿供我确认：\n【收件人或频道、背景和要点】',
    'slack:slack-reply-drafting':'根据上下文起草这条 Slack 消息的回复，先展示草稿：\n【消息链接和回复目标】',
}

def usage_info(row):
    name=row.get('skill_name',row['name']);task=USAGE_EXAMPLES.get(name)
    if not task:
        purpose=re.sub(r'\s+',' ',row.get('purpose','')).strip().rstrip('。.!！')[:160]
        task=('根据我提供的材料，'+purpose+'。\n【粘贴相关材料和具体要求】') if purpose else '处理以下任务，先说明需要的材料：\n【任务和输入材料】'
    note='先安装该技能，再使用下方示例。' if not row['installed'] else ('先在 Codex 中开启该技能的启用设置。' if row['status']=='已停用' else '')
    connection='涉及外部服务时，按 Codex 提示完成账号连接和授权。' if name.split(':')[0] in ('chatcut','google-drive','github','slack','heygen','xiaohongshu') else ''
    leaf=name.split(':',1)[-1]
    return {'usage':'/'+leaf+' '+task,'usage_auto':task,'usage_note':note,'usage_connection':connection,
        'usage_desktop_hint':'在 Codex 桌面端输入 /，从菜单选择「'+name+'」，再填写任务；同名技能按所属插件或路径区分。',
        'usage_cli_hint':'CLI / IDE 请通过 /skills 选择技能，或使用客户端支持的 $技能名 显式引用；不要把桌面端 /技能名 示例直接当作终端命令。'}

def export(base,ledger):
    import skill_manager as management
    import skill_invocation as invocation
    reference=read_json(base/'.data'/'reference.json')
    skills=registry(ledger,reference)
    settings=management.configured(base)
    for row in skills:
        row['skill_name']=row.get('skill_name') or skill_scope.canonical(row['name'])
        record=ledger['snapshot'].get(row['name']) or next((e.get('skill',{}) for e in reversed(ledger['events']) if e['name']==row['name']),{})
        info={k:record[k] for k in ('scope_id','scope_label','scope_path','scope_kind') if k in record}
        if not info:info=skill_scope.scope_for(row['paths'][0],settings) if row['paths'] and ':' not in row['name'] else {'scope_id':'global','scope_label':'全局技能','scope_path':'','scope_kind':'global'}
        row.update(info);row['topic']=row['category']
        row['management']=management.capability(ledger['snapshot'].get(row['name']),settings)
        row['installed']=row['status'] in ('已启用','已停用')
        row['display_status']='已安装' if row['installed'] else '已卸载'
        row.update(usage_info(row))
        row['invocation']=invocation.invocation_info(row,frontmatter)
        if ':' in row['name']:
            origins=row['origin'].split(' ; ')
            builtin='Codex 内置' in row['management'].get('reason','') or any(origin.endswith(('@openai-bundled','@openai-primary-runtime')) or origin in ('sites@openai-curated-remote','work-pets@openai-curated-remote') for origin in origins)
            row['source_type']='Codex 内置组件' if builtin else '插件附带'
            row['source_detail']='由「'+row['source']+'」插件提供；安装来源标识：'+row['origin']+'。此列不表示作者或下载网址。'
        elif row['source']=='Codex 内置':
            row['source_type']='内置技能';row['source_detail']='随 Codex 提供的内置技能；本地文件位置请查看详情。'
        else:
            row['source_type']='独立安装';row['source_detail']='独立安装在本机技能目录中；原始作者和下载网址未记录。'
    events=operation_log(ledger['events'],reference)
    by_name={r['name']:r for r in skills}
    for event in events:
        if event['name'] in by_name:
            owner=by_name[event['name']]
            event.update({k:owner.get(k,'') for k in ('skill_name','scope_id','scope_label','scope_path','scope_kind')})
    known={r['name'] for r in skills}
    visible_events=[e for e in events if e['name'] in known]
    discovery=skill_scope.discovery_info(base,settings)
    revision=hashlib.sha256(json.dumps([skills,visible_events,discovery['roots'],discovery['scopes'],discovery['warnings']],ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:20]
    data=json.dumps({'updated':ledger['last_scan'],'revision':revision,'skills':skills,'events':visible_events,'discovery':discovery},ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    template_path=base/'查看记录.template.html'
    if template_path.exists():
        template=template_path.read_text(encoding='utf-8')
    else:
        template=(HERE/'web'/'viewer.template.html').read_text(encoding='utf-8').replace('__APP__',(HERE/'web'/'app.js').read_text(encoding='utf-8'))
    atomic_write(base/'查看记录.html',template.replace('__DATA__',data))
    atomic_write(base/'.data'/'live-data.js','window.SkillLedgerReceive && window.SkillLedgerReceive('+data+');\n')
    # An open CSV must not prevent the live page from receiving fresh data.
    warnings=[]
    for filename,fields,rows in [
        ('当前技能.csv',FIELDS,[[r['skill_name'],r.get('scope_label','全局技能'),r['display_status'],r['purpose'],r['invocation']['label'],'\n'.join(filter(None,[r['usage_note'],r['usage_desktop_hint'],r['usage']])),r['source'],r['version'],r['copies'],' ; '.join(r['paths'])] for r in skills]),
        ('变更记录.csv',HISTORY_FIELDS,[[e['time'],e['time_label'],e['action_label'],e.get('skill_name',e['name']),e.get('scope_label','全局技能'),e['description'],e.get('evidence','')] for e in visible_events])]:
        try:write_csv(base/filename,fields,rows)
        except OSError as error:warnings.append(filename+': '+str(error))
    atomic_write(base/'.data'/'export-status.json',json.dumps({'warnings':warnings},ensure_ascii=False))

def update(base,verbose=True):
    with locked(base):
        from skill_setup import ensure
        ensure(base)
        import skill_manager as management
        settings=management.configured(base);reference=read_json(base/'.data'/'reference.json')
        store=base/'.data'/'ledger.json';existing=read_json(store) if store.exists() else None
        if existing:existing=skill_scope.migrate(existing,settings)
        stamp=now();snapshot=scan(settings,reference)
        if existing:
            events=changes(existing['snapshot'],snapshot,stamp)
            ledger={**existing,'snapshot':snapshot,'events':existing['events']+events,'last_scan':stamp}
        else:
            imported=read_json(base/'.data'/'历史导入.json')
            events=[];ledger={'schema':1,'scope_schema':1,'created':stamp,'last_scan':stamp,'snapshot':snapshot,'events':imported,
                'baseline_note':'初次扫描为登记基线，不推测历史安装时间。'}
        # One atomic authoritative file commits snapshot and events together.
        atomic_write(store,json.dumps(ledger,ensure_ascii=False,indent=2))
        export(base,ledger)
        counts={state:sum(r['state']==state for r in snapshot.values()) for state in ('已登记','配置停用','缓存待核对')}
        if verbose and sys.stdout:
            print(f"更新完成：已安装 {counts['已登记']+counts['配置停用']}；新增记录 {len(events)} 条。",flush=True)
        return {'new_events':len(events),'counts':counts,'history':len(ledger['events'])}

def main():
    parser=argparse.ArgumentParser(description='更新本机 Skill 清单和增删记录；不修改任何技能或 Codex 配置。')
    parser.add_argument('--base',type=Path,default=HERE)
    parser.add_argument('--open',action='store_true',help='更新后打开记录页面')
    parser.add_argument('--watch',action='store_true',help='保持运行，每 15 秒扫描一次；Ctrl+C 停止')
    parser.add_argument('--quiet',action='store_true',help='后台运行时不输出普通状态')
    args=parser.parse_args();base=args.base.resolve()
    from skill_setup import ensure
    ensure(base)
    def iteration():
        try:
            result=update(base,verbose=not args.quiet)
            if args.watch:
                atomic_write(base/'.data'/'monitor.json',json.dumps({'pid':os.getpid(),'last_scan':now(),'status':'正常','new_events':result['new_events']},ensure_ascii=False))
        except Exception as error:
            if '另一个更新正在进行' in str(error):return True
            message=now()+' '+str(error)
            if sys.stderr: print(message,file=sys.stderr,flush=True)
            error_path=base/'.data'/'运行错误.log'
            if error_path.exists() and error_path.stat().st_size>1024*1024:
                os.replace(error_path,error_path.with_suffix('.previous.log'))
            with (base/'.data'/'运行错误.log').open('a',encoding='utf-8') as f: f.write(message+'\n')
            if args.watch:
                atomic_write(base/'.data'/'monitor.json',json.dumps({'pid':os.getpid(),'last_scan':now(),'status':'扫描失败，未生成移除记录','error':str(error)},ensure_ascii=False))
            return False
        if args.open:
            connection=base/'.data'/'connection.json'
            if connection.exists():
                link=read_json(connection);webbrowser.open(link['url']+'/#access='+link['token'])
            else:webbrowser.open((base/'查看记录.html').as_uri())
            args.open=False
        return True
    if not args.watch: return 0 if iteration() else 1
    try:
        with locked(base,'monitor.lock'):
            import skill_manager as management
            management.serve(base)
            while True:
                iteration();time.sleep(15)
    except RuntimeError as error:
        if '另一个更新正在进行' not in str(error): raise
        if args.open:
            connection=base/'.data'/'connection.json'
            if connection.exists():
                link=read_json(connection);webbrowser.open(link['url']+'/#access='+link['token'])
        if not args.quiet and sys.stdout: print('后台记录器已经运行。')
    return 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except KeyboardInterrupt: print('已停止自动扫描，已有记录保留。')
