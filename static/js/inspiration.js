const ui=window.FacaiUI||{};
const escHtml=ui.escHtml||function(v){return String(v==null?'':v).replace(/[&<>"']/g,function(ch){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];});};
const toast=ui.toast||function(message){alert(message);};
const copyText=ui.copyText||function(text){return navigator.clipboard.writeText(text);};
let chatHistory=[];
const INSPIRATION_HISTORY_KEY='facai.inspiration.conversations.v1';
const MAX_CONVERSATIONS=24;
const MAX_MESSAGES_PER_CONVERSATION=60;
const CONVERSATION_RETENTION_MS=30*24*60*60*1000;
let conversations=[];
let activeConversationId='';
let activeInspirationMode='chat';
let productContextAlways=false;
let webSearchAlways=false;
let selectedAttachments=[];
let inspirationModelInterfaces={};
let inspirationModelConfigLoaded=false;
let archiveSectionOpen=false;
let activeConversationMenuId='';
let activeConversationMenuArchived=false;
let activeInspirationRequest=null;
const INSPIRATION_MODE_LABELS={chat:'AI 对话',thinking:'思考模式',seedance:'分镜提示词生成',research:'深入研究',analysis:'数据分析'};
const INSPIRATION_MODE_INTERFACE_KEYS={chat:'inspiration_chat',thinking:'inspiration_tools',seedance:'script_creation',research:'inspiration_tools',analysis:'inspiration_tools'};
const INSPIRATION_PLACEHOLDERS={
 chat:'问点什么，例如：帮我想一个奶冻粉的短视频脚本方向...',
 thinking:'问点什么，例如：帮我认真分析这场活动怎么做...',
 research:'问点什么，例如：研究一下烘焙短视频趋势...',
 analysis:'问点什么，例如：分析这份投放数据...',
 seedance:'粘贴脚本，或上传脚本文件后填写生成要求...'
};
const fallbackIconPaths={
 'archive':'<rect width="20" height="5" x="2" y="3" rx="1"></rect><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"></path><path d="M10 12h4"></path>',
 'archive-restore':'<rect width="20" height="5" x="2" y="3" rx="1"></rect><path d="M4 8v11a2 2 0 0 0 2 2h6"></path><path d="M10 12h4"></path><path d="m16 16 3-3 3 3"></path><path d="M19 13v8"></path>',
 'bot':'<path d="M12 8V4H8"></path><rect width="16" height="12" x="4" y="8" rx="2"></rect><path d="M2 14h2"></path><path d="M20 14h2"></path><path d="M15 13v2"></path><path d="M9 13v2"></path>',
 'brain-circuit':'<path d="M12 5a3 3 0 1 0-5.8 1.1"></path><path d="M12 5a3 3 0 1 1 5.8 1.1"></path><path d="M7 20a4 4 0 0 1-1.9-7.5"></path><path d="M17 20a4 4 0 0 0 1.9-7.5"></path><path d="M12 5v14"></path><path d="M8 12h8"></path><path d="M9 16h6"></path>',
 'chart-no-axes-column':'<path d="M5 21V10"></path><path d="M12 21V3"></path><path d="M19 21v-6"></path>',
 'chevron-down':'<path d="m6 9 6 6 6-6"></path>',
 'clapperboard':'<path d="M20.2 6 3 11l-.9-3.2a2 2 0 0 1 1.4-2.5l12.6-3.4a2 2 0 0 1 2.5 1.4Z"></path><path d="m6.2 5.3 3.1 3.9"></path><path d="m12.4 3.7 3.1 4"></path><path d="M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"></path>',
 'ellipsis':'<circle cx="12" cy="12" r="1"></circle><circle cx="19" cy="12" r="1"></circle><circle cx="5" cy="12" r="1"></circle>',
 'file-text':'<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"></path><path d="M14 2v4a2 2 0 0 0 2 2h4"></path><path d="M10 9H8"></path><path d="M16 13H8"></path><path d="M16 17H8"></path>',
 'globe-2':'<path d="M21.54 15H17a2 2 0 0 0-2 2v4.54"></path><path d="M7 3.34V5a3 3 0 0 0 3 3"></path><path d="M11 21.95V18a2 2 0 0 0-2-2H2.46"></path><circle cx="12" cy="12" r="10"></circle>',
 'image':'<rect width="18" height="18" x="3" y="3" rx="2"></rect><circle cx="9" cy="9" r="2"></circle><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"></path>',
 'package-search':'<path d="m7.5 4.27 9 5.15"></path><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l4 2.29"></path><path d="M12 22v-9"></path><path d="m3.3 7 8.7 5 8.7-5"></path><circle cx="17" cy="17" r="3"></circle><path d="m21 21-1.9-1.9"></path>',
 'paperclip':'<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path>',
 'pin':'<path d="M12 17v5"></path><path d="M9 10.76 4.5 15.25"></path><path d="M14.5 4.5 9 10l5 5 5.5-5.5"></path><path d="m14 4 6 6"></path>',
 'plus':'<path d="M5 12h14"></path><path d="M12 5v14"></path>',
 'search':'<circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path>',
 'send-horizontal':'<path d="m3 3 3 9-3 9 19-9Z"></path><path d="M6 12h16"></path>',
 'sparkles':'<path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.14-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.14a.5.5 0 0 1 .96 0l1.58 6.14a2 2 0 0 0 1.44 1.44l6.14 1.58a.5.5 0 0 1 0 .96l-6.14 1.58a2 2 0 0 0-1.44 1.44l-1.58 6.14a.5.5 0 0 1-.96 0z"></path><path d="M20 3v4"></path><path d="M22 5h-4"></path><path d="M4 17v2"></path><path d="M5 18H3"></path>',
 'trash-2':'<path d="M3 6h18"></path><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><path d="m19 6-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path><path d="M10 11v6"></path><path d="M14 11v6"></path>',
 'user':'<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle>',
 'x':'<path d="M18 6 6 18"></path><path d="m6 6 12 12"></path>'
};
function fallbackIconSvg(name){
 const paths=fallbackIconPaths[name];
 return paths?'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+paths+'</svg>':'';
}
function renderIcons(){
 if(window.lucide){window.lucide.createIcons();return;}
 document.querySelectorAll('i[data-lucide]').forEach(function(icon){
  const svg=fallbackIconSvg(icon.getAttribute('data-lucide'));
  if(svg)icon.outerHTML=svg;
 });
}
function createConversation(messages){
 const now=Date.now();
 return {id:'conv-'+now+'-'+Math.random().toString(36).slice(2,8),title:'新对话',messages:Array.isArray(messages)?messages:[],updatedAt:now,pinned:false,archived:false};
}
function sanitizeProduct(product){
 if(!product||typeof product!=='object')return null;
 return {
  product_id:product.product_id==null?'':String(product.product_id),
  name:product.name==null?'':String(product.name),
  category:product.category==null?'':String(product.category),
  price:product.price
 };
}
function sanitizeAttachment(attachment){
 if(!attachment||typeof attachment!=='object')return null;
 const filename=String(attachment.filename||'附件').trim()||'附件';
 const kind=attachment.kind==='image'?'image':'text';
 return {
  filename:filename,
  file_type:String(attachment.file_type||'file').trim()||'file',
  text:String(attachment.text||''),
  char_count:Number(attachment.char_count)||String(attachment.text||'').length,
  kind:kind,
  attachment_id:String(attachment.attachment_id||''),
  mime_type:String(attachment.mime_type||''),
  preview_url:String(attachment.preview_url||'')
 };
}
function sanitizeSource(source){
 if(!source||typeof source!=='object')return null;
 const title=String(source.title||'外网资料').trim()||'外网资料';
 const url=String(source.url||'').trim();
 if(!url)return null;
 return {title:title,url:url,snippet:String(source.snippet||'')};
}
function sanitizeAgentTraceStep(step){
 if(!step||typeof step!=='object')return null;
 const label=String(step.label||step.tool||'工具').trim()||'工具';
 return {
  tool:String(step.tool||'').trim(),
  label:label,
  status:String(step.status||'success').trim()||'success',
  summary:String(step.summary||'').trim()
 };
}
function sanitizeMessage(message){
 if(!message||typeof message!=='object')return null;
 const role=message.role==='assistant'?'assistant':'user';
 const content=String(message.content==null?'':message.content);
 if(!content.trim())return null;
 const products=Array.isArray(message.products)?message.products.map(sanitizeProduct).filter(Boolean).slice(0,6):[];
 const attachments=Array.isArray(message.attachments)?message.attachments.map(sanitizeAttachment).filter(Boolean).slice(0,6):[];
 const sources=Array.isArray(message.sources)?message.sources.map(sanitizeSource).filter(Boolean).slice(0,6):[];
 const rawAgentTrace=Array.isArray(message.agentTrace)?message.agentTrace:(Array.isArray(message.agent_trace)?message.agent_trace:[]);
 const agentTrace=rawAgentTrace.map(sanitizeAgentTraceStep).filter(Boolean).slice(0,6);
 return {role:role,content:content,products:products,attachments:attachments,sources:sources,reasoning:String(message.reasoning||''),agentTrace:agentTrace};
}
function deriveConversationTitle(messages){
 const firstUser=(messages||[]).find(function(message){return message.role==='user'&&message.content;});
 const clean=String(firstUser?firstUser.content:'新对话').replace(/\s+/g,' ').trim()||'新对话';
 return clean.length>22?clean.slice(0,22)+'...':clean;
}
function sanitizeConversation(raw){
 if(!raw||typeof raw!=='object')return null;
 const messages=Array.isArray(raw.messages)?raw.messages.map(sanitizeMessage).filter(Boolean).slice(-MAX_MESSAGES_PER_CONVERSATION):[];
 if(!messages.length)return null;
 const title=String(raw.title||deriveConversationTitle(messages)).replace(/\s+/g,' ').trim()||deriveConversationTitle(messages);
 const updatedAt=Number(raw.updatedAt)||Date.now();
 return {id:String(raw.id||('conv-'+updatedAt)),title:title,messages:messages,updatedAt:updatedAt,pinned:Boolean(raw.pinned),archived:Boolean(raw.archived)};
}
function currentConversation(){
 return conversations.find(function(conversation){return conversation.id===activeConversationId;})||null;
}
function setHistoryDrawer(open){
 const side=document.querySelector('.inspiration-side');
 const backdrop=document.getElementById('historyDrawerBackdrop');
 const toggle=document.getElementById('historyDrawerToggle');
 if(!side||!backdrop||!toggle)return;
 side.classList.toggle('is-open',Boolean(open));
 backdrop.classList.toggle('is-open',Boolean(open));
 toggle.setAttribute('aria-expanded',open?'true':'false');
}
function toggleHistoryDrawer(){
 const side=document.querySelector('.inspiration-side');
 setHistoryDrawer(!(side&&side.classList.contains('is-open')));
}
function syncChatHistoryFromActive(){
 const conversation=currentConversation();
 chatHistory=conversation?conversation.messages.map(function(message){return {role:message.role,content:message.content};}).slice(-12):[];
}
function sortConversations(){
 conversations.sort(function(a,b){
  if(Boolean(a.pinned)!==Boolean(b.pinned))return a.pinned?-1:1;
  return Number(b.updatedAt||0)-Number(a.updatedAt||0);
 });
}
function saveConversations(){
 try{
  const cutoff=Date.now()-CONVERSATION_RETENTION_MS;
  const stored=conversations.filter(function(conversation){return conversation.messages&&conversation.messages.length&&Number(conversation.updatedAt)>=cutoff;}).slice(0,MAX_CONVERSATIONS);
  localStorage.setItem(INSPIRATION_HISTORY_KEY,JSON.stringify(stored));
 }catch(error){}
}
function loadConversations(){
 try{
  const raw=JSON.parse(localStorage.getItem(INSPIRATION_HISTORY_KEY)||'[]');
  const cutoff=Date.now()-CONVERSATION_RETENTION_MS;
  conversations=(Array.isArray(raw)?raw:[]).map(sanitizeConversation).filter(function(conversation){return conversation&&Number(conversation.updatedAt)>=cutoff;}).slice(0,MAX_CONVERSATIONS);
 }catch(error){
  conversations=[];
 }
 sortConversations();
 const firstVisible=conversations.find(function(conversation){return !conversation.archived;});
 if(firstVisible){
  activeConversationId=firstVisible.id;
 }else{
  const conversation=createConversation();
  conversations=[conversation];
  activeConversationId=conversation.id;
 }
 syncChatHistoryFromActive();
}
function ensureActiveConversation(){
 let conversation=currentConversation();
 if(conversation&&!conversation.archived)return conversation;
 conversation=createConversation();
 conversations.unshift(conversation);
 activeConversationId=conversation.id;
 syncChatHistoryFromActive();
 return conversation;
}
function formatConversationMeta(conversation){
 const count=conversation.messages.length;
 const timestamp=Number(conversation.updatedAt)||Date.now();
 const diff=Date.now()-timestamp;
 let time='刚刚';
 if(diff>=86400000){
  const date=new Date(timestamp);
  time=(date.getMonth()+1)+'/'+date.getDate();
 }else if(diff>=3600000){
  time=Math.floor(diff/3600000)+' 小时前';
 }else if(diff>=60000){
  time=Math.floor(diff/60000)+' 分钟前';
 }
 return time+' · '+count+' 条';
}
function conversationDisplayTitle(conversation){
 return conversation.title||deriveConversationTitle(conversation.messages);
}
function renderConversationMenu(conversation,isArchived){
 if(isArchived){
  return '<button class="conversation-menu-item" type="button" data-conversation-action="restore" data-conversation-action-id="'+escHtml(conversation.id)+'" role="menuitem"><i data-lucide="archive-restore"></i>恢复</button><button class="conversation-menu-item danger" type="button" data-conversation-action="delete" data-conversation-action-id="'+escHtml(conversation.id)+'" role="menuitem"><i data-lucide="trash-2"></i>删除</button>';
 }
 const pinText=conversation.pinned?'取消置顶':'置顶';
 return '<button class="conversation-menu-item" type="button" data-conversation-action="pin" data-conversation-action-id="'+escHtml(conversation.id)+'" role="menuitem"><i data-lucide="pin"></i>'+pinText+'</button><button class="conversation-menu-item" type="button" data-conversation-action="archive" data-conversation-action-id="'+escHtml(conversation.id)+'" role="menuitem"><i data-lucide="archive"></i>归档</button><button class="conversation-menu-item danger" type="button" data-conversation-action="delete" data-conversation-action-id="'+escHtml(conversation.id)+'" role="menuitem"><i data-lucide="trash-2"></i>删除</button>';
}
function renderConversationCard(conversation,isArchived){
 const active=!isArchived&&conversation.id===activeConversationId?' is-active':'';
 const pinned=conversation.pinned?' is-pinned':'';
 const archived=isArchived?' is-archived':'';
 const title=conversationDisplayTitle(conversation);
 const pinButton=conversation.pinned?'<button class="conversation-action conversation-action-pin" type="button" data-conversation-action="pin" data-conversation-action-id="'+escHtml(conversation.id)+'" aria-label="取消置顶" title="取消置顶"><i data-lucide="pin"></i></button>':'<button class="conversation-action conversation-action-pin" type="button" data-conversation-action="pin" data-conversation-action-id="'+escHtml(conversation.id)+'" aria-label="置顶对话" title="置顶对话"><i data-lucide="pin"></i></button>';
 const menuButton='<span class="conversation-menu-wrap"><button class="conversation-action conversation-menu-button" type="button" data-conversation-action="menu" data-conversation-action-id="'+escHtml(conversation.id)+'" data-conversation-archived="'+(isArchived?'true':'false')+'" aria-haspopup="menu" aria-expanded="false" aria-label="更多对话操作" title="更多"><i data-lucide="ellipsis"></i></button></span>';
 const actions=isArchived?menuButton:pinButton+menuButton;
 return '<div class="conversation-item'+active+pinned+archived+'" role="'+(isArchived?'group':'button')+'" '+(isArchived?'':'tabindex="0" ')+'data-conversation-id="'+escHtml(conversation.id)+'" title="'+escHtml(title+' · '+formatConversationMeta(conversation))+'"><span class="conversation-row"><span class="conversation-title">'+escHtml(title)+'</span></span><span class="conversation-actions">'+actions+'</span></div>';
}
function resetConversationMenuButtons(){
 document.querySelectorAll('.conversation-menu-button[aria-expanded="true"]').forEach(function(button){button.setAttribute('aria-expanded','false');});
}
function hideConversationMenu(){
 const menu=document.getElementById('conversationFloatingMenu');
 if(!menu)return;
 menu.hidden=true;
 menu.classList.remove('is-open');
 menu.innerHTML='';
 activeConversationMenuId='';
 activeConversationMenuArchived=false;
 resetConversationMenuButtons();
}
function positionConversationMenu(anchor,menu){
 if(!anchor||!menu)return;
 const rect=anchor.getBoundingClientRect();
 const gap=8;
 const menuWidth=menu.offsetWidth||154;
 const menuHeight=menu.offsetHeight||120;
 let left=rect.right+gap;
 if(left+menuWidth>window.innerWidth-gap)left=Math.max(gap,rect.left-menuWidth-gap);
 let top=rect.top-6;
 if(top+menuHeight>window.innerHeight-gap)top=Math.max(gap,window.innerHeight-menuHeight-gap);
 menu.style.left=left+'px';
 menu.style.top=top+'px';
}
function showConversationMenu(id,isArchived,anchor,event){
 if(event){event.stopPropagation();event.preventDefault();}
 const menu=document.getElementById('conversationFloatingMenu');
 const conversation=conversations.find(function(item){return item.id===id;});
 if(!menu||!conversation)return;
 if(!menu.hidden&&activeConversationMenuId===id&&activeConversationMenuArchived===Boolean(isArchived)){
  hideConversationMenu();
  return;
 }
 resetConversationMenuButtons();
 activeConversationMenuId=id;
 activeConversationMenuArchived=Boolean(isArchived);
 menu.innerHTML=renderConversationMenu(conversation,isArchived);
 menu.hidden=false;
 menu.classList.add('is-open');
 if(anchor)anchor.setAttribute('aria-expanded','true');
 bindConversationActionButtons(menu);
 positionConversationMenu(anchor,menu);
 renderIcons();
}
function hideConversationMenuOnOutsideClick(event){
 const menu=document.getElementById('conversationFloatingMenu');
 if(!menu||menu.hidden)return;
 if(menu.contains(event.target))return;
 if(event.target.closest&&event.target.closest('.conversation-menu-button'))return;
 hideConversationMenu();
}
function bindConversationActionButtons(root){
 if(!root)return;
 root.querySelectorAll('[data-conversation-action]').forEach(function(button){
  button.addEventListener('click',function(event){
   const id=button.getAttribute('data-conversation-action-id')||'';
   const action=button.getAttribute('data-conversation-action')||'';
   if(action==='menu')return showConversationMenu(id,button.getAttribute('data-conversation-archived')==='true',button,event);
   hideConversationMenu();
   if(action==='pin')return toggleConversationPin(id,event);
   if(action==='archive')return archiveConversation(id,event);
   if(action==='restore')return restoreConversation(id,event);
   if(action==='delete')return deleteConversation(id,event);
  });
 });
}
function bindConversationList(root,allowSelect){
 if(!root)return;
 if(allowSelect){
  root.querySelectorAll('.conversation-item[data-conversation-id]').forEach(function(item){
   item.addEventListener('click',function(event){
    if(event.target.closest('[data-conversation-action]'))return;
    selectConversation(item.getAttribute('data-conversation-id')||'');
   });
   item.addEventListener('keydown',function(event){
    if(event.key==='Enter'||event.key===' '){
     event.preventDefault();
     selectConversation(item.getAttribute('data-conversation-id')||'');
    }
   });
  });
 }
 bindConversationActionButtons(root);
}
function renderConversationHistory(){
 hideConversationMenu();
 const list=document.getElementById('conversationHistoryList');
 if(!list)return;
 const archivedList=document.getElementById('archivedConversationList');
 const archiveToggle=document.getElementById('conversationArchiveToggle');
 const archiveCount=document.getElementById('archivedConversationCount');
 sortConversations();
 const visible=conversations.filter(function(conversation){return conversation.messages&&conversation.messages.length&&!conversation.archived;});
 const archived=conversations.filter(function(conversation){return conversation.messages&&conversation.messages.length&&conversation.archived;});
 if(!visible.length){
  list.innerHTML='<div class="conversation-empty">暂无历史对话<br>开始提问后会自动保存。</div>';
 }else{
  list.innerHTML=visible.map(function(conversation){return renderConversationCard(conversation,false);}).join('');
  bindConversationList(list,true);
 }
 if(archiveCount)archiveCount.textContent=archived.length;
 if(archiveToggle)archiveToggle.setAttribute('aria-expanded',archiveSectionOpen?'true':'false');
 if(archivedList){
  archivedList.hidden=!archiveSectionOpen;
  archivedList.innerHTML=archiveSectionOpen?(archived.length?archived.map(function(conversation){return renderConversationCard(conversation,true);}).join(''):'<div class="conversation-empty">暂无归档对话</div>'):'';
  bindConversationList(archivedList,false);
 }
 renderIcons();
}
function toggleArchiveSection(){
 archiveSectionOpen=!archiveSectionOpen;
 renderConversationHistory();
}
function setModelPillLabel(text){
 const labelText=String(text||'AI 对话');
 const modelPill=document.getElementById('modelPill');
 const label=document.querySelector('#modelPill span');
 if(label)label.textContent=labelText;
 if(modelPill)modelPill.title=labelText;
}
function modelPillModeLabel(mode){
 return INSPIRATION_MODE_LABELS[mode]||INSPIRATION_MODE_LABELS.chat;
}
function interfaceConfigForMode(mode){
 const key=INSPIRATION_MODE_INTERFACE_KEYS[mode]||INSPIRATION_MODE_INTERFACE_KEYS.chat;
 return inspirationModelInterfaces[key]||null;
}
function modelPillTextForMode(mode,overrideModel,productContextUsed){
 const label=modelPillModeLabel(mode);
 const config=interfaceConfigForMode(mode);
 const provider=config&&(config.provider_label||config.provider)?(config.provider_label||config.provider):'';
 const model=overrideModel||(config&&(config.display_model||config.model))||'';
 const parts=[label];
 if(provider)parts.push(provider);
 parts.push(model||(inspirationModelConfigLoaded?'模型未配置':'模型读取中'));
 if(isProductContextAlways()&&mode!=='seedance')parts.push('基于产品资料');
 if(isWebSearchAlways()&&mode!=='seedance')parts.push('联网搜索');
 return parts.join(' · ');
}
function updateModelPillForMode(mode,overrideModel,productContextUsed){
 setModelPillLabel(modelPillTextForMode(mode||getActiveInspirationMode(),overrideModel,productContextUsed));
}
async function loadInspirationModelConfig(){
 try{
  const response=await fetch('/api/ai-config/interfaces');
  const data=await response.json();
  if(!response.ok)throw new Error(data.detail||data.message||'模型配置读取失败');
  inspirationModelInterfaces={};
  (data.interfaces||[]).forEach(function(item){
   if(item&&item.interface_key)inspirationModelInterfaces[item.interface_key]=item;
  });
  inspirationModelConfigLoaded=true;
 }catch(error){
  inspirationModelConfigLoaded=false;
 }finally{
  updateModelPillForMode(getActiveInspirationMode());
 }
}
function renderConversation(){
 const conversation=ensureActiveConversation();
 if(!conversation.messages.length){
  renderWelcome();
  return;
 }
 const thread=document.getElementById('inspirationThread');
 thread.innerHTML='';
 conversation.messages.forEach(function(message){
  appendMessage(message.role,message.content,{products:message.products,attachments:message.attachments,reasoning:message.reasoning,sources:message.sources,agentTrace:message.agentTrace,scroll:'none'});
 });
 thread.scrollTop=thread.scrollHeight;
 const hasProductContext=conversation.messages.some(function(message){return message.products&&message.products.length;});
 updateModelPillForMode(getActiveInspirationMode(),null,hasProductContext);
 renderIcons();
}
function selectConversation(id){
 if(!id)return;
 if(id===activeConversationId){setHistoryDrawer(false);return;}
 const conversation=conversations.find(function(item){return item.id===id;});
 if(!conversation||conversation.archived)return;
 activeConversationId=conversation.id;
 syncChatHistoryFromActive();
 renderConversation();
 renderConversationHistory();
 setHistoryDrawer(false);
}
function stopConversationAction(event){
 if(event){event.stopPropagation();event.preventDefault();}
}
function selectNextAvailableConversation(){
 sortConversations();
 const next=conversations.find(function(conversation){return conversation.messages&&conversation.messages.length&&!conversation.archived;});
 if(next){
  activeConversationId=next.id;
  syncChatHistoryFromActive();
  renderConversation();
  renderConversationHistory();
  return;
 }
 const conversation=createConversation();
 conversations.unshift(conversation);
 activeConversationId=conversation.id;
 syncChatHistoryFromActive();
 renderWelcome();
 renderConversationHistory();
 saveConversations();
}
function toggleConversationPin(id,event){
 stopConversationAction(event);
 const conversation=conversations.find(function(item){return item.id===id;});
 if(!conversation||conversation.archived)return;
 conversation.pinned=!conversation.pinned;
 sortConversations();
 saveConversations();
 renderConversationHistory();
}
function archiveConversation(id,event){
 stopConversationAction(event);
 const conversation=conversations.find(function(item){return item.id===id;});
 if(!conversation)return;
 const wasActive=conversation.id===activeConversationId;
 conversation.archived=true;
 conversation.pinned=false;
 sortConversations();
 saveConversations();
 if(wasActive){
  selectNextAvailableConversation();
 }else{
  renderConversationHistory();
 }
}
function restoreConversation(id,event){
 stopConversationAction(event);
 const conversation=conversations.find(function(item){return item.id===id;});
 if(!conversation)return;
 conversation.archived=false;
 sortConversations();
 saveConversations();
 renderConversationHistory();
}
function deleteConversation(id,event){
 stopConversationAction(event);
 if(!confirm('删除这条对话？此操作不可恢复。'))return;
 const wasActive=id===activeConversationId;
 conversations=conversations.filter(function(conversation){return conversation.id!==id;});
 saveConversations();
 if(wasActive){
  selectNextAvailableConversation();
 }else{
  renderConversationHistory();
 }
}
function addConversationMessage(role,content,extras){
 const conversation=ensureActiveConversation();
 const message=sanitizeMessage({role:role,content:content,products:extras&&extras.products,attachments:extras&&extras.attachments,reasoning:extras&&extras.reasoning,sources:extras&&extras.sources,agentTrace:extras&&extras.agentTrace});
 if(!message)return null;
 conversation.messages.push(message);
 conversation.messages=conversation.messages.slice(-MAX_MESSAGES_PER_CONVERSATION);
 conversation.title=deriveConversationTitle(conversation.messages);
 conversation.updatedAt=Date.now();
 sortConversations();
 syncChatHistoryFromActive();
 saveConversations();
 renderConversationHistory();
 return message;
}
function startNewConversation(){
 setHistoryDrawer(false);
 const current=currentConversation();
 if(current&&current.messages.length){
  const conversation=createConversation();
  conversations.unshift(conversation);
  activeConversationId=conversation.id;
 }else if(current){
  activeConversationId=current.id;
 }else{
  ensureActiveConversation();
 }
 syncChatHistoryFromActive();
 document.getElementById('inspirationInput').value='';
 resizeInspirationInput();
 selectedAttachments=[];
 renderSelectedAttachments();
 updateModelPillForMode(getActiveInspirationMode());
 renderWelcome();
 renderConversationHistory();
 saveConversations();
 document.getElementById('inspirationInput').focus();
}
function clearCurrentConversation(){
 const conversation=ensureActiveConversation();
 conversation.messages=[];
 conversation.title='新对话';
 conversation.updatedAt=Date.now();
 syncChatHistoryFromActive();
 saveConversations();
 document.getElementById('inspirationInput').value='';
 resizeInspirationInput();
 selectedAttachments=[];
 renderSelectedAttachments();
 updateModelPillForMode(getActiveInspirationMode());
 renderWelcome();
 renderConversationHistory();
}
function renderWelcome(){
 const thread=document.getElementById('inspirationThread');
 const prompts=[
  ['新品开头','帮我想 5 个烘焙新品短视频开头'],
  ['低成本选题','给我 3 个低成本拍摄选题'],
  ['直播话术','把卖点改成更口语的直播话术'],
  ['促单文案','帮我做一版活动促单文案']
 ];
 thread.innerHTML='<div class="inspiration-empty"><div class="inspiration-empty-icon"><i data-lucide="sparkles"></i></div><h1>今天想聊点什么？</h1><p>可以直接问选题、脚本、标题、活动文案或拍摄方向。</p><div class="inspiration-empty-prompts">'+prompts.map(function(item){return '<button class="prompt-chip" type="button" data-prompt="'+escHtml(item[1])+'">'+escHtml(item[0])+'</button>';}).join('')+'</div></div>';
 thread.querySelectorAll('[data-prompt]').forEach(function(button){
  button.addEventListener('click',function(){usePrompt(button.getAttribute('data-prompt')||'');});
 });
 renderIcons();
}
function formatReferencePrice(value){
 const number=Number(value);
 if(!Number.isFinite(number))return '';
 return '¥'+(Math.round(number*100)/100).toString();
}
function renderReferenceProducts(products){
 if(!products||!products.length)return '';
 return '<div class="reference-products"><span class="reference-products-label">参考产品</span>'+products.slice(0,6).map(function(product){const meta=[product.category||'',formatReferencePrice(product.price)].filter(Boolean).join(' · ');return '<span class="reference-product-chip"><span>'+escHtml(product.name||'相关产品')+'</span>'+(meta?'<span class="reference-product-meta">'+escHtml(meta)+'</span>':'')+'</span>';}).join('')+'</div>';
}
function renderAttachmentVisual(attachment){
 if(attachment&&attachment.kind==='image'){
  const preview=String(attachment.preview_url||'').trim();
  if(preview)return '<img class="attachment-thumb" src="'+escHtml(preview)+'" alt="">';
  return '<i data-lucide="image"></i>';
 }
 return '<i data-lucide="file-text"></i>';
}
function renderMessageAttachments(attachments){
 if(!attachments||!attachments.length)return '';
 return '<div class="message-attachments">'+attachments.slice(0,6).map(function(attachment){return '<span class="message-attachment-chip">'+renderAttachmentVisual(attachment)+'<span>'+escHtml(attachment.filename||'附件')+'</span></span>';}).join('')+'</div>';
}
function renderReasoning(reasoning){
 if(!reasoning)return '';
 return '<details class="reasoning-block"><summary>思考过程</summary><div class="reasoning-body">'+escHtml(reasoning)+'</div></details>';
}
function renderAgentTrace(agentTrace){
 if(!agentTrace||!agentTrace.length)return '';
 const chips=agentTrace.slice(0,6).map(function(step){
  if(!step)return '';
  const label=String(step.label||step.tool||'工具').trim()||'工具';
  const summary=String(step.summary||'').trim();
  const status=String(step.status||'success').trim();
  const className='agent-trace-chip'+(status==='error'?' is-error':'');
  return '<span class="'+className+'" title="'+escHtml(summary)+'">'+escHtml(label)+'</span>';
 }).filter(Boolean).join('');
 if(!chips)return '';
 return '<div class="agent-trace"><span class="agent-trace-label">已使用</span>'+chips+'</div>';
}
function renderSources(sources){
 if(!sources||!sources.length)return '';
 return '<div class="source-list"><span class="source-label">外网参考</span>'+sources.slice(0,6).map(function(source,index){return '<a class="source-chip" href="'+escHtml(source.url||'#')+'" target="_blank" rel="noopener noreferrer">'+escHtml((index+1)+'. '+(source.title||'资料来源'))+'</a>';}).join('')+'</div>';
}
function renderGeneratedDocument(document){
 if(!document||!document.download_url)return '';
 return '<div class="generated-document-card"><div class="generated-document-title"><i data-lucide="file-text"></i><span>'+escHtml(document.title||document.filename||'Word 文档')+'</span></div><a class="generated-document-download" href="'+escHtml(document.download_url)+'" target="_blank" rel="noopener">下载 Word 文档</a></div>';
}
function getActiveInspirationMode(){
 return activeInspirationMode;
}
function isProductContextAlways(){
 return productContextAlways;
}
function isWebSearchAlways(){
 return webSearchAlways;
}
function getProductContextMode(){
 return isProductContextAlways()&&getActiveInspirationMode()!=='seedance'?'always':'off';
}
function getWebSearchMode(){
 return isWebSearchAlways()&&getActiveInspirationMode()!=='seedance'?'always':'auto';
}
function renderProductContextMode(){
 const button=document.getElementById('productContextToggle');
 if(!button)return;
 const active=isProductContextAlways();
 button.classList.toggle('is-active',active);
 button.setAttribute('aria-pressed',active?'true':'false');
 button.title=active?'已开启：回答会基于产品资料':'开启后，回答会基于产品资料';
}
function renderWebSearchMode(){
 const button=document.getElementById('webSearchToggle');
 if(!button)return;
 const active=isWebSearchAlways();
 button.classList.toggle('is-active',active);
 button.setAttribute('aria-pressed',active?'true':'false');
 button.title=active?(getActiveInspirationMode()==='seedance'?'已开启：分镜提示词生成不会叠加联网搜索':'已开启：回答会先联网检索公开信息'):'开启后，回答会先联网检索公开信息';
}
function toggleProductContextMode(){
 productContextAlways=!productContextAlways;
 renderProductContextMode();
 updateModelPillForMode(getActiveInspirationMode());
}
function toggleWebSearchMode(){
 webSearchAlways=!webSearchAlways;
 renderWebSearchMode();
 updateModelPillForMode(getActiveInspirationMode());
}
function renderInspirationMode(){
 document.querySelectorAll('.mode-button').forEach(function(button){
  const isActive=button.getAttribute('data-tool-mode')===activeInspirationMode;
  button.classList.toggle('is-active',isActive);
  button.setAttribute('aria-pressed',isActive?'true':'false');
 });
}
function updateInspirationPlaceholder(){
 const input=document.getElementById('inspirationInput');
 if(input)input.placeholder=INSPIRATION_PLACEHOLDERS[activeInspirationMode]||INSPIRATION_PLACEHOLDERS.chat;
}
function setInspirationMode(mode){
 activeInspirationMode=activeInspirationMode===mode?'chat':mode;
 renderInspirationMode();
 renderProductContextMode();
 renderWebSearchMode();
 updateModelPillForMode(activeInspirationMode);
 updateInspirationPlaceholder();
}
function renderSelectedAttachments(){
 const list=document.getElementById('attachmentList');
 if(!list)return;
 list.innerHTML=selectedAttachments.map(function(attachment,index){return '<span class="attachment-pill">'+renderAttachmentVisual(attachment)+'<span>'+escHtml(attachment.filename||'附件')+'</span><button type="button" onclick="removeSelectedAttachment('+index+')" aria-label="移除附件"><i data-lucide="x"></i></button></span>';}).join('');
 renderIcons();
}
function removeSelectedAttachment(index){
 selectedAttachments.splice(index,1);
 renderSelectedAttachments();
}
async function uploadInspirationFiles(files){
 const list=Array.prototype.slice.call(files||[]);
 if(!list.length)return;
 for(const file of list.slice(0,6-selectedAttachments.length)){
  const formData=new FormData();
  formData.append('file',file);
  try{
   const response=await fetch('/api/inspiration/attachments',{method:'POST',body:formData});
   const data=await response.json();
   if(!response.ok)throw new Error(data.detail||data.message||'附件解析失败');
   const attachment=sanitizeAttachment(data);
   if(attachment)selectedAttachments.push(attachment);
   toast('已读取附件：'+(data.filename||file.name),'success');
  }catch(error){
   toast((file.name||'附件')+'：'+(error&&error.message?error.message:'上传失败'),'error');
  }
 }
 renderSelectedAttachments();
}
function clipboardImageFiles(event){
 const items=event&&event.clipboardData&&event.clipboardData.items?Array.prototype.slice.call(event.clipboardData.items):[];
 return items.map(function(item,index){
  if(!item||item.kind!=='file')return null;
  if(item.type.indexOf('image/')===0){
  const file=item.getAsFile&&item.getAsFile();
  if(!file)return null;
  const rawType=file.type||item.type||'image/png';
  const ext=rawType.indexOf('webp')>=0?'webp':(rawType.indexOf('jpeg')>=0?'jpg':'png');
  const name=file.name&&file.name!=='image.png'?file.name:('clipboard-image-'+Date.now()+'-'+index+'.'+ext);
  try{
   return new File([file],name,{type:rawType});
  }catch(error){
   return file;
  }
  }
  return null;
 }).filter(Boolean);
}
function handleInspirationPaste(event){
 const files=clipboardImageFiles(event);
 if(!files.length)return;
 event.preventDefault();
 uploadInspirationFiles(files);
}
function scrollChatToMessage(message,mode){
 const thread=document.getElementById('inspirationThread');
 if(!thread||!message||mode==='none')return;
 if(mode==='top'){
  const top=Math.max(0,message.offsetTop-thread.offsetTop-14);
  thread.scrollTo({top:top,behavior:'smooth'});
  return;
 }
 thread.scrollTop=thread.scrollHeight;
}
function appendMessage(role,content,options){
 const thread=document.getElementById('inspirationThread');
 if(thread.querySelector('.inspiration-empty'))thread.innerHTML='';
 const msg=document.createElement('div');
 msg.className='chat-message '+(role==='user'?'user':'assistant');
 const safe=escHtml(content);
 const bodyHtml='<div class="message-content">'+safe+'</div>';
 const attachmentHtml=options?renderMessageAttachments(options.attachments):'';
 const reasoningHtml=role==='assistant'&&options?renderReasoning(options.reasoning):'';
 const agentTraceHtml=role==='assistant'&&options?renderAgentTrace(options.agentTrace):'';
 const references=role==='assistant'&&options?(options.referenceProductsHtml||renderReferenceProducts(options.products)):'';
 const sourceHtml=role==='assistant'&&options?renderSources(options.sources):'';
 const tools=role==='assistant'&&!(options&&options.thinking)?'<div class="message-tools"><button class="message-tool" type="button" onclick="copyAssistantMessage(this)">复制</button><button class="message-tool" type="button" onclick="generateAssistantDocument(this)">生成文档</button></div>':'';
 const bubbleContent=role==='user'?attachmentHtml+bodyHtml:bodyHtml+attachmentHtml+reasoningHtml+agentTraceHtml+references+sourceHtml+tools;
 msg.innerHTML=(role==='user'?'':'<span class="chat-avatar"><i data-lucide="bot"></i></span>')+'<div class="chat-bubble '+(options&&options.thinking?'thinking':'')+'">'+bubbleContent+'</div>'+(role==='user'?'<span class="chat-avatar"><i data-lucide="user"></i></span>':'');
 thread.appendChild(msg);
 const scrollMode=(options&&options.scroll)||((role==='assistant'&&!(options&&options.thinking))?'top':'bottom');
 scrollChatToMessage(msg,scrollMode);
 renderIcons();
 return msg;
}
function copyAssistantMessage(button){
 const bubble=button.closest('.chat-bubble');
 const text=bubble?bubble.childNodes[0].textContent:'';
 copyText(text).then(function(){toast('已成功复制到剪贴板','success');}).catch(function(){toast('复制失败，请手动选中文案复制','error');});
}
function findAssistantDocumentContext(answer){
 const conversation=currentConversation();
 const toDocumentHistory=function(items){
  return (items||[]).slice(-12).map(function(item){return {role:item.role,content:String(item.content||'').slice(0,4000)};});
 };
 const fallback={message:'',answer:answer,history:toDocumentHistory(chatHistory),attachments:[],products:[]};
 if(!conversation||!conversation.messages)return fallback;
 for(let index=conversation.messages.length-1;index>=0;index--){
  const message=conversation.messages[index];
  if(message.role==='assistant'&&message.content===answer){
   let previousUser=null;
   for(let cursor=index-1;cursor>=0;cursor--){
    if(conversation.messages[cursor].role==='user'){previousUser=conversation.messages[cursor];break;}
   }
   return {
    message:previousUser?previousUser.content:'',
    answer:answer,
    history:toDocumentHistory(conversation.messages.slice(Math.max(0,index-12),index+1)),
    attachments:previousUser&&previousUser.attachments?previousUser.attachments:[],
    products:message.products||[],
    title:previousUser?previousUser.content:''
   };
  }
 }
 return fallback;
}
function formatInspirationApiError(data,fallback){
 if(!data)return fallback||'请求失败';
 if(typeof data.detail==='string')return data.detail;
 if(Array.isArray(data.detail)){
  const first=data.detail[0]||{};
  if(first.msg)return first.msg;
  if(first.message)return first.message;
  return fallback||'请求参数有误，请检查内容后重试。';
 }
 if(data.detail&&typeof data.detail==='object'){
  if(data.detail.msg)return data.detail.msg;
  if(data.detail.message)return data.detail.message;
  return fallback||'请求参数有误，请检查内容后重试。';
 }
 if(data.message)return String(data.message);
 return fallback||'请求失败';
}
async function generateAssistantDocument(button){
 const bubble=button.closest('.chat-bubble');
 const answer=bubble?bubble.childNodes[0].textContent.trim():'';
 if(!bubble||!answer)return toast('暂无可生成文档的内容','error');
 const oldText=button.textContent;
 button.disabled=true;
 button.textContent='生成中...';
 try{
  const payload=findAssistantDocumentContext(answer);
  const response=await fetch('/api/inspiration/documents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const data=await response.json();
  if(!response.ok)throw new Error(formatInspirationApiError(data,'文档生成失败'));
  const existing=bubble.querySelector('.generated-document-card');
  if(existing)existing.remove();
  bubble.insertAdjacentHTML('beforeend',renderGeneratedDocument(data));
  toast('Word 文档已生成','success');
  renderIcons();
 }catch(error){
  toast(error&&error.message?error.message:'文档生成失败','error');
 }finally{
  button.disabled=false;
  button.textContent=oldText;
 }
}
function usePrompt(text){
 const input=document.getElementById('inspirationInput');
 input.value=text;
 resizeInspirationInput();
 input.focus();
}
function resizeInspirationInput(){
 const input=document.getElementById('inspirationInput');
 if(!input)return;
 input.style.height='auto';
 const computed=getComputedStyle(input);
 const minHeight=Number.parseFloat(computed.minHeight)||44;
 const maxHeight=Number.parseFloat(computed.maxHeight)||260;
 const nextHeight=Math.min(Math.max(input.scrollHeight,minHeight),maxHeight);
 input.style.height=nextHeight+'px';
 input.style.overflowY=input.scrollHeight>maxHeight?'auto':'hidden';
}
function submitOnEnter(event){
 if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();document.getElementById('inspirationSend').click();}
}
function setBusy(isBusy){
 document.getElementById('inspirationSend').disabled=isBusy;
 document.getElementById('inspirationInput').disabled=isBusy;
 document.querySelectorAll('.tool-button').forEach(function(button){button.disabled=isBusy;});
 const cancel=document.getElementById('inspirationCancelBtn');
 if(cancel){cancel.hidden=!isBusy;cancel.disabled=false;}
}
function cancelInspirationChat(){
 if(!activeInspirationRequest)return;
 document.getElementById('inspirationCancelBtn').disabled=true;
 activeInspirationRequest.abort('cancelled');
}
async function readInspirationSse(response,onEvent){
 if(!response.body||!response.body.getReader)throw new Error('stream-unavailable');
 const reader=response.body.getReader();
 const decoder=new TextDecoder('utf-8');
 let buffer='';
 async function emitBlock(block){
  if(!block.trim())return;
  let eventName='message';
  const dataLines=[];
  block.split(/\r?\n/).forEach(function(line){
   if(line.indexOf('event: ')===0)eventName=line.slice(7).trim();
   if(line.indexOf('data: ')===0)dataLines.push(line.slice(6));
  });
  if(!dataLines.length)return;
  let payload={};
  try{payload=JSON.parse(dataLines.join('\n'));}catch(error){payload={message:dataLines.join('\n')};}
  await onEvent(eventName,payload);
 }
 while(true){
  const result=await reader.read();
  buffer+=decoder.decode(result.value||new Uint8Array(),{stream:!result.done});
  const blocks=buffer.split(/\r?\n\r?\n/);
  buffer=blocks.pop()||'';
  for(const block of blocks)await emitBlock(block);
  if(result.done)break;
 }
 if(buffer.trim())await emitBlock(buffer);
}
async function fetchLegacyInspirationChat(payload,signal){
 const response=await fetch('/api/inspiration/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:signal});
 const data=await response.json();
 if(!response.ok)throw new Error(formatInspirationApiError(data,'发送失败'));
 return data;
}
function formatInspirationChatError(error){
 const message=error&&error.message?String(error.message):'网络错误';
 if(message.indexOf('Failed to fetch')>=0){
  return '连接后端失败或响应超时，请确认本地服务正在运行后重试。';
 }
 return message;
}
async function sendInspirationChat(event){
 event.preventDefault();
 const input=document.getElementById('inspirationInput');
 const message=input.value.trim();
 if(!message)return;
 ensureActiveConversation();
 const historyForRequest=chatHistory.slice();
 input.value='';
 resizeInspirationInput();
 const attachmentsForRequest=selectedAttachments.slice();
 appendMessage('user',message,{attachments:selectedAttachments});
 addConversationMessage('user',message,{attachments:selectedAttachments});
 selectedAttachments=[];
 renderSelectedAttachments();
 const loadingText=getActiveInspirationMode()==='seedance'?'正在生成分镜提示词...':'正在思考...';
 const loading=appendMessage('assistant',loadingText, {thinking:true});
 const streamContent=loading.querySelector('.message-content');
 const controller=new AbortController();
 activeInspirationRequest=controller;
 let partial='';
 let reasoningPartial='';
 let data={products:[],sources:[],attachments:[],agent_trace:[],reasoning:'',answer:'',model:'',tool_mode:getActiveInspirationMode(),product_context_used:false};
 const payload={message:message,history:historyForRequest,tool_mode:getActiveInspirationMode(),product_context_mode:getProductContextMode(),web_search_mode:getWebSearchMode(),attachments:attachmentsForRequest};
 setBusy(true);
 try{
  const response=await fetch('/api/inspiration/chat/stream',{method:'POST',headers:{'Content-Type':'application/json','Accept':'text/event-stream'},body:JSON.stringify(payload),signal:controller.signal});
  if(!response.ok){
   const errorData=await response.json().catch(function(){return {};});
   throw new Error(formatInspirationApiError(errorData,'发送失败'));
  }
  if(!response.body||!response.body.getReader){
   data=await fetchLegacyInspirationChat(payload,controller.signal);
   partial=data.answer||'';
  }else{
   await readInspirationSse(response,async function(eventName,eventData){
    if(eventName==='meta'){
     data.model=eventData.model||data.model;
     data.tool_mode=eventData.tool_mode||data.tool_mode;
     updateModelPillForMode(data.tool_mode,data.model,data.product_context_used);
    }else if(eventName==='context'){
     data.products=eventData.products||[];
     data.sources=eventData.sources||[];
     data.attachments=eventData.attachments||[];
     data.agent_trace=eventData.agent_trace||[];
     data.product_context_used=Boolean(eventData.product_context_used);
    }else if(eventName==='reasoning_delta'){
     reasoningPartial+=eventData.text||'';
    }else if(eventName==='delta'){
     partial+=eventData.text||'';
     streamContent.textContent=partial;
     loading.querySelector('.chat-bubble').classList.remove('thinking');
     scrollChatToMessage(loading,'bottom');
    }else if(eventName==='done'){
     data=Object.assign(data,eventData);
    }else if(eventName==='error'){
     if(eventData.partial&&!partial)partial=eventData.partial;
     throw new Error(eventData.message||'流式生成失败');
    }
   });
   data.answer=partial;
   data.reasoning=data.reasoning||reasoningPartial;
  }
  loading.remove();
  addConversationMessage('assistant',data.answer||'',{products:data.products,reasoning:data.reasoning,sources:data.sources,agentTrace:data.agent_trace});
  const referenceProductsHtml=renderReferenceProducts(data.products);
  updateModelPillForMode(data.tool_mode||getActiveInspirationMode(),data.model,data.product_context_used);
  appendMessage('assistant',data.answer||'没有收到回复',{products:data.products,referenceProductsHtml:referenceProductsHtml,reasoning:data.reasoning,sources:data.sources,agentTrace:data.agent_trace});
 }catch(error){
  loading.remove();
  const cancelled=error&&error.name==='AbortError';
  if(partial){
   const retained=partial+(cancelled?'\n\n（已取消，已保留部分内容）':'\n\n（生成中断，已保留部分内容）');
   addConversationMessage('assistant',retained,{products:data.products,reasoning:reasoningPartial,sources:data.sources,agentTrace:data.agent_trace,partial:true,cancelled:cancelled});
   appendMessage('assistant',retained,{products:data.products,reasoning:reasoningPartial,sources:data.sources,agentTrace:data.agent_trace});
  }else if(cancelled){
   toast('已取消生成','success');
  }else{
   appendMessage('assistant','发送失败：'+formatInspirationChatError(error));
  }
 }finally{
  if(activeInspirationRequest===controller)activeInspirationRequest=null;
  setBusy(false);
  input.focus();
 }
}
function clearChat(){
 clearCurrentConversation();
}
loadConversations();
renderConversation();
renderConversationHistory();
renderInspirationMode();
renderProductContextMode();
renderWebSearchMode();
updateInspirationPlaceholder();
renderSelectedAttachments();
resizeInspirationInput();
loadInspirationModelConfig();
document.getElementById('inspirationFileInput').addEventListener('change',function(event){
 uploadInspirationFiles(event.target.files);
 event.target.value='';
});
document.getElementById('inspirationInput').addEventListener('input',resizeInspirationInput);
document.getElementById('inspirationInput').addEventListener('paste',handleInspirationPaste);
document.addEventListener('paste',function(event){
 const input=document.getElementById('inspirationInput');
 if(input&&(event.target===input||input.contains(event.target)))return;
 handleInspirationPaste(event);
});
document.addEventListener('click',hideConversationMenuOnOutsideClick);
document.addEventListener('keydown',function(event){
 if(event.key==='Escape'){hideConversationMenu();setHistoryDrawer(false);}
});
document.addEventListener('scroll',function(event){
 if(event.target&&event.target.classList&&event.target.classList.contains('conversation-list'))hideConversationMenu();
},true);
document.addEventListener('DOMContentLoaded',renderIcons);
