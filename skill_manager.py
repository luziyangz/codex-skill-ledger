"""Loopback-only skill management. Names resolve to freshly checked local paths."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import threading
import time
from urllib.parse import urlsplit

import skill_ledger as L

def run_cli(settings,args,timeout=40):
    cli=Path(settings.get('plugin_cli',''))
    if not cli.is_file(): raise RuntimeError('没有可用的 Codex 插件管理程序。')
    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    result=subprocess.run([str(cli),'plugin',*args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,creationflags=creationflags)
    if result.returncode:raise RuntimeError((result.stderr or result.stdout)[-1000:].strip() or 'Codex 插件操作失败。')
    return json.loads(result.stdout),result.stderr

def refresh_catalog(base):
    settings=L.read_json(base/'设置.json')
    try:
        result,warning=run_cli(settings,['list','--json'],timeout=25)
        installed=result.get('installed')
        if not isinstance(installed,list):raise ValueError('无法识别插件安装清单。')
        rows=[{'id':r['pluginId'],'name':r['name'],'enabled':r.get('enabled',True)} for r in installed if r.get('installed')]
        complete=not bool(warning.strip());catalog_path=base/'.data'/'installed-plugins.json'
        previous=L.read_json(catalog_path) if catalog_path.exists() else {}
        if not complete:
            # A partial remote response cannot revoke previously confirmed installations.
            merged={r['id']:r for r in previous.get('installed',[])}
            merged.update({r['id']:r for r in rows});rows=list(merged.values())
        stamp=L.now()
        L.atomic_write(catalog_path,json.dumps({'updated':stamp,'complete':complete,'last_complete':stamp if complete else previous.get('last_complete',previous.get('updated') if previous.get('complete') else None),'installed':rows},ensure_ascii=False))
    except Exception as error:
        L.atomic_write(base/'.data'/'catalog-status.json',json.dumps({'time':L.now(),'error':str(error)},ensure_ascii=False))

def configured(base):
    settings=L.read_json(base/'设置.json');path=base/'.data'/'installed-plugins.json'
    if path.exists():
        catalog=L.read_json(path)
        settings['known_plugins']=sorted(set(settings.get('known_plugins',[]))|{r['name'] for r in catalog.get('installed',[])})
        settings['plugin_ids']={r['id'] for r in catalog.get('installed',[])}
    return settings

def capability(row,settings):
    if not row or row.get('state')=='缓存待核对':return {'kind':'none','reason':'当前未安装，无需卸载。'}
    paths=[Path(p) for p in row.get('paths',[])]
    if any('.system' in p.parts for p in paths):return {'kind':'none','reason':'Codex 内置技能，请在 Codex 中管理。'}
    if ':' in row['name']:
        origins=row.get('origin','').split(' ; ')
        if len(origins)!=1 or '@' not in origins[0]:return {'kind':'none','reason':'无法确认所属插件。'}
        origin=origins[0]
        if origin.endswith(('@openai-bundled','@openai-primary-runtime')) or origin in ('sites@openai-curated-remote','work-pets@openai-curated-remote'):
            return {'kind':'none','reason':'Codex 内置组件，不支持在此卸载；启用开关不影响其已安装状态。'}
        if not Path(settings.get('plugin_cli','')).is_file():return {'kind':'none','reason':'没有可用的插件管理程序。'}
        return {'kind':'plugin','plugin':origin,'label':'卸载所属插件'}
    roots=[Path(e['path']).absolute() for e in settings['skill_roots']]
    for p in paths:
        parent=p.parent.absolute()
        if p.name!='SKILL.md' or not any(parent!=r and parent.is_relative_to(r) for r in roots):
            return {'kind':'none','reason':'技能不在允许管理的目录内。'}
        if getattr(parent,'is_junction',lambda:False)():
            return {'kind':'none','reason':'目录是 Windows 联接，请在原安装位置管理。'}
        if not parent.is_symlink() and not any(parent.resolve().is_relative_to(r.resolve()) and parent.resolve()!=r.resolve() for r in roots):
            return {'kind':'none','reason':'实际目录超出允许管理范围。'}
    return {'kind':'local','label':'卸载'} if paths else {'kind':'none','reason':'未找到技能文件。'}

def digest(snapshot):return hashlib.sha256(json.dumps(snapshot,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

class Manager:
    def __init__(self,base):self.base=base;self.plans={};self.completed={};self.mutex=threading.Lock()
    def preview(self,names):
        if not isinstance(names,list) or not names or len(names)>500 or any(not isinstance(n,str) for n in names):raise ValueError('请选择要卸载的技能。')
        with L.locked(self.base):
            settings=configured(self.base);reference=L.read_json(self.base/'.data'/'reference.json');snapshot=L.scan(settings,reference)
            groups={};blocked=[]
            for name in dict.fromkeys(names):
                row=snapshot.get(name);cap=capability(row,settings)
                if cap['kind']=='none':blocked.append({'name':name,'reason':cap['reason']});continue
                key=cap.get('plugin') or name
                if key in groups:continue
                if cap['kind']=='plugin':
                    affected=sorted(n for n,r in snapshot.items() if r['origin']==key and r['state']!='缓存待核对')
                    groups[key]={'kind':'plugin','key':key,'names':affected,'paths':[]}
                else:
                    paths=sorted({str(Path(p).parent.absolute()) for p in row['paths']})
                    # A package can contain child skills; reveal all affected names before committing.
                    affected=sorted(n for n,r in snapshot.items() if any(Path(p).absolute().is_relative_to(Path(d)) for p in r['paths'] for d in paths))
                    groups[key]={'kind':'local','key':key,'names':affected,'paths':paths}
            values=list(groups.values())
            values=[g for g in values if g['kind']!='local' or not any(other is not g and other['kind']=='local' and all(any(Path(p)!=Path(q) and Path(p).is_relative_to(Path(q)) for q in other['paths']) for p in g['paths']) for other in values)]
            valid=[]
            for group in values:
                protected=[n for n in group['names'] if capability(snapshot[n],settings)['kind']=='none']
                if protected:
                    blocked.extend({'name':n,'reason':'所在目录包含受保护的技能，不能整体移除。'} for n in names if n in group['names'])
                else:valid.append(group)
            plan={'id':secrets.token_urlsafe(24),'created':time.time(),'fingerprint':digest(snapshot),'groups':valid,'blocked':blocked,'selected_names':list(dict.fromkeys(names))}
            self.plans={k:v for k,v in self.plans.items() if time.time()-v['created']<300};self.plans[plan['id']]=plan
            return self.public(plan)
    def public(self,plan):
        affected=sorted({n for g in plan['groups'] for n in g['names']});selected=plan.get('selected_names',[])
        return {'id':plan['id'],'groups':[{'kind':g['kind'],'key':g['key'],'names':g['names']} for g in plan['groups']],'blocked':plan['blocked'],
                'selected_names':selected,'affected_names':affected,'extra_names':[n for n in affected if n not in selected],'count':len(affected)}
    def commit(self,plan_id):
        with self.mutex,L.locked(self.base):
            if plan_id in self.completed:return self.completed[plan_id]
            plan=self.plans.pop(plan_id,None)
            if not plan or time.time()-plan['created']>300:raise ValueError('确认已过期，请重新选择。')
            settings=configured(self.base);ref=L.read_json(self.base/'.data'/'reference.json');before=L.scan(settings,ref)
            if digest(before)!=plan['fingerprint']:raise ValueError('技能已发生变化，请重新检查卸载范围。')
            store=L.read_json(self.base/'.data'/'ledger.json');results=[];operations=[]
            backup=self.base/'.data'/'uninstall-backups'/secrets.token_hex(12)
            for group in plan['groups']:
                moved=[]
                try:
                    if group['kind']=='local':
                        # All paths originate in a fresh server-side scan, never in a client request.
                        for index,source in enumerate(group['paths']):
                            target=Path(source)
                            if not target.exists() and not target.is_symlink():continue
                            for name in group['names']:
                                if name in before and capability(before[name],settings)['kind']=='none':raise RuntimeError('卸载目录包含受保护的技能。')
                            destination=backup/(str(len(results))+'-'+str(index))
                            if not destination.resolve().is_relative_to((self.base/'.data'/'uninstall-backups').resolve()):raise RuntimeError('恢复目录校验失败。')
                            destination.parent.mkdir(parents=True,exist_ok=True)
                            L.atomic_write(backup/'transaction.json',json.dumps({'group':group,'completed_moves':moved,'next_move':{'from':str(target),'backup':str(destination)}},ensure_ascii=False,indent=2))
                            shutil.move(str(target),str(destination));moved.append({'from':str(target),'backup':str(destination)})
                    else:
                        run_cli(settings,['remove',group['key'],'--json'],timeout=50)
                    after=L.scan(settings,ref)
                    still=[n for n in group['names'] if n in after and after[n]['state']!='缓存待核对']
                    if still:raise RuntimeError('卸载后仍可发现技能：'+', '.join(still))
                    stamp=L.now()
                    for name in group['names']:
                        operations.append({'time':stamp,'occurred_at':stamp,'action':'卸载','name':name,'detail':'本地技能已移出加载目录，保留恢复备份。' if moved else '已通过 Codex 卸载所属插件。','evidence':'技能台账：用户确认卸载','skill':before[name],'recovery':moved})
                    results.append({'key':group['key'],'names':group['names'],'ok':True})
                except Exception as error:
                    rollback=[]
                    for item in reversed(moved):
                        try:
                            if Path(item['from']).exists():raise RuntimeError('原位置已存在文件')
                            shutil.move(item['backup'],item['from'])
                        except Exception as restore_error:rollback.append(str(restore_error))
                    results.append({'key':group['key'],'names':group['names'],'ok':False,'error':str(error)+('；恢复失败：'+'；'.join(rollback) if rollback else '')})
                # Persist each completed group before attempting the next one.
                stamp=L.now();current=L.scan(settings,ref)
                incidental=[e for e in L.changes(store['snapshot'],current,stamp) if e['name'] not in {e['name'] for e in operations}]
                store={**store,'snapshot':current,'last_scan':stamp,'events':store['events']+incidental+operations};operations=[]
                L.atomic_write(self.base/'.data'/'ledger.json',json.dumps(store,ensure_ascii=False,indent=2))
                if backup.exists():L.atomic_write(backup/'receipt.json',json.dumps({'time':stamp,'results':results,'events':[e for e in store['events'] if e.get('recovery') and any(Path(x['backup']).is_relative_to(backup) for x in e['recovery'])]},ensure_ascii=False,indent=2))
            L.export(self.base,store)
            live=(self.base/'.data'/'live-data.js').read_text(encoding='utf-8')
            payload=json.loads(live.removeprefix('window.SkillLedgerReceive && window.SkillLedgerReceive(').removesuffix(');\n'))
            result={'results':results,'blocked':plan['blocked'],'data':payload}
            self.completed[plan_id]=result
            if len(self.completed)>20:self.completed.pop(next(iter(self.completed)))
            return result

def serve(base,catalog=True):
    manager=Manager(base);token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def host_ok(self):return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
        def origin_ok(self):return self.headers.get('Origin') in (None,'null',f'http://127.0.0.1:{self.server.server_port}')
        def reply(self,code,value,kind='application/json; charset=utf-8'):
            payload=value.encode('utf-8') if isinstance(value,str) else json.dumps(value,ensure_ascii=False).encode('utf-8')
            self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','no-referrer')
            if self.origin_ok() and self.headers.get('Origin'):self.send_header('Access-Control-Allow-Origin',self.headers['Origin'])
            self.end_headers();self.wfile.write(payload)
        def authorized(self):return self.host_ok() and self.origin_ok() and hmac.compare_digest(self.headers.get('X-Skill-Ledger-Token',''),token)
        def do_OPTIONS(self):
            if not self.host_ok() or not self.origin_ok():return self.reply(403,{'error':'来源不允许。'})
            self.send_response(204);self.send_header('Access-Control-Allow-Origin',self.headers.get('Origin','null'));self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.send_header('Access-Control-Allow-Headers','Content-Type, X-Skill-Ledger-Token');self.send_header('Access-Control-Allow-Private-Network','true');self.end_headers()
        def do_GET(self):
            if not self.host_ok():return self.reply(403,{'error':'地址不允许。'})
            route=urlsplit(self.path).path
            if route=='/':return self.reply(200,(base/'查看记录.html').read_text(encoding='utf-8'),'text/html; charset=utf-8')
            if route=='/api/data' and self.authorized():
                script=(base/'.data'/'live-data.js').read_text(encoding='utf-8')
                return self.reply(200,json.loads(script.removeprefix('window.SkillLedgerReceive && window.SkillLedgerReceive(').removesuffix(');\n')))
            return self.reply(403 if route.startswith('/api/') else 404,{'error':'请求不可用。'})
        def do_POST(self):
            if not self.authorized():return self.reply(403,{'error':'管理连接无效，请重新打开台账。'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size<1 or size>65536 or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('请求格式不正确。')
                body=json.loads(self.rfile.read(size));route=urlsplit(self.path).path
                if route=='/api/uninstall/preview':result=manager.preview(body.get('names'))
                elif route=='/api/uninstall/commit':result=manager.commit(body.get('id'))
                else:return self.reply(404,{'error':'请求不可用。'})
                self.reply(200,result)
            except Exception as error:self.reply(400,{'error':str(error)})
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    connection={'url':f'http://127.0.0.1:{server.server_port}','token':token,'pid':os.getpid()}
    L.atomic_write(base/'.data'/'connection.json',json.dumps(connection))
    L.atomic_write(base/'.data'/'connection.js','window.SkillLedgerConnect && window.SkillLedgerConnect('+json.dumps(connection)+');')
    threading.Thread(target=server.serve_forever,daemon=True).start()
    def catalog_loop():
        while True:refresh_catalog(base);time.sleep(60)
    if catalog:threading.Thread(target=catalog_loop,daemon=True).start()
    return server
