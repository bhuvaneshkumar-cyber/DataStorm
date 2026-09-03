const nodes=[
{id:'app',type:'source',title:'Gig worker mobile app',role:'Onboard',detail:'React Native registration and withdrawal request',x:30,y:130},
{id:'consent',type:'guardrail',title:'AA consent + UPI mandate',role:'Secure onboarding',detail:'Time-bound bank consent and capped AutoPay authorization',x:30,y:360},
{id:'bank',type:'source',title:'Banking APIs',role:'Ingest',detail:'Read-only webhooks for debits and platform payouts',x:240,y:130},
{id:'gateway',type:'guardrail',title:'OAuth 2.0 + mTLS gateway',role:'Protect',detail:'TLS 1.3, server authentication and no client API keys',x:450,y:130},
{id:'ledger',type:'source',title:'PostgreSQL ledger',role:'Persist',detail:'ACID records with AES-256 column encryption',x:660,y:130},
{id:'roundup',type:'process',title:'Expense round-up engine',role:'Calculate',detail:'₹132 debit becomes ₹18 toward the next ₹50',x:870,y:65},
{id:'income',type:'process',title:'Income smoothing engine',role:'Calculate',detail:'30-day moving average finds payout surplus',x:870,y:245},
{id:'aggregate',type:'process',title:'Micro-savings aggregator',role:'Aggregate',detail:'Combines round-ups and configured surplus buffers',x:1080,y:130},
{id:'check',type:'guardrail',title:'Threshold + limit check',role:'Authorize',detail:'₹100 minimum and mandate cap must both pass',x:1080,y:360},
{id:'autopay',type:'process',title:'UPI AutoPay executor',role:'Execute',detail:'Transfers the exact authorized amount',x:1290,y:130},
{id:'stash',type:'output',title:'Resilience Stash',role:'Save',detail:'High-yield virtual account or liquid mutual fund',x:1500,y:130},
{id:'dashboard',type:'output',title:'Savings dashboard',role:'Withdraw',detail:'Balance, sweep history and lean-week relief',x:1500,y:360},
{id:'payout',type:'output',title:'Instant withdrawal',role:'Withdraw',detail:'Payout returns to the primary bank account',x:1500,y:560}
];
const edges=[['app','gateway'],['consent','gateway'],['bank','gateway'],['gateway','ledger'],['ledger','roundup'],['ledger','income'],['roundup','aggregate'],['income','aggregate'],['aggregate','check'],['check','autopay'],['autopay','stash'],['stash','dashboard'],['dashboard','payout'],['payout','app']];
const board=document.querySelector('#board'),links=document.querySelector('#links');let selected=null,drag=null;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
function render(){document.querySelectorAll('.node').forEach(n=>n.remove());nodes.forEach(n=>{const el=document.createElement('article');el.className=`node node-${n.type}${selected===n.id?' selected':''}`;el.dataset.id=n.id;el.style.left=n.x+'px';el.style.top=n.y+'px';el.innerHTML=`<small>${n.role}</small><h3>${esc(n.title)}</h3><p>${esc(n.detail)}</p><i class="port"></i>`;el.onpointerdown=e=>startDrag(e,n);el.onclick=e=>{e.stopPropagation();select(n.id)};board.append(el)});draw();inspector()}
function draw(){links.innerHTML='';edges.forEach(([a,b])=>{const x=nodes.find(n=>n.id===a),y=nodes.find(n=>n.id===b);if(!x||!y)return;const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('d',`M${x.x+170} ${x.y+47} C${x.x+210} ${x.y+47},${y.x-40} ${y.y+47},${y.x} ${y.y+47}`);p.setAttribute('fill','none');p.setAttribute('stroke','#73958d');p.setAttribute('stroke-width','2');links.append(p)})}
function select(id){selected=id;render()}
function startDrag(e,n){if(e.button!==0)return;drag={n,sx:e.clientX,sy:e.clientY,ox:n.x,oy:n.y};e.currentTarget.setPointerCapture(e.pointerId);e.currentTarget.onpointermove=moveDrag;e.currentTarget.onpointerup=()=>{drag=null}}
function moveDrag(e){if(!drag)return;drag.n.x=Math.max(8,drag.ox+e.clientX-drag.sx);drag.n.y=Math.max(8,drag.oy+e.clientY-drag.sy);const el=document.querySelector(`[data-id="${drag.n.id}"]`);el.style.left=drag.n.x+'px';el.style.top=drag.n.y+'px';draw()}
function inspector(){const form=document.querySelector('#form'),empty=document.querySelector('#empty'),n=nodes.find(x=>x.id===selected);form.hidden=!n;empty.hidden=!!n;if(!n)return;['title','role','detail'].forEach(k=>{const f=document.querySelector('#'+k);f.value=n[k];f.oninput=()=>{n[k]=f.value;render();document.querySelector('#'+k).focus()}})}
document.querySelector('#remove').onclick=()=>{const gone=selected;nodes.splice(nodes.findIndex(n=>n.id===gone),1);for(let i=edges.length-1;i>=0;i--)if(edges[i].includes(gone))edges.splice(i,1);selected=null;render()};document.querySelectorAll('[draggable]').forEach(b=>b.ondragstart=e=>e.dataTransfer.setData('type',b.dataset.type));board.ondragover=e=>e.preventDefault();board.ondrop=e=>{e.preventDefault();const type=e.dataTransfer.getData('type');if(!type)return;nodes.push({id:'new'+Date.now(),type,title:'New '+type,role:'Define role',detail:'Add implementation notes',x:e.offsetX-85,y:e.offsetY-45});render()};board.onclick=()=>{selected=null;render()};render();
