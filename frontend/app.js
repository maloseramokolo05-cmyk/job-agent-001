const $=s=>document.querySelector(s);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const json=(method,body)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
const offlineBanner=$('#offlineBanner');
let installPrompt=null;

async function api(url,options){
  try{
    const response=await fetch(url,options);
    const data=await response.json().catch(()=>({}));
    if(!response.ok) throw Error(data.detail||'Request failed');
    offlineBanner.classList.add('hidden');
    return data;
  }catch(error){
    if(error instanceof TypeError) offlineBanner.classList.remove('hidden');
    throw error;
  }
}

function safeHttpUrl(value){
  try{
    const url=new URL(value,location.origin);
    return ['http:','https:'].includes(url.protocol)?url.href:null;
  }catch{return null;}
}

function isStandalone(){
  return window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;
}

function updateAppMode(){
  $('#appMode').textContent=isStandalone()?'Installed app mode':'Browser mode · install for a home-screen app';
}

function setInstallButtons(show){
  for(const selector of ['#installApp','#installAppCard']) $(selector).classList.toggle('hidden',!show||isStandalone());
}

async function installApp(){
  if(!installPrompt) return;
  installPrompt.prompt();
  await installPrompt.userChoice.catch(()=>null);
  installPrompt=null;
  setInstallButtons(false);
}

window.addEventListener('beforeinstallprompt',event=>{
  event.preventDefault();
  installPrompt=event;
  setInstallButtons(true);
});
window.addEventListener('appinstalled',()=>{installPrompt=null;setInstallButtons(false);updateAppMode();});
window.matchMedia('(display-mode: standalone)').addEventListener?.('change',updateAppMode);

$('#installApp').onclick=installApp;
$('#installAppCard').onclick=installApp;
$('#menu').onclick=()=>$('#nav').classList.toggle('open');
document.querySelectorAll('nav a').forEach(a=>a.onclick=()=>$('#nav').classList.remove('open'));
$('#filterToggle').onclick=()=>$('#filters').classList.toggle('open');
document.querySelectorAll('.close').forEach(x=>x.onclick=()=>x.closest('dialog').close());

const metrics={jobs_found:'Jobs discovered',high_match:'High matches',prepared:'Prepared',submitted:'Submitted',needs_input:'Needs input',interviews:'Interviews',rejected:'Rejected',awaiting_response:'Awaiting response',runs_today:'Runs today',last_run:'Last run'};

async function load(){
  try{
    const m=await api('/api/overview');
    $('#metrics').innerHTML=Object.entries(metrics).map(([k,v])=>`<div class="metric"><b>${esc(m[k]||0)}</b><span>${v}</span></div>`).join('');
    const jobs=await api(`/api/jobs?q=${encodeURIComponent($('#search').value)}&status=${encodeURIComponent($('#status').value)}`);
    $('#empty').hidden=jobs.length;
    $('#jobcards').innerHTML=jobs.map(j=>`<article class="card" data-job-id="${Number(j.id)}"><div class="cardtop"><div class="score">${Math.round(j.score||0)}</div><div><div class="title">${esc(j.title)}</div><div class="sub">${esc(j.company)} · ${esc(j.location||'Location unstated')}</div></div></div><span class="pill">${esc(j.status)}</span><button class="review-job" type="button">Review</button></article>`).join('');
    const apps=await api('/api/applications');
    const docs=await api('/api/documents');
    $('#applicationList').innerHTML=apps.length?apps.map(a=>`<p><b>${esc(a.title)}</b> · ${esc(a.company)}<br><small>${esc(a.status)} · ${esc(a.application_date)}</small></p>`).join(''):'<p>No applications tracked yet.</p>';
    $('#documentList').innerHTML=docs.length?docs.map(d=>`<p><b>${esc(d.document_type)}</b><br><small>${esc(d.local_path)} · ${esc(d.created_at)}</small></p>`).join(''):'<p>No generated documents yet.</p>';
    const g=await api('/api/google/status');
    $('#googleState').innerHTML=`<p><b>${g.connected?'CONNECTED':'NOT CONNECTED'}</b></p><small>Scopes: ${esc((g.scopes||[]).join(', ')||'none')}</small>`;
    const sources=await api('/api/sources');
    $('#sourceList').innerHTML=sources.map(s=>`<p><b>${esc(s.source_name)}</b> · ${esc(s.status)}<br><small>Search ${s.search_supported?'supported':'unavailable'} · Applications ${s.application_supported?'supported':'assisted/manual'}</small></p>`).join('');
    const c=await api('/api/config');
    $('#scheduleList').textContent=(c.preferences.schedule_times||[]).join(' · ');
    const logs=await api('/api/logs');
    $('#logLines').textContent=logs.lines.join('\n')||'No logs yet.';
  }catch(error){
    console.warn('Dashboard refresh failed',error);
  }
}

