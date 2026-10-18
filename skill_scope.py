"""Directory-based scope and bounded discovery; never read skill instructions."""
import hashlib
import json
import os
from pathlib import Path
import time

SKIP={'.git','.agents','.agent','.codex','.data','.venv','venv','node_modules','__pycache__','dist','build','target','vendor','outputs','logs','tmp','temp','work','sources','archive','backup','backups','artifacts','invoke-data','site-packages','$RECYCLE.BIN','System Volume Information'}

def key(path):
    return os.path.normcase(os.path.abspath(str(path))).replace('\\','/')

def describe_root(entry,settings):
    root=Path(entry['path']).absolute()
    globals_={key(Path.home()/'.agents'/'skills'),key(Path(settings['codex_config']).parent/'skills')}
    project=entry.get('scope')=='project' or (entry.get('scope')!='global' and root.parent.name in ('.agents','.codex') and key(root) not in globals_)
    if not project:return {'scope_id':'global','scope_label':'全局技能','scope_path':'','scope_kind':'global'}
    owner=Path(entry.get('project_path') or root.parent.parent).absolute()
    identity='project-'+hashlib.sha256(key(owner).encode()).hexdigest()[:12]
    return {'scope_id':identity,'scope_label':entry.get('project_label') or owner.name,'scope_path':str(owner),'scope_kind':'project'}

def scope_for(path,settings):
    p=Path(path).absolute()
    candidates=[e for e in settings['skill_roots'] if p.is_relative_to(Path(e['path']).absolute())]
    if not candidates:return {'scope_id':'global','scope_label':'全局技能','scope_path':'','scope_kind':'global'}
    return describe_root(max(candidates,key=lambda e:len(key(e['path']))),settings)

def identity(name,scope):
    return name if scope['scope_id']=='global' else name+'@@'+scope['scope_id']

def canonical(name):return name.split('@@project-',1)[0]

def write(path,value):
    from skill_setup import write_json
    write_json(path,value)

def discover(base,settings,force=False):
    cache=base/'.data'/'project-discovery.json'
    previous=json.loads(cache.read_text(encoding='utf-8')) if cache.exists() else {}
    roots=settings.get('project_scan_roots',[])
    signature=json.dumps(roots,sort_keys=True)
    if not force and previous.get('signature')==signature and time.time()-previous.get('checked_epoch',0)<30:
        result=previous
    else:
        found={key(e['path']):e for e in previous.get('skill_roots',[])}
        projects={key(p['path']):p for p in previous.get('projects',[])}
        warnings=[];fatal=[];visited=set();total=0;depth_limited=0
        for raw in roots:
            entry={'path':raw} if isinstance(raw,str) else raw
            start=Path(entry['path']).absolute()
            if not start.is_dir():
                warnings.append('扫描目录不可访问：'+str(start))
                if any(Path(e['path']).is_relative_to(start) for e in found.values()):fatal.append(str(start))
                continue
            stack=[(start,0)]
            if not entry.get('collection'):projects[key(start)]={'path':str(start),'label':entry.get('label') or start.name}
            while stack:
                folder,depth=stack.pop();marker=key(folder)
                if marker in visited:continue
                visited.add(marker);total+=1
                if total>20000:
                    warnings.append('目录数量超过 20000，请缩小扫描范围。');stack.clear();break
                skillroot=folder/'.agents'/'skills'
                if skillroot.is_dir():
                    project={'path':str(folder),'label':(entry.get('label') or folder.name) if folder==start else folder.name}
                    projects[key(folder)]=project
                    found[key(skillroot)]={'path':str(skillroot),'label':'项目技能','required':False,'scope':'project','project_path':str(folder),'project_label':project['label']}
                if depth>=int(settings.get('project_scan_depth',6)):
                    try:
                        if any(p.is_dir() and p.name not in SKIP for p in folder.iterdir()):depth_limited+=1
                    except OSError:warnings.append('子目录不可访问：'+str(folder))
                    continue
                try:
                    children=list(folder.iterdir())
                    for child in children:
                        if child.name in SKIP or child.name.startswith('.') or child.is_symlink() or getattr(child,'is_junction',lambda:False)():continue
                        if child.is_dir():stack.append((child,depth+1))
                except OSError:
                    warnings.append('子目录不可访问：'+str(folder))
                    if any(Path(e['path']).is_relative_to(folder) for e in found.values()):fatal.append(str(folder))
        if depth_limited:warnings.append(str(depth_limited)+' 个子目录达到深度上限；更深的项目请直接添加为扫描范围。')
        shown_warnings=warnings[:20]+(['另有 '+str(len(warnings)-20)+' 项提示；请缩小扫描范围或添加更具体的项目目录。'] if len(warnings)>20 else [])
        result={'signature':signature,'checked_epoch':time.time(),'skill_roots':list(found.values()),'projects':list(projects.values()),'warnings':shown_warnings,'fatal':fatal,'directories_checked':total}
        write(cache,result)
    # Incomplete discovery cannot turn known installs into removals.
    if result.get('fatal'):
        raise RuntimeError('已知项目扫描目录不可访问，保留原台账：'+result['fatal'][0])
    combined={key(e['path']):dict(e) for e in settings['skill_roots']}
    for entry in result.get('skill_roots',[]):combined.setdefault(key(entry['path']),entry)
    settings={**settings,'skill_roots':list(combined.values())}
    return settings

