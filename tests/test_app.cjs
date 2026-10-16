const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const appName='../web/app.js';
const {environment}=require('./dom.cjs'),M=require('./'+appName);
const source=fs.readFileSync(path.join(__dirname,appName),'utf8');
let checks=0;const check=fn=>{fn();checks++},settle=()=>new Promise(resolve=>setImmediate(resolve));
const fixture=()=>({updated:'2026-10-16T23:00:00+08:00',revision:'r1',skills:[
 {name:'alpha',category:'开发',status:'已启用',purpose:'开发',source:'本地',paths:['alpha'],management:{kind:'local'}},
 {name:'beta',category:'开发',status:'已停用',purpose:'开发',source:'本地',paths:['beta'],management:{kind:'local'}},
 {name:'gamma',category:'内置',status:'已启用',purpose:'管理',source:'Codex',paths:['gamma'],management:{kind:'none',reason:'Codex 内置组件'}},
 {name:'plugin:demo',category:'写作',status:'已启用',purpose:'写作',source:'Plugin',paths:['demo'],management:{kind:'plugin'}},
 {name:'plugin:demo-blind',category:'写作',status:'已启用',purpose:'写作',source:'Plugin',paths:['demo-blind'],management:{kind:'plugin'}},
 {name:'old',category:'写作',status:'已归档',purpose:'旧技能',source:'本地',paths:['old'],archive_paths:'backup/old',management:{kind:'none'}}
],events:[{id:'old-event',name:'old',category:'写作',action:'归档',action_label:'归档',time:'2026-10-16T20:00:00+08:00',time_kind:'recorded',time_label:'记录时间',description:'已移出技能目录，文件保留用于恢复。'}]});