async function detail(id){
  const j=await api('/api/jobs/'+id);
  const target=safeHttpUrl(j.application_url||j.vacancy_url);
  $('#detail').innerHTML=`<p class="eyebrow">MATCH SCORE ${esc(j.score||0)}</p><h2>${esc(j.title)}</h2><p>${esc(j.company)} · ${esc(j.location)}</p><h3>Why it matches</h3><p>${esc(j.reasoning)}</p><h3>Missing requirements / concerns</h3><p>${esc(j.missing_requirements)}</p><h3>Description</h3><div class="description">${esc(j.description)}</div><div class="actions"><button type="button" data-job-action="cv" data-job-id="${Number(id)}">Generate CV</button><button type="button" data-job-action="cover-letter" data-job-id="${Number(id)}">Cover letter</button><button type="button" data-job-action="applied" data-job-id="${Number(id)}">Mark applied</button>${target?`<button type="button" data-job-action="open" data-job-id="${Number(id)}" data-url="${esc(target)}">Open application</button>`:''}</div>`;
  $('#detailModal').showModal();
}

async function action(id,name){
  try{await api(`/api/jobs/${id}/${name}`,{method:'POST'});await detail(id);load();}catch(e){alert(e.message);}
}
async function setStatus(id,status){await api(`/api/jobs/${id}/status`,json('POST',{status}));await detail(id);load();}

document.addEventListener('click',event=>{
  const review=event.target.closest('.review-job');
  if(review){const card=review.closest('[data-job-id]');detail(Number(card.dataset.jobId)).catch(e=>alert(e.message));return;}
  const button=event.target.closest('[data-job-action]');
  if(!button) return;
  const id=Number(button.dataset.jobId),kind=button.dataset.jobAction;
  if(kind==='cv'||kind==='cover-letter') action(id,kind);
  else if(kind==='applied') setStatus(id,'APPLIED').catch(e=>alert(e.message));
  else if(kind==='open'){
    const url=safeHttpUrl(button.dataset.url);
    if(url) window.open(url,'_blank','noopener,noreferrer');
  }
});

$('#run').onclick=async()=>{try{await api('/api/runs',{method:'POST'});$('#progress').classList.remove('hidden');poll();}catch(e){alert(e.message);}};
async function poll(){
  try{
    const r=await api('/api/runs/latest');
    $('#runmsg').textContent=r.message;$('#runstate').textContent=r.state;
    if(r.state==='RUNNING') setTimeout(poll,1200); else {setTimeout(()=>$('#progress').classList.add('hidden'),2500);load();}
  }catch{setTimeout(poll,2500);}
}

$('#search').oninput=load;
$('#status').onchange=load;
$('#connectGoogle').onclick=async()=>{try{const r=await api('/api/google/connect',json('POST',{features:['gmail','drive','calendar']}));const url=safeHttpUrl(r.authorization_url);if(url) location.href=url;}catch(e){alert(e.message);}};
$('#syncGmail').onclick=async()=>{try{const r=await api('/api/gmail/sync',{method:'POST'});alert(`${r.messages_saved} job-related messages saved`);load();}catch(e){alert(e.message);}};
$('#disconnectGoogle').onclick=async()=>{if(confirm('Remove the local Google token?')){await api('/api/google',{method:'DELETE'});load();}};

$('#setup').onclick=async()=>{
  const c=await api('/api/config'),f=$('#form'),p=c.profile,s=c.preferences;
  for(const n of ['name','email','phone','location','work_authorization']) if(f[n]) f[n].value=p[n]||'';
  f.skills.value=(p.skills||[]).join(', ');f.categories.value=(s.job_categories||[]).join(', ');f.locations.value=(s.priority_locations||[]).join(', ');f.salary.value=p.salary_expectations||'';f.score.value=s.minimum_score||75;f.schedule.value=(s.schedule_times||[]).join(', ');f.mode.value=s.application_mode||'PREPARE';$('#wizard').showModal();
};

$('#form').onsubmit=async event=>{
  event.preventDefault();
  const f=event.target,c=await api('/api/config'),p=c.profile,s=c.preferences;
  for(const n of ['name','email','phone','location','work_authorization']) p[n]=f[n].value;
  p.skills=f.skills.value.split(',').map(x=>x.trim()).filter(Boolean);p.salary_expectations=f.salary.value;s.job_categories=f.categories.value.split(',').map(x=>x.trim()).filter(Boolean);s.priority_locations=f.locations.value.split(',').map(x=>x.trim()).filter(Boolean);s.minimum_score=+f.score.value;s.schedule_times=f.schedule.value.split(',').map(x=>x.trim()).filter(Boolean);s.application_mode=f.mode.value;
  await api('/api/setup',json('POST',{profile:p,preferences:s}));
  if(f.cv.files[0]){const data=new FormData();data.append('file',f.cv.files[0]);await api('/api/cv',{method:'POST',body:data});}
  $('#wizard').close();alert('Setup saved. Run your first search when ready.');load();
};

async function registerPwa(){
  if(!('serviceWorker' in navigator)) return;
  try{
    const registration=await navigator.serviceWorker.register('/assets/sw.js',{scope:'/assets/'});
    registration.update().catch(()=>null);
  }catch(error){console.warn('Service worker registration failed',error);}
}

updateAppMode();
setInstallButtons(false);
api('/api/health').then(h=>{document.title=`Tumelo Job Agent ${h.version}`;if(!location.hash)location.hash='dashboard';}).catch(()=>offlineBanner.classList.remove('hidden'));
registerPwa();
load();