def discovery_info(base,settings):
    path=base/'.data'/'project-discovery.json'
    cached=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    scopes={'global':{'scope_id':'global','scope_label':'全局技能','scope_path':'','scope_kind':'global'}}
    for entry in settings['skill_roots']:
        info=describe_root(entry,settings)
        if info['scope_kind']=='global' or Path(entry['path']).exists():scopes[info['scope_id']]=info
    for project in cached.get('projects',[]):
        info=describe_root({'path':str(Path(project['path'])/'.agents'/'skills'),'scope':'project','project_label':project['label']},settings)
        scopes.setdefault(info['scope_id'],info)
    return {'roots':settings.get('project_scan_roots',[]),'checked_epoch':cached.get('checked_epoch'),'scopes':list(scopes.values()),'warnings':cached.get('warnings',[]),'depth':int(settings.get('project_scan_depth',6))}

def invalidate(base):
    path=base/'.data'/'project-discovery.json'
    if path.exists():
        value=json.loads(path.read_text(encoding='utf-8'));value['checked_epoch']=0;write(path,value)

def add_project(base,path,collection=False):
    from skill_ledger import read_json
    folder=Path(path)
    if not folder.is_absolute() or str(path).startswith(('\\\\','//')) or not folder.is_dir() or folder.parent==folder:
        raise ValueError('请输入存在的本地项目文件夹绝对路径；不能使用整个磁盘或网络路径。')
    settings=read_json(base/'设置.json');roots=settings.setdefault('project_scan_roots',[])
    if not isinstance(collection,bool):raise ValueError('项目集合选项无效。')
    if not any(key(e if isinstance(e,str) else e['path'])==key(folder) for e in roots):roots.append({'path':str(folder),'label':folder.name,'collection':collection})
    write(base/'设置.json',settings);invalidate(base)

def migrate(ledger,settings):
    if ledger.get('scope_schema')==1:return ledger
    def split(row,name):
        canonical_name=row.get('skill_name') or canonical(name);groups={}
        for path in row.get('paths',[]):
            scope=scope_for(path,settings) if ':' not in canonical_name else {'scope_id':'global','scope_label':'全局技能','scope_path':'','scope_kind':'global'}
            ident=identity(canonical_name,scope)
            if ident not in groups:groups[ident]={**row,**scope,'name':ident,'skill_name':canonical_name,'paths':[],'_scope_migrated':True}
            groups[ident]['paths'].append(path)
        for value in groups.values():value['copies']=len(value['paths'])
        return groups or {name:{**row,'skill_name':canonical_name}}
    snapshot={}
    for name,row in ledger['snapshot'].items():snapshot.update(split(row,name))
    events=[]
    for event in ledger['events']:
        if event.get('skill'):
            for name,row in split(event['skill'],event['name']).items():events.append({**event,'name':name,'skill':row})
        else:events.append(event)
    return {**ledger,'snapshot':snapshot,'events':events,'scope_schema':1}
