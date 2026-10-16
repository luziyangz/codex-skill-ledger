const vm=require('node:vm');
function environment(data,initialHash='',appSource,fetcher=undefined,overrides={}){
 const listeners={},saved=new Map(),downloads=[],blobs=new Map();let nextURL=0;
 class Element{
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.parentNode=null;this.attributes={};this.dataset={};this.style={};this.className='';this.id='';this._text='';this._value='';this.scrollTop=0;this.hidden=false;this.open=false;this.selectionStart=0;this.selectionEnd=0;this.listeners={};this.classList={toggle:(name,on)=>{const set=new Set(this.className.split(' ').filter(Boolean));if(on)set.add(name);else set.delete(name);this.className=[...set].join(' ')}}}
  set textContent(text){this.replaceChildren();this._text=String(text)}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('')}
  append(...nodes){for(const child of nodes){if(child.parentNode)child.remove();child.parentNode=this;this.children.push(child)}}
  prepend(...nodes){for(const child of [...nodes].reverse()){if(child.parentNode)child.remove();child.parentNode=this;this.children.unshift(child)}}
  replaceChildren(...nodes){for(const child of this.children)child.parentNode=null;this.children=[];this._text='';this.append(...nodes)}
  setAttribute(key,value){this.attributes[key]=String(value)}
  addEventListener(key,fn){(this.listeners[key]??=[]).push(fn)}
  fire(key,extra={}){const event={target:this,preventDefault(){},...extra};this['on'+key]?.(event);for(const fn of this.listeners[key]||[])fn(event)}
  focus(){document.activeElement=this}
  setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end}
  select(){this.selectionStart=0;this.selectionEnd=this.value.length}
  set value(value){this._value=String(value)}
  get value(){return this._value}
  showModal(){this.open=true}
  close(){this.open=false}
  remove(){if(this.parentNode){const siblings=this.parentNode.children;siblings.splice(siblings.indexOf(this),1);this.parentNode=null}}
  click(){if(this.tagName==='A'&&this.download)downloads.push({filename:this.download,blob:blobs.get(this.href)});this.fire('click')}
 }
 const document={body:new Element('body'),head:new Element('head'),activeElement:null,createElement:tag=>new Element(tag),createTextNode:text=>{const e=new Element('#text');e.textContent=text;return e},getElementById(id){const find=node=>node.id===id?node:node.children.map(find).find(Boolean);return find(document.body)||find(document.head)||null}};
 const ids=['data','head','columns','body','table-scroll','categories','skills-tab','logs-tab','exact-skill','exact-skill-name','clear-exact','filter-error','count','export','reset','detail','detail-title','detail-body','detail-close','skill-logs','locate-skill','about','about-button','about-close','last-scan','bulk-remove','detail-remove','remove-title','remove-body','remove-dialog','remove-confirm','remove-close','manager-notice','selection-tools','select-visible','select-installed','clear-selection','selection-summary','copy-dialog','copy-text','copy-close'];
 for(const id of ids){const node=new Element(id==='detail'||id==='about'?'dialog':id==='export'?'a':'div');node.id=id;document.body.append(node)}
 document.getElementById('data').textContent=JSON.stringify(data);
 const location={hash:initialHash,protocol:'file:',origin:'null'},stack=[],history={index:-1,get state(){return stack[this.index]?.state},replaceState(value,title,hash){const entry={state:structuredClone(value),hash};if(this.index<0){this.index=0;stack.push(entry)}else stack[this.index]=entry;location.hash=hash},pushState(value,title,hash){stack.splice(this.index+1);stack.push({state:structuredClone(value),hash});this.index++;location.hash=hash},back(){if(this.index>0){this.index--;location.hash=stack[this.index].hash;for(const fn of listeners.popstate||[])fn({state:this.state})}}};
 const window={__SKILL_LEDGER_TEST__:true,addEventListener(key,fn){(listeners[key]??=[]).push(fn)}};
 const context={document,window,location,history,localStorage:{getItem:key=>saved.get(key)||null,setItem:(key,value)=>saved.set(key,value)},URLSearchParams,Blob,URL:{createObjectURL:blob=>{const id='blob:test/'+nextURL++;blobs.set(id,blob);return id},revokeObjectURL:()=>{}},Option:function(label,value){const node=new Element('option');node.textContent=label;node.value=value;return node},setTimeout:()=>{},setInterval:()=>{},console};
 context.sessionStorage=context.localStorage;context.fetch=fetcher;
 Object.assign(context,overrides);
 vm.runInNewContext(appSource,context,{filename:'skill-ledger-app.js'});
 return {get:id=>document.getElementById(id),window,history,location,downloads,api:window.__ledgerTest};
}

module.exports={environment};
