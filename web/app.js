const SkillLedgerModel=(()=>{
 const clone=value=>JSON.parse(JSON.stringify(value));
 const blankSkills=()=>({name:'',exactName:'',status:'',purpose:'',usage:'',invocation:'',source:''});
 const blankLogs=()=>({name:'',exactName:'',action:'',description:'',from:'',to:''});
 const defaults=()=>({view:'skills',category:'',skills:{...blankSkills(),status:'已安装'},logs:blankLogs(),sort:{skills:{key:'name',direction:1},logs:{key:'time',direction:-1}},scroll:{skills:0,logs:0},detail:null});
 const status=value=>['已安装','已启用','已停用','使用中'].includes(value)?'已安装':['已卸载','已归档','已移除','未发现'].includes(value)?'已卸载':'';
 const installed=row=>typeof row.installed==='boolean'?row.installed:row.status==='已安装';
 const toggleSelection=(current,names,checked)=>{const next=new Set(current);for(const name of names){if(checked)next.add(name);else next.delete(name)}return next};
 const pruneSelection=(current,skills)=>new Set(skills.filter(row=>installed(row)&&current.has(row.name)).map(row=>row.name));
 const scopeKey=row=>row.scope_id||row.category||'global';
 const scopeLabel=row=>row.scope_label||row.category||'全局技能';
 const toggleScope=(current,names)=>toggleSelection(current,names,!names.length||!names.every(name=>current.has(name)));
 const contains=(value,q)=>!q||String(value||'').toLowerCase().includes(q.trim().toLowerCase());
 function normalize(raw){
  const state=defaults();if(!raw||typeof raw!=='object')return state;
  if(['skills','logs'].includes(raw.view))state.view=raw.view;
  if(typeof raw.category==='string')state.category=raw.category;
  for(const view of ['skills','logs']){
   for(const key of Object.keys(state[view]))if(typeof raw[view]?.[key]==='string')state[view][key]=raw[view][key];
   const allowed=view==='skills'?['name','category','status','purpose','usage','source']:['time','name','category','action','description'];
   if(allowed.includes(raw.sort?.[view]?.key))state.sort[view]={key:raw.sort[view].key,direction:raw.sort[view].direction===-1?-1:1};
   if(Number.isFinite(raw.scroll?.[view]))state.scroll[view]=Math.max(0,raw.scroll[view]);
  }
  if(raw.detail&&typeof raw.detail.name==='string')state.detail={name:raw.detail.name,eventId:typeof raw.detail.eventId==='string'?raw.detail.eventId:''};
  state.skills.status=status(state.skills.status);if(['归档','移除'].includes(state.logs.action))state.logs.action='卸载';return state
 }
 function reduce(state,action){
  const next=clone(state),view=next.view;
  if(action.type==='TAB'&&['skills','logs'].includes(action.view)){next.view=action.view;next.detail=null}
  if(action.type==='CATEGORY'){next.category=action.value;next.scroll={skills:0,logs:0}}
  if(action.type==='FILTER'&&Object.hasOwn(next[view],action.key)){next[view][action.key]=action.value;if(action.key==='name')next[view].exactName='';next.scroll[view]=0}
  if(action.type==='CLEAR'){next.category='';next[view]=view==='skills'?blankSkills():blankLogs();next.scroll[view]=0}
  if(action.type==='SORT'){const current=next.sort[view];next.sort[view]={key:action.key,direction:current.key===action.key?-current.direction:action.key==='time'?-1:1};next.scroll[view]=0}
  if(action.type==='SCROLL')next.scroll[view]=Math.max(0,action.value);
  if(action.type==='DETAIL')next.detail={name:action.name,eventId:action.eventId||''};
  if(action.type==='CLOSE_DETAIL')next.detail=null;
  if(action.type==='SKILL_LOGS'){next.view='logs';next.logs={...blankLogs(),name:action.name,exactName:action.name};next.scroll.logs=0;next.detail=null}
  if(action.type==='LOCATE_SKILL'){next.view='skills';next.skills={...blankSkills(),name:action.name,exactName:action.name};next.scroll.skills=0;next.detail=null}
  return next
 }
 function dateError(state){return state.view==='logs'&&state.logs.from&&state.logs.to&&state.logs.from>state.logs.to?'开始日期不能晚于结束日期。':''}
 function select(data,state,ignoreCategory=false){
  if(dateError(state))return [];
  const f=state[state.view];let rows;
  if(state.view==='skills')rows=data.skills.filter(r=>(!f.exactName?r.name&&contains(r.name,f.name):r.name===f.exactName)&&(!f.status||r.status===f.status)&&contains(r.purpose,f.purpose)&&contains([r.invocation?.label,r.usage_note,r.usage].filter(Boolean).join(' '),f.usage)&&(!f.invocation||r.invocation?.mode===f.invocation)&&(!f.source||r.source===f.source));
  else rows=data.events.filter(e=>(!f.exactName?contains(e.name,f.name):e.name===f.exactName)&&(!f.action||e.action===f.action)&&contains(e.description||e.detail,f.description)&&(!f.from||e.time.slice(0,10)>=f.from)&&(!f.to||e.time.slice(0,10)<=f.to));
  if(!ignoreCategory&&state.category)rows=rows.filter(r=>scopeKey(r)===state.category);
  const sort=state.sort[state.view],sortValue=row=>sort.key==='category'?scopeLabel(row):sort.key==='name'?(row.skill_name||row.name):row[sort.key];return [...rows].sort((a,b)=>String(sortValue(a)||'').localeCompare(String(sortValue(b)||''),'zh-CN')*sort.direction)
 }
 function csv(data,state){
  const rows=select(data,state),history=state.view==='logs';
  const fields=history?['事件时间','时间类型','操作','技能名称','所属项目 / 范围','说明']:['技能名称','所属项目 / 范围','状态','用途','调用方式','使用方法','技能来源'];
  const cells=history?rows.map(r=>[r.time,r.time_label,r.action_label||r.action,r.skill_name||r.name,scopeLabel(r),r.description||r.detail]):rows.map(r=>[r.skill_name||r.name,scopeLabel(r),r.status,r.purpose,r.invocation?.label||'策略待核对',[r.usage_note,r.usage_desktop_hint,r.usage].filter(Boolean).join('\n'),r.source]);
  const escape=value=>{let text=String(value??'');if(/^[=+\-@\t\r\n]/.test(text))text="'"+text;return '"'+text.replaceAll('"','""')+'"'};
  return '\ufeff'+[fields,...cells].map(row=>row.map(escape).join(',')).join('\r\n')+'\r\n'
 }
 function hash(state){
  const p=new URLSearchParams({view:state.view});if(state.category)p.set('category',state.category);
  for(const [key,value]of Object.entries(state[state.view]))if(value)p.set(key,value);
  if(state.detail){p.set('detail',state.detail.name);if(state.detail.eventId)p.set('event',state.detail.eventId)}
  return '#'+p.toString()
 }
 function fromHash(value,fallback){
  const p=new URLSearchParams(value.replace(/^#/,''));if(!['skills','logs'].includes(p.get('view')))return normalize(fallback);
  const state=normalize(fallback);state.view=p.get('view');state.category=p.get('category')||'';
  state[state.view]=state.view==='skills'?blankSkills():blankLogs();
  for(const key of Object.keys(state[state.view]))state[state.view][key]=p.get(key)||'';
  state.detail=p.get('detail')?{name:p.get('detail'),eventId:p.get('event')||''}:null;return normalize(state)
 }
 return {defaults,normalize,reduce,select,csv,dateError,hash,fromHash,status,installed,toggleSelection,pruneSelection,toggleScope,scopeKey,scopeLabel}
})();
if(typeof module!=='undefined'&&module.exports)module.exports=SkillLedgerModel;
if(typeof document!=='undefined')(()=>{
 const M=SkillLedgerModel,$=id=>document.getElementById(id),make=(tag,className,text)=>{const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node};
 const prepare=value=>({...value,skills:value.skills.map(row=>{const installed=typeof row.installed==='boolean'?row.installed:['已安装','已启用','已停用'].includes(row.status);return {...row,installed,raw_status:row.status,status:installed?'已安装':'已卸载',invocation:row.invocation||{mode:'unknown',label:'策略待核对',summary:'暂未读取调用策略，建议从技能菜单手动选择。',copies:[]},usage:row.usage||'/'+(row.skill_name||row.name.split('@@project-')[0]).split(':').at(-1)+' 【任务和材料】',usage_note:row.usage_note||(!installed?'先安装该技能，再使用下方示例。':row.status==='已停用'?'先在 Codex 中开启该技能的启用设置。':'')}}),events:value.events.map(event=>({...event,raw_action:event.action,action:['归档','移除'].includes(event.action)?'卸载':event.action,action_label:event.action==='归档'?'卸载':event.action_label||event.action}))});
 let data=prepare(JSON.parse($('data').textContent)),saved=null,connection=null,selection=new Set(),plan=null,busy=false;
 const access=new URLSearchParams(location.hash.replace(/^#/,''));
 try{saved=JSON.parse(localStorage.getItem('skill-ledger-view-v5'));const token=access.get('access')||sessionStorage.getItem('skill-ledger-access');if(token&&location.protocol==='http:'){connection={url:location.origin,token};sessionStorage.setItem('skill-ledger-access',token)}}catch{}
 let state=M.fromHash(location.hash,saved||M.defaults());let rendering=false;let headerView='';let headerSignature='';
 const timeText=value=>value?value.slice(0,19).replace('T',' '):'未记录';
 const options=(values,selected)=>[...new Set([...values,...(selected?[selected]:[])])].sort((a,b)=>a.localeCompare(b,'zh-CN'));
 const skillMap=()=>new Map(data.skills.map(s=>[s.name,s]));
 const scopeMap=()=>new Map([...(data.discovery?.scopes||[]).map(r=>[r.scope_id,r]),...data.skills.map(r=>[M.scopeKey(r),{scope_id:M.scopeKey(r),scope_label:M.scopeLabel(r),scope_path:r.scope_path||''}])]);
 const scopeCaption=key=>key?(scopeMap().get(key)?.scope_label||key):'全部技能';
 const displayName=name=>{const skill=skillMap().get(name);return skill?.skill_name||name.split('@@project-')[0]};
 const removalName=name=>displayName(name)+(skillMap().get(name)?.scope_kind==='project'?' · '+M.scopeLabel(skillMap().get(name)):'');
 if(data.discovery&&state.category&&!scopeMap().has(state.category))state.category='';
 function remember(){try{localStorage.setItem('skill-ledger-view-v5',JSON.stringify(state))}catch{}}
 function writeHistory(push,detailEntry=false){
  const value={skillLedger:true,state:JSON.parse(JSON.stringify(state)),detailEntry};
  try{history[push?'pushState':'replaceState'](value,'',M.hash(state))}catch{}
  remember()
 }
 function transition(action,push=false){
  state.scroll[state.view]=$('table-scroll').scrollTop;
  if(push)writeHistory(false,Boolean(state.detail));
  state=M.reduce(state,action);writeHistory(push,action.type==='DETAIL');render()
 }
 function badge(status){return make('span','badge '+(status==='已安装'?'enabled':'uninstalled'),status)}
 function invocationBadge(skill){const policy=skill.invocation;const tag=make('span','invocation-badge '+policy.mode,policy.label+(policy.scope==='backup'?'（备份）':''));tag.title=policy.summary;return tag}
 function fillUsageCell(cell,skill){cell.append(invocationBadge(skill));if(skill.usage_note)cell.append(make('span','usage-note',skill.usage_note));const example=make('span','usage-example',skill.usage);example.title=(skill.usage_desktop_hint||'输入 /，从菜单选择对应技能，再填写任务。')+'\n'+skill.usage;cell.append(example,copyButton(skill))}
 function usageDetails(skill){
  const section=make('section','usage-instructions'),policy=skill.invocation;section.append(make('h3','','调用方式'),invocationBadge(skill),make('p','',policy.summary));
  if(skill.usage_note)section.append(make('p','usage-note',skill.usage_note));
  if(policy.mode==='auto_manual'&&skill.usage_auto){section.append(make('h4','','自动匹配'),make('p','','直接描述相关任务，Codex 可按场景选择本技能；不保证每次自动触发。'),make('pre','usage-full',skill.usage_auto),copyButton(skill,'auto'))}
  section.append(make('h4','','桌面端手动调用'),make('p','',skill.usage_desktop_hint||'输入 /，从菜单选中对应技能，再填写任务。'),make('pre','usage-full',skill.usage),copyButton(skill));
  if(skill.usage_connection)section.append(make('p','usage-help',skill.usage_connection));if(skill.usage_cli_hint)section.append(make('p','usage-help',skill.usage_cli_hint));
  const evidence=make('details','invocation-evidence');evidence.append(make('summary','','查看判断依据'));
  for(const copy of policy.copies||[])evidence.append(make('p','',copy.skill_path+'\n'+copy.basis+'\n'+copy.metadata_path));
  if(!policy.copies?.length)evidence.append(make('p','','没有可读取的当前技能文件或恢复备份，自动匹配策略尚待核对。'));
  if(policy.description)evidence.append(make('h4','','技能声明的适用场景'),make('p','',policy.description));section.append(evidence);return section
 }
 function nameButton(name,eventId=''){const button=make('button','skill-link',displayName(name).includes(':')?displayName(name).slice(displayName(name).indexOf(':')+1):displayName(name));button.type='button';button.title=name.includes('@@project-')?displayName(name)+' · '+(skillMap().get(name)?.scope_path||'项目技能'):name;button.onclick=()=>transition({type:'DETAIL',name,eventId},true);return button}
 function buildHead(){
  const sourceValues=options(data.skills.map(s=>s.source),state.skills.source),categoryValues=[...scopeMap().keys()].sort();
  const signature=JSON.stringify([state.view,sourceValues,categoryValues,data.events.map(e=>e.action).filter((v,i,a)=>a.indexOf(v)===i),state.sort[state.view]]);
  if(signature===headerSignature&&state.view===headerView)return;
  const focused=document.activeElement,id=focused?.id,textSelection=focused?.type==='search'?[focused.selectionStart,focused.selectionEnd]:null;
  headerSignature=signature;headerView=state.view;$('head').replaceChildren();$('columns').replaceChildren();
  const fields=state.view==='skills'?[['技能名称','name',18,'text'],['所属范围','category',11,'category'],['状态','status',9,'status'],['用途','purpose',20,'text'],['使用方法','usage',20,'text'],['技能来源','source',10,'source']]:[['事件时间','time',22,'range'],['技能名称','name',25,'text'],['所属范围','category',16,'category'],['操作','action',13,'action'],['说明','description',24,'text']];
  const titles=make('tr'),filters=make('tr','filters');
  if(state.view==='skills'){
   const col=make('col');col.style.width='4%';$('columns').append(col);const th=make('th'),select=make('input');select.type='checkbox';select.id='select-all';select.setAttribute('aria-label','全选当前结果中的已安装技能');select.title='全选当前结果中的已安装技能';select.onchange=()=>{selection=M.toggleSelection(selection,M.select(data,state).filter(M.installed).map(row=>row.name),select.checked);syncSelection()};th.append(select);titles.append(th);filters.append(make('th'))
  }
  for(const [label,key,width,type]of fields){
   const col=make('col');col.style.width=width+'%';$('columns').append(col);
   const th=make('th');th.scope='col';const sort=make('button','sort'+(state.sort[state.view].key===key?' sorted':''));sort.type='button';sort.append(document.createTextNode(label),make('span','arrow',state.sort[state.view].key===key?(state.sort[state.view].direction===1?'↑':'↓'):'↕'));sort.setAttribute('aria-label','按'+label+'排序');if(key==='source')sort.title='提供该技能的插件或本地安装方式，不表示作者、下载网址或文件位置';if(key==='usage')sort.title='复制示例到本机 Codex 对话，替换【】中的材料；不会自动执行';sort.onclick=()=>transition({type:'SORT',key});th.append(sort);titles.append(th);
   const cell=make('th');
   if(type==='range'){
    const wrap=make('div','date-range');for(const key of ['from','to']){const input=make('input','filter filter-date');input.type='date';input.id='filter-'+key;input.setAttribute('aria-label',key==='from'?'日志起始日期':'日志结束日期');input.onchange=()=>transition({type:'FILTER',key,value:input.value});wrap.append(input)}cell.append(wrap)
   }else{
    let control;
    if(['category','source','status','action'].includes(type)){
     control=make('select','filter');const values=type==='category'?categoryValues:type==='source'?sourceValues:type==='status'?['已安装','已卸载']:options(data.events.map(e=>e.action),state.logs.action);
     control.append(new Option({category:'全部范围',source:'全部来源',status:'全部状态',action:'全部操作'}[type],''));for(const value of values)control.append(new Option(type==='category'?scopeCaption(value):value,value));
     control.onchange=()=>transition(type==='category'?{type:'CATEGORY',value:control.value}:{type:'FILTER',key,value:control.value})
    }else{control=make('input','filter');control.type='search';control.placeholder=key==='name'?'筛选名称':'筛选关键词';control.oninput=()=>transition({type:'FILTER',key,value:control.value})}
    control.id='filter-'+key;control.setAttribute('aria-label','筛选'+label);cell.append(control)
   }
   if(key==='usage'){const mode=make('select','filter invocation-filter');mode.id='filter-invocation';mode.setAttribute('aria-label','筛选调用方式');for(const [value,label]of [['','全部调用方式'],['auto_manual','自动匹配 + 手动'],['manual','仅手动调用'],['mixed','多份策略不同'],['unknown','策略待核对']])mode.append(new Option(label,value));mode.onchange=()=>transition({type:'FILTER',key:'invocation',value:mode.value});cell.prepend(mode)}
   filters.append(cell)
  }
  if(state.view==='skills'){const col=make('col');col.style.width='8%';$('columns').append(col);titles.append(make('th','','操作'));filters.append(make('th'))}
  $('head').append(titles,filters);
  if(id){const replacement=$(id);if(replacement){replacement.focus();if(textSelection)replacement.setSelectionRange(...textSelection)}}
 }
 function syncControls(){
  for(const [key,value]of Object.entries(state[state.view])){const input=$('filter-'+key);if(input&&input.value!==value)input.value=value}
  if($('filter-category').value!==state.category)$('filter-category').value=state.category;
  const selected=state[state.view].exactName;$('exact-skill').hidden=!selected;$('exact-skill-name').textContent=selected?removalName(selected):'';
  const error=M.dateError(state);$('filter-error').textContent=error;$('filter-error').hidden=!error
 }
 function renderCategories(){
  const nav=$('categories'),active=document.activeElement?.dataset?.category;nav.replaceChildren();
  const scopes=scopeMap(),counts=new Map();for(const row of M.select(data,state,true))counts.set(M.scopeKey(row),(counts.get(M.scopeKey(row))||0)+1);
  const entries=[['全部技能','',M.select(data,state,true).length],...([...scopes.values()].sort((a,b)=>a.scope_id==='global'?-1:b.scope_id==='global'?1:a.scope_label.localeCompare(b.scope_label,'zh-CN')).map(r=>[r.scope_label,r.scope_id,counts.get(r.scope_id)||0]))];
  for(const [label,key,count]of entries){
   const button=make('button','category-button'+(state.category===key?' active':'')+(count===0?' no-results':''));button.type='button';button.dataset.category=key;
   const scope=scopes.get(key);button.title=key==='global'?'用户级独立技能、插件及内置技能':scope?.scope_path||'所有监控范围；数字随当前筛选变化';
   if(state.category===key)button.setAttribute('aria-current','true');button.append(make('span','',label),make('span','number',count));button.onclick=()=>transition({type:'CATEGORY',value:key});nav.append(button);if(active===key)button.focus()
  }
 }
 function renderRows(){
  const tbody=$('body');tbody.replaceChildren();const rows=M.select(data,state);
  for(const row of rows){const tr=make('tr');
   if(state.view==='skills'){const pick=make('td','pick-cell'),checkbox=make('input');checkbox.type='checkbox';checkbox.dataset.skill=row.name;checkbox.checked=selection.has(row.name);checkbox.disabled=!row.installed||busy;checkbox.setAttribute('aria-label','选择 '+removalName(row.name));checkbox.title=row.installed?'选择 '+removalName(row.name):'已经卸载，无需重复选择';checkbox.onchange=()=>{selection=M.toggleSelection(selection,[row.name],checkbox.checked);syncSelection()};pick.append(checkbox);const name=make('td'),status=make('td'),action=make('td','row-action'),usage=make('td','usage-cell'),source=make('td','source-cell');name.append(nameButton(row.name));status.append(badge(row.status));fillUsageCell(usage,row);source.title=row.source_detail||'提供该技能的插件或本地安装方式';source.append(make('span','',row.source));if(row.source_type)source.append(make('span','source-type',row.source_type));if(canRemove(row)){const button=make('button','remove-button',row.management.kind==='plugin'?'卸载插件':'卸载');button.disabled=busy;button.onclick=()=>previewUninstall([row.name]);action.append(button)}else if(row.installed){const managed=(row.management?.reason||'').includes('内置');const note=make(managed?'span':'button','managed-note',managed?'由 Codex 管理':'查看说明');note.title=row.management?.reason||'请在 Codex 中管理';if(managed){note.tabIndex=0;note.setAttribute('aria-label','由 Codex 管理：'+note.title)}else note.onclick=()=>transition({type:'DETAIL',name:row.name},true);action.append(note)}else action.append(make('span','protected-note','—'));tr.append(pick,name,make('td','category-cell',M.scopeLabel(row)),status,make('td','purpose-cell',row.purpose),usage,source,action)}
   else{const at=make('td','event-time'),name=make('td');at.append(make('span','event-time-value',timeText(row.time)),make('span','time-kind '+row.time_kind,row.time_label));name.append(nameButton(row.name,row.id));tr.append(at,name,make('td','category-cell',M.scopeLabel(row)),make('td','history-action',row.action_label||row.action),make('td','history-summary',row.description||row.detail))}
   tbody.append(tr)
  }
  if(!rows.length){const tr=make('tr'),td=make('td','empty');td.colSpan=state.view==='skills'?8:5;td.append(make('strong','','没有匹配的记录'),document.createTextNode(M.dateError(state)||'当前分类下没有符合筛选条件的记录。'));const clear=make('button','','清空当前页筛选');clear.onclick=()=>transition({type:'CLEAR'});td.append(make('br'),clear);tr.append(td);tbody.append(tr)}
  syncSelection();
  const parts=[scopeCaption(state.category),state.view==='skills'?(state.skills.status||'全部状态'):(state.logs.action||'全部操作')];$('count').textContent=parts.join(' · ')+' · '+rows.length+(state.view==='skills'?' 项技能':' 条日志');
  $('skills-tab').classList.toggle('active',state.view==='skills');$('logs-tab').classList.toggle('active',state.view==='logs');$('skills-tab').setAttribute('aria-selected',state.view==='skills');$('logs-tab').setAttribute('aria-selected',state.view==='logs');
  $('table-scroll').scrollTop=state.scroll[state.view]
 }
 function syncSelection(){
  selection=M.pruneSelection(selection,data.skills);const shown=state.view==='skills'?M.select(data,state).filter(M.installed):[],selectedShown=shown.filter(row=>selection.has(row.name)).length;
  $('selection-tools').hidden=state.view!=='skills';$('bulk-remove').hidden=state.view!=='skills';$('bulk-remove').disabled=!selection.size||busy;$('bulk-remove').textContent='卸载所选'+(selection.size?'（'+selection.size+'）':'');
  $('select-visible').disabled=!shown.length||busy;$('select-visible').textContent=(shown.length&&selectedShown===shown.length?'取消当前结果选择':'全选当前结果')+'（'+shown.length+'）';$('clear-selection').disabled=!selection.size||busy;
  $('selection-summary').textContent=selection.size?'已选 '+selection.size+' 项'+(selection.size>selectedShown?' · 其中 '+(selection.size-selectedShown)+' 项不在当前列表':''):'尚未选择技能';
  const header=$('select-all');if(header){header.checked=shown.length>0&&selectedShown===shown.length;header.indeterminate=selectedShown>0&&selectedShown<shown.length;header.disabled=!shown.length||busy;header.title=header.checked?'取消当前结果选择':'全选当前结果中的已安装技能';header.setAttribute('aria-label',header.title)}
  const byName=skillMap();for(const tr of $('body').children){const input=tr.children[0]?.children[0];if(input?.dataset?.skill){input.checked=selection.has(input.dataset.skill);input.disabled=busy||!byName.get(input.dataset.skill)?.installed}}
 }
 function renderDetail(){
  const context=state.detail,dialog=$('detail');if(!context){if(dialog.open)dialog.close();return}
  const skill=skillMap().get(context.name);if(!skill){if(dialog.open)dialog.close();return}
  $('detail-title').textContent=displayName(skill.name);const body=$('detail-body');body.replaceChildren();
  const selectedEvent=context.eventId?data.events.find(e=>e.id===context.eventId):null;
  if(selectedEvent){const panel=make('section','event-panel');panel.append(make('strong','',selectedEvent.action_label||selectedEvent.action),make('p','',timeText(selectedEvent.time)+' · '+selectedEvent.time_label),make('p','',selectedEvent.description||selectedEvent.detail));body.append(panel)}
  const dl=make('dl'),lifecycle=skill.lifecycle||{};
  const installation=lifecycle.installed_at?timeText(lifecycle.installed_at)+'（操作时间）':lifecycle.present_at_baseline?'未记录，建账前已存在':'未记录';
  const fields=[['安装状态',skill.status],['所属范围',M.scopeLabel(skill)],...(skill.scope_path?[['项目目录',skill.scope_path],['适用说明','此处表示该目录本地安装的技能；Codex 是否加载取决于工作目录到仓库根的查找范围。全局技能另列。']]:[['适用说明','用户级或插件 / 内置技能，可跨项目使用；实际可用性仍取决于启用配置与连接。']]),['用途',skill.purpose],['技能来源',skill.source],['来源说明',skill.source_detail||'提供该技能的插件或本地安装方式'],['安装时间',installation]];
  if(skill.installed)fields.splice(1,0,['启用设置',skill.raw_status==='已停用'?'已关闭；文件仍安装在本机':'已开启']);
  else fields.splice(1,0,['卸载说明',skill.raw_status==='已归档'?'已移出安装目录，另有恢复备份':'安装目录中已无该技能']);
  if(lifecycle.first_detected_at)fields.push(['首次发现',timeText(lifecycle.first_detected_at)+'（检测时间）']);
  const statusAction={'已卸载':'卸载','已归档':'归档','已停用':'停用','已移除':'移除'}[skill.raw_status];
  const statusEvent=statusAction?data.events.filter(e=>e.name===skill.name&&(e.raw_action||e.action)===statusAction).at(-1):null;
  if(statusEvent)fields.push([(statusAction==='归档'?'卸载':statusAction)+(statusEvent.time_kind==='operation'?'时间':'记录'),timeText(statusEvent.time)+'（'+statusEvent.time_label+'）']);
  fields.push(['版本',skill.version||'未标注'],[['已归档','已卸载','已移除','未发现'].includes(skill.raw_status)?'原位置':'位置',skill.paths.join('\n')||'未记录']);
  if(skill.archive_paths)fields.push(['恢复备份',Array.isArray(skill.archive_paths)?skill.archive_paths.join('\n'):skill.archive_paths]);
  if(skill.recovery_paths?.length)fields.push(['卸载备份',skill.recovery_paths.join('\n')]);
  for(const [label,value]of fields)dl.append(make('dt','',label),make('dd','',value));body.append(dl);
  body.append(usageDetails(skill));
  const related=data.events.filter(e=>e.name===skill.name).slice().sort((a,b)=>b.time.localeCompare(a.time));
  if(related.length){body.append(make('h3','','操作时间线'));for(const event of related){const row=make('div','timeline-event');row.append(make('span','timeline-action',event.action_label||event.action),make('span','timeline-time',timeText(event.time)+' · '+event.time_label),make('span','timeline-description',event.description||event.detail));body.append(row)}}
  $('skill-logs').onclick=()=>transition({type:'SKILL_LOGS',name:skill.name},true);$('locate-skill').onclick=()=>transition({type:'LOCATE_SKILL',name:skill.name},true);
  $('detail-remove').hidden=!canRemove(skill);$('detail-remove').textContent=skill.management?.kind==='plugin'?'卸载插件':'卸载';$('detail-remove').onclick=()=>previewUninstall([skill.name]);
  if(!dialog.open)dialog.showModal()
 }
 function render(){
  if(data.discovery&&state.category&&!scopeMap().has(state.category))state.category='';
  rendering=true;buildHead();syncControls();renderCategories();renderRows();renderDetail();$('last-scan').textContent=timeText(data.updated);rendering=false
 }
 function closeDetail(){if(history.state?.detailEntry)history.back();else transition({type:'CLOSE_DETAIL'})}
 const canRemove=row=>Boolean(row.management&&['local','plugin'].includes(row.management.kind));
 function copyButton(skill,kind='manual'){const label=kind==='auto'?'复制任务示例':'复制手动指令',text=kind==='auto'?skill.usage_auto:skill.usage;const button=make('button','copy-usage',label);button.type='button';button.title=kind==='auto'?'复制自然语言任务，供 Codex 按场景自动匹配；不会自动执行':'桌面端先输入 / 并从菜单选择技能，再填写任务；不会自动执行';button.setAttribute('aria-label',label+' '+skill.name);button.onclick=async()=>{try{if(typeof navigator==='undefined'||!navigator.clipboard?.writeText)throw Error('manual copy');await navigator.clipboard.writeText(text);button.textContent='已复制';setTimeout(()=>{button.textContent=label},1600)}catch{$('copy-text').value=text;if(!$('copy-dialog').open)$('copy-dialog').showModal();$('copy-text').focus();$('copy-text').select()}};return button}
 $('copy-close').onclick=()=>$('copy-dialog').close();
 async function request(route,body){
  if(!connection)throw Error('管理连接尚未就绪，请用“更新并打开记录.cmd”打开台账。');
  const response=await fetch(connection.url+route,{method:body?'POST':'GET',headers:{'X-Skill-Ledger-Token':connection.token,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
  const value=await response.json();if(!response.ok)throw Error(value.error||'操作失败。');return value
 }
 function notice(text,error=false){$('manager-notice').hidden=false;$('manager-notice').textContent=text;$('manager-notice').classList.toggle('error',error)}
 function planReady(){const ack=$('remove-ack');$('remove-confirm').disabled=busy||!plan?.count||Boolean(ack&&!ack.checked)}
 function renderPlan(value,names){
  const body=$('remove-body');body.replaceChildren();const chosen=new Set(value.selected_names||names),extra=value.extra_names||value.groups.flatMap(g=>g.names).filter(n=>!chosen.has(n));
  body.append(make('p','remove-summary','已选 '+chosen.size+' 项 · 实际卸载 '+value.count+' 项'+(extra.length?' · 另含 '+extra.length+' 项连带技能':'')+(value.blocked.length?' · '+value.blocked.length+' 项不执行':'')));
  for(const group of value.groups){const section=make('section','remove-group');section.append(make('strong','',group.kind==='plugin'?'整个插件 · '+group.key.split('@')[0]:'本地技能'));
   for(const name of group.names){const row=make('div','remove-skill-row');row.append(make('span','remove-skill-name',removalName(name)),make('span','scope-tag'+(chosen.has(name)?'':' extra'),chosen.has(name)?'已选':'连带移除'));section.append(row)}
   section.append(make('p','impact-note',group.kind==='plugin'?'此操作同时卸载该插件及其连接能力。':'将移出安装目录；恢复备份保留在本机。'));body.append(section)
  }
  if(value.blocked.length){const section=make('section','blocked-group');section.append(make('strong','','以下项目不执行卸载'));for(const row of value.blocked){const line=make('div','blocked-item');line.append(make('span','remove-skill-name',removalName(row.name)),make('span','',row.reason));section.append(line)}body.append(section)}
  if(value.count&&(extra.length||value.groups.some(g=>g.kind==='plugin'))){const label=make('label','impact-ack'),input=make('input');input.type='checkbox';input.id='remove-ack';input.onchange=planReady;label.append(input,make('span','','我已核对以上范围，同意同时移除列出的插件及连带技能。'));body.append(label)}
  $('remove-confirm').textContent=value.count?'确认卸载 '+value.count+' 项':'没有可卸载项目';
 }
 function renderResult(result){
  const body=$('remove-body'),success=new Set(result.results.filter(r=>r.ok).flatMap(r=>r.names)),failed=new Set(result.results.filter(r=>!r.ok).flatMap(r=>r.names));
  body.replaceChildren(make('p','remove-summary','已卸载 '+success.size+' 项'+(failed.size?' · 失败 '+failed.size+' 项':'')+(result.blocked?.length?' · 未执行 '+result.blocked.length+' 项':'')));
  for(const group of result.results){const section=make('section','remove-group');for(const name of group.names){const row=make('div','remove-skill-row');row.append(make('span','remove-skill-name',removalName(name)),make('span','result-tag '+(group.ok?'success':'failure'),group.ok?'已卸载':'卸载失败'));section.append(row)}if(!group.ok)section.append(make('p','error-message',group.error||'未完成卸载，请重新检查。'));body.append(section)}
  if(result.blocked?.length){const section=make('section','blocked-group');for(const row of result.blocked)section.append(make('p','',removalName(row.name)+' · 未执行：'+row.reason));body.append(section)}
  for(const name of success)selection.delete(name);for(const row of result.blocked||[])selection.delete(row.name);return {success:success.size,failed:failed.size}
 }
 async function previewUninstall(names){
  if(busy||!names.length)return;state.scroll[state.view]=$('table-scroll').scrollTop;busy=true;plan=null;$('remove-title').textContent='核对卸载范围';$('remove-close').textContent='取消';$('remove-body').replaceChildren(make('p','','正在检查卸载范围…'));$('remove-confirm').disabled=true;$('remove-confirm').hidden=false;$('remove-confirm').textContent='正在检查…';syncSelection();
  if($('detail').open){state.detail=null;writeHistory(false);$('detail').close()}
  $('remove-dialog').showModal();
  try{plan=await request('/api/uninstall/preview',{names});renderPlan(plan,names);
  }catch(error){$('remove-body').replaceChildren(make('p','error-message',error.message));if(connection&&location.protocol==='file:'){const link=make('a','action-button','打开本机管理页面');link.href=connection.url+'/'+M.hash(state)+'&access='+encodeURIComponent(connection.token);$('remove-body').append(link)}}
  finally{busy=false;planReady();syncSelection()}
 }
 $('select-visible').onclick=()=>{if(busy)return;selection=M.toggleScope(selection,M.select(data,state).filter(M.installed).map(r=>r.name));syncSelection()};
 $('clear-selection').onclick=()=>{selection.clear();syncSelection()};
 $('bulk-remove').onclick=()=>previewUninstall([...selection]);
 $('remove-close').onclick=()=>{if(!busy)$('remove-dialog').close()};$('remove-dialog').addEventListener('cancel',event=>{if(busy)event.preventDefault()});
 $('remove-confirm').onclick=async()=>{
  if(!plan||busy||$('remove-confirm').disabled)return;busy=true;$('remove-title').textContent='正在卸载';$('remove-confirm').disabled=true;$('remove-confirm').textContent='正在卸载 '+plan.count+' 项…';$('remove-close').disabled=true;syncSelection();
  try{const result=await request('/api/uninstall/commit',{id:plan.id});const counts=renderResult(result);$('remove-title').textContent=counts.failed?'卸载结果：部分失败':'卸载结果';
   notice('已卸载 '+counts.success+' 项'+(counts.failed?'，失败 '+counts.failed+' 项，失败项仍保留勾选。':'，操作日志已更新。'),Boolean(counts.failed));
   try{window.SkillLedgerReceive(result.data||await request('/api/data'))}catch{notice('卸载已执行，清单暂未刷新；请刷新页面核对结果。',true)}
  }catch(error){$('remove-title').textContent='卸载结果待核对';$('remove-body').replaceChildren(make('p','error-message',error.message),make('p','impact-note','请求未正常完成，请刷新清单核对；不会自动重复卸载。'));notice('卸载结果待核对，请刷新清单。',true)}
  finally{busy=false;plan=null;$('remove-confirm').hidden=true;$('remove-close').disabled=false;$('remove-close').textContent='完成';render()}
 };
 $('skills-tab').onclick=()=>{if(state.view!=='skills')transition({type:'TAB',view:'skills'},true)};
 $('logs-tab').onclick=()=>{if(state.view!=='logs')transition({type:'TAB',view:'logs'},true)};
 $('reset').onclick=()=>transition({type:'CLEAR'});$('clear-exact').onclick=()=>transition({type:'FILTER',key:'name',value:''});
 $('detail-close').onclick=closeDetail;$('detail').addEventListener('cancel',event=>{event.preventDefault();closeDetail()});
 $('about-button').onclick=()=>$('about').showModal();$('about-close').onclick=()=>$('about').close();
 $('table-scroll').addEventListener('scroll',()=>{if(!rendering){state.scroll[state.view]=$('table-scroll').scrollTop;writeHistory(false,Boolean(state.detail))}});
 $('export').onclick=event=>{event.preventDefault();const blob=new Blob([M.csv(data,state)],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),link=make('a');link.href=url;link.download='技能台账-'+(state.view==='skills'?'技能清单':'操作日志')+'.csv';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)};
 window.addEventListener('popstate',event=>{state=M.normalize(event.state?.skillLedger?event.state.state:M.fromHash(location.hash,M.defaults()));headerSignature='';remember();render()});
 window.SkillLedgerReceive=next=>{
  if(!next||!Array.isArray(next.skills)||!Array.isArray(next.events))return;
  const before=new Set(data.skills.filter(M.installed).map(r=>r.name)),added=next.skills.filter(r=>r.installed&&!before.has(r.name));
  const changed=next.revision!==data.revision;data=prepare(next);
  if(next.monitor?.status?.includes('扫描失败'))notice('后台扫描未完成，当前显示上次成功的清单：'+(next.monitor.error||'请检查扫描范围。'),true);
  if(added.length)notice('发现 '+added.length+' 项新安装技能，已归入：'+[...new Set(added.map(M.scopeLabel))].join('、')+'。当前筛选可能隐藏新项目，可清空筛选查看。');
  if(changed){state.scroll[state.view]=$('table-scroll').scrollTop;headerSignature='';render()}else $('last-scan').textContent=timeText(data.updated)
 };
 function scanDetails(){
  const body=$('scan-body');body.replaceChildren();const info=data.discovery||{};
  body.append(make('p','usage-help','按安装目录归属分类。项目视图仅列本地安装，全局技能单独查看。数量随当前筛选变化。新技能约 15 秒检查，新项目目录约 30 秒发现。'));
  body.append(make('h3','','全局技能目录'));body.append(make('p','scan-path','用户 .agents/skills、Codex skills，以及已确认安装的插件。'));
  body.append(make('h3','','项目发现范围'));
  for(const root of info.roots||[])body.append(make('p','scan-path',typeof root==='string'?root:root.path));
  if(!info.roots?.length)body.append(make('p','usage-note','尚未添加项目扫描范围。请在下方添加项目或项目集合文件夹。'));
  body.append(make('p','usage-help','只在以上目录内查找 .agents/skills，默认最多 '+(info.depth||6)+' 层；跳过依赖、缓存和链接目录。范围以外的新项目需在下方添加。'));
  if(info.checked_epoch)body.append(make('p','usage-help','最近项目检查：'+new Date(info.checked_epoch*1000).toLocaleString('zh-CN')));
  for(const warning of info.warnings||[])body.append(make('p','usage-note',warning));
 }
 async function refreshScope(route,body){
  const refresh=$('scan-refresh'),add=$('scan-add');refresh.disabled=true;add.disabled=true;$('scan-status').textContent='正在检查项目与技能…';
  try{const result=await request(route,body);window.SkillLedgerReceive(result.data);scanDetails();$('scan-status').textContent='检查完成，清单已同步。';if(route==='/api/projects')$('scan-path').value=''}
  catch(error){$('scan-status').textContent=error.message}
  finally{refresh.disabled=false;add.disabled=false}
 }
 if($('scan-button')){
  $('scan-button').onclick=()=>{scanDetails();$('scan-status').textContent='';$('scan-dialog').showModal()};$('scan-close').onclick=()=>$('scan-dialog').close();
  $('scan-refresh').onclick=()=>refreshScope('/api/scan/refresh',{});
  $('scan-add').onclick=()=>{const path=$('scan-path').value.trim();if(!path){$('scan-status').textContent='先填写项目文件夹绝对路径。';return}refreshScope('/api/projects',{path,collection:Boolean($('scan-collection')?.checked)})};
 }
 window.SkillLedgerConnect=value=>{if(value&&/^http:\/\/127\.0\.0\.1:\d+$/.test(value.url)&&typeof value.token==='string')connection=value};
 function poll(){if(connection){request('/api/data').then(window.SkillLedgerReceive).catch(()=>{if(location.protocol==='http:')notice('后台连接中断，请重新打开台账。',true);else connection=null});return}if(location.protocol==='http:')return;for(const file of ['connection.js','live-data.js']){const script=make('script');script.src='.data/'+file+'?t='+Date.now();script.onload=()=>script.remove();script.onerror=()=>script.remove();document.head.append(script)}}
 writeHistory(false,false);render();if(!window.__SKILL_LEDGER_TEST__){poll();setInterval(poll,15000);window.addEventListener('focus',poll)}
 if(window.__SKILL_LEDGER_TEST__)window.__ledgerTest={getState:()=>M.normalize(state),select:()=>M.select(data,state),dispatch:transition};
})();
