const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{environment}=require('./dom.cjs');
const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
const row=(name,mode,label)=>({name,category:'写作',status:'已启用',source:'本地技能',purpose:'整理文章',paths:[name],management:{kind:'local'},usage:'/'+name+' 整理以下文章：\n【文章材料】',usage_auto:'整理以下文章：\n【文章材料】',usage_desktop_hint:'输入 /，从菜单选择「'+name+'」，再填写任务。',usage_cli_hint:'CLI / IDE 使用 /skills 或 $技能名。',invocation:{mode,label,scope:'current',summary:mode==='manual'?'明确关闭自动匹配，需要手动调用。':'根据任务选择；不保证每次自动触发。',copies:[{skill_path:name+'/SKILL.md',metadata_path:name+'/agents/openai.yaml',basis:'policy.allow_implicit_invocation = '+(mode==='manual'?'false':'true')}],description:'用于整理文章'}});
const fixture={revision:'policy1',updated:'2026-10-17T00:20:00+08:00',skills:[row('copy-editing','auto_manual','自动匹配 + 手动'),row('edit-article','manual','仅手动调用'),row('writing-shape','mixed','多份策略不同'),{...row('to-spec','unknown','策略待核对'),status:'已归档',invocation:{mode:'unknown',label:'策略待核对',scope:'none',summary:'没有可读取的配置。',copies:[]}}],events:[]};
const settle=()=>new Promise(resolve=>setImmediate(resolve)),all=node=>[node,...node.children.flatMap(all)];let checks=0;const check=fn=>{fn();checks++};
async function main(){
 const copied=[],env=environment(fixture,'',source,undefined,{navigator:{clipboard:{writeText:async text=>copied.push(text)}}}),get=env.get;
 const find=name=>[...get('body').children].find(tr=>tr.children[1]?.children[0]?.title===name);
 check(()=>assert.match(find('edit-article').children[5].textContent,/仅手动调用/));check(()=>assert.match(find('copy-editing').children[5].textContent,/自动匹配 \+ 手动/));
 check(()=>assert.match(find('writing-shape').children[5].textContent,/多份策略不同/));
 get('filter-invocation').value='manual';get('filter-invocation').fire('change');check(()=>assert.equal(env.api.select().length,1));check(()=>assert.equal(env.api.select()[0].name,'edit-article'));
 find('edit-article').children[5].children.at(-1).click();await settle();check(()=>assert.ok(copied[0].startsWith('/edit-article ')));check(()=>assert.ok(!copied[0].startsWith('请使用')));
 find('edit-article').children[1].children[0].click();
 const manualTitles=all(get('detail-body')).filter(node=>node.tagName==='H4').map(node=>node.textContent);check(()=>assert.ok(!manualTitles.includes('自动匹配')));check(()=>assert.ok(manualTitles.includes('桌面端手动调用')));check(()=>assert.match(get('detail-body').textContent,/allow_implicit_invocation = false/));
 get('detail-close').click();get('filter-invocation').value='auto_manual';get('filter-invocation').fire('change');find('copy-editing').children[1].children[0].click();
 const automatic=all(get('detail-body')).find(node=>node.tagName==='BUTTON'&&node.textContent==='复制任务示例');check(()=>assert.ok(automatic));automatic.click();await settle();check(()=>assert.equal(copied.at(-1),fixture.skills[0].usage_auto));check(()=>assert.ok(!copied.at(-1).startsWith('/')));check(()=>assert.match(get('detail-body').textContent,/不保证每次自动触发/));
 get('detail-close').click();get('reset').click();get('filter-invocation').value='unknown';get('filter-invocation').fire('change');check(()=>assert.equal(env.api.select().length,1));check(()=>assert.match(find('to-spec').children[5].textContent,/先安装/));
 get('export').click();const csv=await env.downloads[0].blob.text();check(()=>assert.ok(csv.includes('调用方式')&&csv.includes('/to-spec ')));
 get('logs-tab').click();get('skills-tab').click();check(()=>assert.equal(get('filter-invocation').value,'unknown'));
 console.log('通过 '+checks+' 项调用方式筛选、斜杠示例、自动任务与依据展示断言。');
}
main().catch(error=>{console.error(error);process.exitCode=1});