async function main(){
 check(()=>assert.equal(M.defaults().skills.status,'已安装'));
 check(()=>assert.equal(M.normalize({skills:{status:'已停用'}}).skills.status,'已安装'));
 check(()=>assert.equal(M.fromHash('#view=skills&status='+encodeURIComponent('已归档'),M.defaults()).skills.status,'已卸载'));
 check(()=>assert.equal(M.fromHash('#view=skills&status='+encodeURIComponent('未使用'),M.defaults()).skills.status,''));
 let data=fixture(),calls=[],release;
 const mock=async(url,options)=>{
  const body=options.body?JSON.parse(options.body):null;calls.push({url,body});
  if(url.endsWith('/preview')){
   const names=body.names,groups=[],blocked=[];
   for(const name of names){if(name==='gamma'){blocked.push({name,reason:'Codex 内置组件，不支持在此卸载。'});continue}if(name.startsWith('plugin:')){if(!groups.some(g=>g.kind==='plugin'))groups.push({kind:'plugin',key:'plugin@market',names:['plugin:demo','plugin:demo-blind']})}else groups.push({kind:'local',key:name,names:[name]})}
   const affected=[...new Set(groups.flatMap(g=>g.names))];return {ok:true,json:async()=>({id:'plan',count:affected.length,selected_names:names,groups,blocked,extra_names:affected.filter(n=>!names.includes(n))})}
  }
  if(url.endsWith('/commit')){
   await new Promise(resolve=>{release=resolve});
   const removed=['alpha','plugin:demo','plugin:demo-blind'];data={...data,revision:'r2',skills:data.skills.map(row=>removed.includes(row.name)?{...row,status:'已卸载',installed:false,management:{kind:'none'}}:row)};
   for(const name of removed)data.events.push({id:name+'-removed',name,category:name==='alpha'?'开发':'写作',action:'卸载',action_label:'卸载',time:'2026-10-16T23:10:00+08:00',time_kind:'operation',time_label:'操作时间',description:'卸载已完成。'});
   return {ok:true,json:async()=>({results:[{key:'alpha',names:['alpha'],ok:true},{key:'beta',names:['beta'],ok:false,error:'文件正在使用，未卸载。'},{key:'plugin',names:removed.slice(1),ok:true}],blocked:[{name:'gamma',reason:'内置组件'}],data})}
  }
  if(url.endsWith('/api/data'))return {ok:true,json:async()=>data};throw Error('Unexpected '+url)
 };
 const env=environment(data,'',source,mock),get=env.get,api=env.api;
 env.window.SkillLedgerConnect({url:'http://127.0.0.1:12345',token:'test'});
 const row=name=>[...get('body').children].find(tr=>tr.children[1]?.children[0]?.title===name);
 const pick=name=>row(name).children[0].children[0];
 const filter=(key,value)=>{get('filter-'+key).value=value;get('filter-'+key).fire(key==='name'?'input':'change')};
 check(()=>assert.equal(api.select().length,5));
 check(()=>assert.equal(api.select().find(r=>r.name==='beta').status,'已安装'));
 check(()=>assert.equal(get('filter-status').children.map(o=>o.value).join('|'),'|已安装|已卸载'));
 check(()=>assert.equal([...get('columns').children].reduce((total,col)=>total+parseInt(col.style.width),0),100));
 check(()=>assert.equal(pick('gamma').disabled,false));check(()=>!appName.includes('v5')?assert.equal(row('gamma').children[7].children[0].textContent,'由 Codex 管理'):assert.equal(row('gamma').children[6].children[0].disabled,true));
 get('select-all').checked=true;get('select-all').fire('change');
 check(()=>assert.match(get('selection-summary').textContent,/已选 5 项/));check(()=>assert.equal([...get('body').children].filter(tr=>tr.children[0].children[0].checked).length,5));
 const stable=pick('alpha');stable.checked=false;stable.fire('change');
 check(()=>assert.equal(pick('alpha'),stable));check(()=>assert.equal(get('select-all').indeterminate,true));
 get('select-visible').click();check(()=>assert.match(get('selection-summary').textContent,/已选 5 项/));
 filter('name','alpha');check(()=>assert.match(get('selection-summary').textContent,/4 项不在当前列表/));check(()=>assert.equal(pick('alpha').checked,true));
 get('select-all').checked=false;get('select-all').fire('change');check(()=>assert.match(get('selection-summary').textContent,/已选 4 项/));
 get('select-installed').click();check(()=>assert.match(get('selection-summary').textContent,/已选 5 项/));
 get('logs-tab').click();get('skills-tab').click();check(()=>assert.match(get('selection-summary').textContent,/已选 5 项/));check(()=>assert.equal(get('filter-name').value,'alpha'));
 get('clear-selection').click();check(()=>assert.equal(get('bulk-remove').disabled,true));
 filter('name','plugin:demo');const input=pick('plugin:demo');input.checked=true;input.fire('change');get('bulk-remove').click();await settle();
 check(()=>assert.match(get('remove-body').textContent,/已选 1 项 · 实际卸载 2 项 · 另含 1 项连带技能/));
 check(()=>assert.match(get('remove-body').textContent,/连带移除/));check(()=>assert.equal(get('remove-confirm').disabled,true));
 get('remove-confirm').click();check(()=>assert.equal(calls.filter(c=>c.url.endsWith('/commit')).length,0));
 get('remove-close').click();get('clear-selection').click();get('reset').click();filter('status','已安装');
 get('select-installed').click();get('bulk-remove').click();await settle();
 check(()=>assert.match(get('remove-body').textContent,/已选 5 项 · 实际卸载 4 项 · 1 项不执行/));
 check(()=>assert.match(get('remove-body').textContent,/以下项目不执行卸载/));
 get('remove-ack').checked=true;get('remove-ack').fire('change');check(()=>assert.equal(get('remove-confirm').disabled,false));
 get('remove-confirm').click();await settle();
 check(()=>assert.equal(get('select-all').disabled,true));check(()=>assert.equal(get('select-installed').disabled,true));
 check(()=>assert.equal(pick('beta').disabled,true));check(()=>assert.match(get('remove-confirm').textContent,/正在卸载 4 项/));
 get('remove-confirm').click();check(()=>assert.equal(calls.filter(c=>c.url.endsWith('/commit')).length,1));
 release();await settle();await settle();
 check(()=>assert.equal(calls.filter(c=>c.url.endsWith('/api/data')).length,0));
 check(()=>assert.match(get('remove-body').textContent,/已卸载 3 项 · 失败 1 项 · 未执行 1 项/));
 check(()=>assert.match(get('remove-body').textContent,/beta卸载失败/));check(()=>assert.match(get('remove-body').textContent,/gamma · 未执行/));
 check(()=>assert.equal(get('remove-title').textContent,'卸载结果：部分失败'));
 check(()=>assert.equal(api.select().length,2));check(()=>assert.equal(pick('beta').checked,true));check(()=>assert.equal(pick('gamma').checked,false));
 check(()=>assert.match(get('selection-summary').textContent,/已选 1 项/));check(()=>assert.match(get('select-installed').textContent,/2/));
 filter('status','已卸载');check(()=>assert.equal(api.select().length,4));check(()=>assert.equal(get('select-visible').disabled,true));
 check(()=>assert.match(get('selection-summary').textContent,/1 项不在当前列表/));
 row('old').children[1].children[0].click();check(()=>assert.ok(!get('detail-body').textContent.includes('已归档')));check(()=>assert.match(get('detail-body').textContent,/已卸载/));
 get('detail-close').click();get('export').click();const csv=await env.downloads[0].blob.text();check(()=>assert.ok(csv.includes('已卸载')&&!csv.includes('已归档')&&!csv.includes('未使用')));
 const next=structuredClone(data);next.revision='r3';next.skills=next.skills.map(r=>r.name==='beta'?{...r,status:'已卸载',installed:false,management:{kind:'none'}}:r);env.window.SkillLedgerReceive(next);
 check(()=>assert.equal(get('bulk-remove').disabled,true));check(()=>assert.match(get('selection-summary').textContent,/尚未选择/));
 console.log('通过 '+checks+' 项安装状态、全选、跨筛选勾选、卸载范围与结果同步断言。');
}
main().catch(error=>{console.error(error);process.exitCode=1});
