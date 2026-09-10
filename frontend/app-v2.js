const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cookie = n => document.cookie.split('; ').find(x => x.startsWith(n + '='))?.split('=')[1] || '';
const json = (method, body) => ({method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});

let jobsCache = [];
let actionsCache = [];
let applicationsCache = [];
let currentJob = null;
let currentAppTab = 'action';
let runStartedAt = null;
let runTimer = null;
let toastTimer = null;
let confirmResolve = null;

function toast(message, type='success') {
  const el = $('#toast');
  clearTimeout(toastTimer);
  el.textContent = message;
  el.className = `toast show ${type}`;
  toastTimer = setTimeout(() => el.className='toast', 3600);
}

function showLogin(message='') {
  $('#loginError').textContent = message;
  if (!$('#loginDialog').open) $('#loginDialog').showModal();
  googleBootstrapStatus();
}

async function api(url, options={}) {
  options.headers = {...(options.headers || {})};
  const method = options.method || 'GET';
  if (!['GET','HEAD','OPTIONS'].includes(method)) options.headers['X-CSRF-Token'] = decodeURIComponent(cookie('job_agent_csrf'));
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const code = data.error?.code || '';
    const message = data.error?.message || data.detail || `Request failed (${response.status})`;
    if (response.status === 401 && code === 'UNAUTHENTICATED') showLogin(message);
    const error = new Error(message);
    error.code = code;
    error.status = response.status;
    throw error;
  }
  return data;
}

function safeJson(value, fallback=[]) {
  if (Array.isArray(value) || (value && typeof value === 'object')) return value;
  try { return JSON.parse(value || ''); } catch (_) { return fallback; }
}

function formatDate(value) {
  if (!value) return 'Not set';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return new Intl.DateTimeFormat('en-ZA',{day:'numeric',month:'short',year:'numeric'}).format(d);
}

function relativeTime(value) {
  if (!value) return 'Never';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return formatDate(value);
  const diff = Math.max(0, Date.now() - d.getTime());
  const min = Math.floor(diff/60000);
  if (min < 2) return 'just now';
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min/60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr/24);
  return day < 7 ? `${day}d ago` : formatDate(value);
}

function initials(value='') {
  const parts = String(value).trim().split(/\s+/).filter(Boolean);
  return (parts.slice(0,2).map(x=>x[0]).join('') || 'JOB').toUpperCase();
}

function humanStatus(value='') {
  return {
    DISCOVERED:'Discovered',SHORTLISTED:'Shortlisted',PREPARED:'CV ready',READY_TO_APPLY:'Ready to apply',
    NEEDS_USER_INPUT:'Action needed',NEEDS_USER_ACTION:'Action needed',MANUAL_APPLICATION:'Manual application',
    APPLIED:'Applied',APPLIED_CONFIRMED:'Application confirmed',INTERVIEW:'Interview',ASSESSMENT:'Assessment',
    REJECTED:'Rejected',OFFER:'Offer',WITHDRAWN:'Withdrawn',EXPIRED:'Expired'
  }[value] || String(value || 'Unknown').replaceAll('_',' ').toLowerCase().replace(/\b\w/g,c=>c.toUpperCase());
}

function classification(score) {
  const n = Number(score || 0);
  if (n >= 90) return 'Excellent';
  if (n >= 80) return 'Strong';
  if (n >= 70) return 'Good';
  if (n >= 60) return 'Possible';
  return 'Low';
}

function workMode(job) {
  if (job.work_mode) return String(job.work_mode).toLowerCase();
  const text = `${job.title||''} ${job.description||''}`.toLowerCase();
  if (/\bhybrid\b/.test(text)) return 'hybrid';
  if (/\bremote\b|work from home|\bwfh\b/.test(text)) return 'remote';
  if (/on[- ]?site|office[- ]?based|in[- ]?office/.test(text)) return 'on-site';
  return '';
}

function errorBlock(message, retry='') {
  return `<div class="error-card"><b>Couldn’t load this section</b><p>${esc(message)}</p>${retry?`<button class="secondary" onclick="${retry}">Retry</button>`:''}</div>`;
}

function setGreeting() {
  try {
    const hour = Number(new Intl.DateTimeFormat('en-ZA',{hour:'numeric',hour12:false,timeZone:'Africa/Johannesburg'}).format(new Date()));
    const part = hour < 12 ? 'MORNING' : hour < 18 ? 'AFTERNOON' : 'EVENING';
    $('#greeting').textContent = `GOOD ${part}, TUMELO`;
  } catch (_) {}
}

function route() {
  const allowed = ['dashboard','jobs','applications','documents','profile','integrations','settings','diagnostics'];
  let name = (location.hash || '#dashboard').slice(1).split('?')[0];
  if (!allowed.includes(name)) name = 'dashboard';
  $$('.page-view').forEach(el => el.classList.toggle('active-page', el.dataset.page === name));
  $$('[data-route]').forEach(el => el.classList.toggle('active', el.dataset.route === name));
  if (name === 'dashboard') loadDashboard();
  if (name === 'jobs') loadJobs();
  if (name === 'applications') loadApplications();
  if (name === 'documents') loadDocuments();
  if (name === 'profile') loadProfile();
  if (name === 'integrations') loadIntegrations();
  if (name === 'settings') loadSettings();
  if (name === 'diagnostics') loadDiagnostics();
  window.scrollTo({top:0,behavior:'instant'});
}
window.addEventListener('hashchange', route);

async function googleBootstrapStatus() {
  try {
    const r = await fetch('/api/google/bootstrap');
    const d = await r.json();
    $('#googleBootstrapState').textContent = d.stored_credentials ? 'Google OAuth credentials are already stored securely.' : `Required redirect: ${d.redirect_uri}`;
    if (d.stored_credentials) $('#googleBootstrap').open = false;
  } catch (_) { $('#googleBootstrapState').textContent = 'Google setup status could not be loaded.'; }
}

$('#uploadGoogleCredentials').onclick = async () => {
  const file = $('#googleCredentialsFile').files?.[0];
  if (!file) return $('#googleBootstrapState').textContent='Choose the Google OAuth JSON file first.';
  const data = new FormData(); data.append('file',file);
  try {
    $('#googleBootstrapState').textContent='Saving securely…';
    await api('/api/google/bootstrap',{method:'POST',body:data});
    location.href='/api/google/callback';
  } catch(e) { $('#googleBootstrapState').textContent=e.message; }
};
$('#googleLogin').onclick=()=>location.href='/api/google/callback';

function metric(icon,value,label,sub='') {
  return `<div class="metric"><span class="metric-icon">${icon}</span><b>${esc(value ?? 0)}</b><span>${esc(label)}</span><small>${esc(sub)}</small></div>`;
}

async function loadDashboard() {
  const metrics = $('#dashboardMetrics');
  const [dashResult, actionsResult, jobsResult] = await Promise.allSettled([
    api('/api/dashboard'), api('/api/actions?limit=8'), api('/api/jobs?min_score=75')
  ]);
  if (dashResult.status === 'fulfilled') {
    const d = dashResult.value;
    metrics.innerHTML = [
      metric('◎',d.relevant_jobs,'Relevant Jobs','65%+ CV fit'),
      metric('★',d.high_matches,'High Matches','80%+ CV fit'),
      metric('!',d.action_needed,'Action Needed','Applications waiting on you'),
      metric('↗',d.submitted,'Applications Sent','Tracked submissions')
    ].join('');
    $('#googleSummaryText').textContent = d.google?.connected ? 'Connected' : 'Needs attention';
    $('#replySummary').textContent = `${d.employer_replies || 0} synced`;
    $('#interviewSummary').textContent = d.next_interview?.starts_at ? formatDate(d.next_interview.starts_at) : 'None scheduled';
    $('#lastRunSummary').textContent = d.last_run?.started_at ? `${humanStatus(d.last_run.state)} · ${relativeTime(d.last_run.started_at)}` : 'Not run yet';
    if (d.last_run?.state === 'RUNNING') showRunProgress();
  } else {
    metrics.innerHTML = errorBlock(dashResult.reason.message,'loadDashboard()');
  }

  if (actionsResult.status === 'fulfilled') {
    actionsCache = actionsResult.value;
    renderActions(actionsCache);
    renderNotifications(actionsCache);
  } else $('#nextActions').innerHTML = errorBlock(actionsResult.reason.message,'loadDashboard()');

  if (jobsResult.status === 'fulfilled') renderTopMatches(jobsResult.value);
  else $('#topMatches').innerHTML = errorBlock(jobsResult.reason.message,'loadDashboard()');
}
window.loadDashboard = loadDashboard;

function renderActions(actions) {
  const box = $('#nextActions');
  if (!actions.length) {
    box.innerHTML='<div class="empty-inline"><b>You’re caught up.</b><p>No urgent actions right now.</p></div>';
    return;
  }
  box.innerHTML = actions.slice(0,6).map(a=>{
    let button = '<button class="secondary">Review</button>';
    let handler = `openAction('${esc(a.type)}',${Number(a.job_id||a.run_id||0)})`;
    if (a.type === 'google_reconnect') handler = "location.hash='#integrations'";
    return `<div class="action-item"><div class="activity-icon">${a.type==='interrupted_run'?'↻':a.type==='google_reconnect'?'G':'!'}</div><div><b>${esc(a.title)}</b><small>${esc(a.job_title ? `${a.job_title} · ${a.company||''}` : a.detail||'')}</small></div><button class="secondary" onclick="${handler}">${a.type==='interrupted_run'?'Clear':'Open'}</button></div>`;
  }).join('');
}

async function openAction(type,id) {
  if (type === 'interrupted_run') {
    const ok = await confirmAction('Clear interrupted search?','This only clears the stale run marker. It does not delete jobs or applications.');
    if (!ok) return;
    try { await api(`/api/runs/${id}/discard`,{method:'POST'}); toast('Interrupted run cleared.'); loadDashboard(); } catch(e){ toast(e.message,'error'); }
    return;
  }
  if (id) openJob(id);
}
window.openAction=openAction;

function renderNotifications(actions) {
  const unresolved = actions.filter(Boolean);
  $('#notificationDot').hidden = unresolved.length === 0;
  $('#notificationList').innerHTML = unresolved.length ? unresolved.map(a=>`<div class="record-row"><div class="activity-icon">!</div><div><div class="record-title">${esc(a.title)}</div><div class="record-sub">${esc(a.job_title ? `${a.job_title} · ${a.company||''}` : a.detail||'')}</div></div></div>`).join('') : '<div class="empty-inline">No unresolved notifications.</div>';
}

function renderTopMatches(jobs) {
  const top = [...jobs].filter(j=>Number(j.score||0)>=75).sort((a,b)=>Number(b.score)-Number(a.score)).slice(0,5);
  $('#topMatches').innerHTML = top.length ? top.map(j=>`<div class="compact-job"><div class="company-badge">${esc(initials(j.company))}</div><div class="compact-job-copy"><b>${esc(j.title)}</b><small>${esc(j.company)} · ${esc(j.location||'Location not listed')}</small></div><span class="match">${Math.round(Number(j.score||0))}%</span><button class="row-action" onclick="openJob(${Number(j.id)})">›</button></div>`).join('') : '<div class="empty-inline">No strong matches yet. Run a new search or adjust target roles.</div>';
}

function setRunButton(running) {
  $('#run').disabled = running;
  $('#runFromJobs').disabled = running;
  $('#runLabel').textContent = running ? 'Searching…' : 'Run Job Search';
}

function showRunProgress() {
  $('#runProgress').classList.remove('hidden');
  if (!runStartedAt) runStartedAt = Date.now();
  clearInterval(runTimer);
  runTimer = setInterval(()=>{
    const seconds = Math.floor((Date.now()-runStartedAt)/1000);
    $('#runElapsed').textContent = `${seconds}s elapsed`;
  },1000);
}

function renderRunStats(stats={}) {
  const values = [
    ['Found',stats.discovered||0],['Skipped',stats.duplicates||0],['Analysed',stats.analyzed||0],['Shortlisted',stats.shortlisted||stats.strong_matches||0],['Errors',stats.errors||0]
  ];
  $('#runStats').innerHTML = values.map(([label,value])=>`<div class="run-stat"><b>${esc(value)}</b><small>${label}</small></div>`).join('');
}

async function pollRun() {
  try {
    const r = await api('/api/runs/latest');
    $('#runMessage').textContent = r.message || 'Searching South African vacancies…';
    $('#runState').textContent = r.state || 'RUNNING';
    $('#runBar').style.width = `${Math.max(5,Math.min(100,Number(r.progress||5)))}%`;
    const cp = safeJson(r.checkpoint,{});
    const stats = cp.stats || safeJson(r.stats,{});
    renderRunStats(stats);
    if (r.state === 'RUNNING') return setTimeout(pollRun,1500);
    setRunButton(false);
    clearInterval(runTimer); runTimer=null; runStartedAt=null;
    if (r.state === 'INTERRUPTED') {
      $('#interruptedActions').classList.remove('hidden');
      $('#interruptedActions').innerHTML=`<button class="secondary" onclick="openAction('interrupted_run',${Number(r.id)})">Clear interrupted run</button>`;
    } else {
      setTimeout(()=>$('#runProgress').classList.add('hidden'),3500);
      toast(r.message || 'Search complete.');
      loadDashboard();
      if ((location.hash||'#dashboard') === '#jobs') loadJobs();
    }
  } catch(e) {
    setRunButton(false);
    clearInterval(runTimer); runTimer=null;
    $('#runMessage').textContent=e.message;
    $('#runState').textContent='ERROR';
  }
}

function runSearch() {
  setRunButton(true);
  showRunProgress();
  $('#runMessage').textContent='Starting South Africa job search…';
  $('#runState').textContent='STARTING';
  renderRunStats({});
  // Start polling immediately. The search request can remain synchronous on
  // Vercel while a concurrent request reads durable run progress from Neon.
  api('/api/runs',{method:'POST'}).catch(e=>{ if (!/already active/i.test(e.message)) toast(e.message,'error'); });
  setTimeout(pollRun,500);
}
$('#run').onclick=runSearch;
$('#runFromJobs').onclick=runSearch;

async function loadJobs() {
  const minScore = Number($('#minScore')?.value || 75);
  const status = $('#jobStatus')?.value || '';
  const q = $('#jobSearch')?.value || '';
  $('#jobcards').innerHTML='Loading jobs…';
  try {
    jobsCache = await api(`/api/jobs?min_score=${minScore}&status=${encodeURIComponent(status)}&q=${encodeURIComponent(q)}`);
    renderJobs();
  } catch(e) { $('#jobcards').innerHTML=errorBlock(e.message,'loadJobs()'); }
}
window.loadJobs=loadJobs;

function renderJobs() {
  let jobs=[...jobsCache];
  const mode=$('#workMode')?.value||'all';
  if (mode!=='all') jobs=jobs.filter(j=>workMode(j)===mode);
  const sort=$('#jobSort')?.value||'score';
  if (sort==='score') jobs.sort((a,b)=>Number(b.score||0)-Number(a.score||0));
  if (sort==='newest') jobs.sort((a,b)=>new Date(b.discovered_at||0)-new Date(a.discovered_at||0));
  if (sort==='closing') jobs.sort((a,b)=>new Date(a.closing_date||'2999-01-01')-new Date(b.closing_date||'2999-01-01'));
  $('#jobCount').textContent=`${jobs.length} relevant job${jobs.length===1?'':'s'}`;
  $('#jobcards').innerHTML = jobs.length ? jobs.map(j=>{
    const score=Math.round(Number(j.score||0));
    return `<article class="job-card"><div class="company-badge">${esc(initials(j.company))}</div><div class="job-main"><h3>${esc(j.title)}</h3><p>${esc(j.company)} · ${esc(j.location||'Location not listed')}</p><p class="fit-line">${esc((j.reasoning||'').slice(0,150) || `${classification(score)} match to your verified CV`)}</p><div class="job-meta"><span class="pill success">${classification(score)}</span>${workMode(j)?`<span class="pill">${esc(workMode(j))}</span>`:''}${j.salary?`<span class="pill">${esc(j.salary)}</span>`:''}<span class="pill">${esc(humanStatus(j.status))}</span>${j.application_method?`<span class="pill">${esc(j.application_method==='EMAIL'?'Email apply':'Employer website')}</span>`:''}</div></div><div class="job-score"><b>${score}% match</b><small>${j.closing_date?`Closes ${esc(formatDate(j.closing_date))}`:esc(relativeTime(j.discovered_at))}</small></div><button class="review-button" onclick="openJob(${Number(j.id)})">Review</button></article>`;
  }).join('') : '<div class="empty-inline"><b>No jobs match these filters.</b><p>Lower the minimum score slightly or run a fresh search.</p></div>';
}

async function openJob(id) {
  try {
    const j=await api(`/api/jobs/${id}`); currentJob=j;
    const missing=safeJson(j.missing_requirements,[]);
    const score=Math.round(Number(j.score||0));
    const emailReady=j.email_verified && j.application_email && score>=80;
    let primary='';
    if (emailReady && ['READY_TO_APPLY','PREPARED','SHORTLISTED','NEEDS_USER_ACTION'].includes(j.status)) primary=`<button class="primary" onclick="previewEmail(${id})">Review email application</button>`;
    else if (['NEEDS_USER_ACTION','MANUAL_APPLICATION'].includes(j.status)) primary=`<button class="primary" onclick="openEmployer()">Open employer application</button>`;
    else if (!j.cv_path) primary=`<button class="primary" onclick="prepareDocument(${id},'cv')">Prepare tailored CV</button>`;
    else primary=`<button class="primary" onclick="openEmployer()">Open employer application</button>`;
    $('#jobDetail').innerHTML=`<p class="eyebrow">${esc(classification(score).toUpperCase())} MATCH</p><h2>${esc(j.title)}</h2><p class="section-copy">${esc(j.company)} · ${esc(j.location||'Location not listed')}</p><div class="job-detail-grid"><div class="detail-fact"><small>Match</small><b>${score}%</b></div><div class="detail-fact"><small>Status</small><b>${esc(humanStatus(j.status))}</b></div><div class="detail-fact"><small>Salary</small><b>${esc(j.salary||'Not listed')}</b></div><div class="detail-fact"><small>Work style</small><b>${esc(workMode(j)||'Not specified')}</b></div><div class="detail-fact"><small>Source</small><b>${esc(j.source||'Unknown')}</b></div><div class="detail-fact"><small>Closing date</small><b>${esc(j.closing_date?formatDate(j.closing_date):'Not listed')}</b></div></div><h3>Why this fits</h3><p>${esc(j.reasoning||'No fit explanation recorded.')}</p><h3>Missing requirements / concerns</h3>${missing.length?`<ul>${missing.map(x=>`<li>${esc(typeof x==='string'?x:JSON.stringify(x))}</li>`).join('')}</ul>`:'<p>No mandatory concerns recorded.</p>'}<h3>Application</h3><p>${esc(j.application_method==='EMAIL'&&j.email_verified?'Verified email application route available.':'This application opens on the employer/source website.')}</p><div class="button-row">${primary}<button class="secondary" onclick="prepareDocument(${id},'cover-letter')">Cover letter</button><select id="statusSelect" class="status-select" onchange="changeJobStatus(${id},this.value)">${['SHORTLISTED','PREPARED','READY_TO_APPLY','NEEDS_USER_ACTION','APPLIED','INTERVIEW','ASSESSMENT','REJECTED','OFFER','WITHDRAWN'].map(s=>`<option value="${s}" ${s===j.status?'selected':''}>${esc(humanStatus(s))}</option>`).join('')}</select>${j.status==='INTERVIEW'?`<button class="secondary" onclick="openInterview(${id})">Add interview to Calendar</button>`:''}</div><h3>Description</h3><div class="description">${esc(j.description||'No description available.')}</div>`;
    $('#jobDialog').showModal();
  } catch(e){toast(e.message,'error');}
}
window.openJob=openJob;

function openEmployer(){ if(currentJob) window.open(currentJob.application_url||currentJob.vacancy_url,'_blank','noopener'); }
window.openEmployer=openEmployer;

async function prepareDocument(id,type){
  const label=type==='cv'?'CV':'cover letter';
  try{toast(`Preparing ${label}…`);await api(`/api/jobs/${id}/${type==='cv'?'cv':'cover-letter'}`,{method:'POST'});toast(`${label==='CV'?'CV':'Cover letter'} ready.`);await openJob(id);loadDocuments();}catch(e){toast(e.message,'error');}
}
window.prepareDocument=prepareDocument;

async function changeJobStatus(id,status){
  try{await api(`/api/jobs/${id}/status`,json('POST',{status}));toast(`Marked ${humanStatus(status).toLowerCase()}.`);await openJob(id);loadDashboard();}catch(e){toast(e.message,'error');}
}
window.changeJobStatus=changeJobStatus;

async function previewEmail(id){
  try{
    const p=await api(`/api/jobs/${id}/email-preview`);
    if(!p.eligible){toast('A duplicate application is already tracked.','error');return;}
    $('#jobDetail').insertAdjacentHTML('beforeend',`<div class="notice"><b>Email preview</b><p><b>To:</b> ${esc(p.recipient)}<br><b>Subject:</b> ${esc(p.subject)}<br><b>Attachment:</b> ${esc(p.cv_filename)}</p></div><pre>${esc(p.body)}</pre><button class="primary" onclick="sendEmailApplication(${id})">Confirm & send application</button>`);
  }catch(e){ if(e.status===401) location.hash='#integrations'; toast(e.message,'error'); }
}
window.previewEmail=previewEmail;

async function sendEmailApplication(id){
  const ok=await confirmAction('Send this application?','The Job Agent will re-check the published email, check Gmail for duplicates, attach the tailored PDF CV, and send only after this confirmation.');
  if(!ok)return;
  try{const r=await api(`/api/jobs/${id}/apply-email`,json('POST',{confirmed:true}));toast(r.duplicate?'Duplicate prevented.':'Application sent.');$('#jobDialog').close();loadDashboard();loadApplications();}catch(e){toast(e.message,'error');}
}
window.sendEmailApplication=sendEmailApplication;

async function loadApplications(){
  const [appR,actionR,inboxR]=await Promise.allSettled([api('/api/applications'),api('/api/actions?limit=100'),api('/api/inbox?limit=30')]);
  applicationsCache=appR.status==='fulfilled'?appR.value:[];
  actionsCache=actionR.status==='fulfilled'?actionR.value:[];
  renderApplicationTab();
  if(inboxR.status==='fulfilled') renderInbox(inboxR.value); else $('#inboxList').innerHTML=errorBlock(inboxR.reason.message,'loadApplications()');
}
window.loadApplications=loadApplications;

function renderApplicationTab(){
  let html='';
  if(currentAppTab==='action'){
    const jobs=actionsCache.filter(a=>a.job_id);
    html=jobs.length?jobs.map(a=>`<div class="record-row"><div class="activity-icon">!</div><div><div class="record-title">${esc(a.job_title)}</div><div class="record-sub">${esc(a.company||'')} · ${Math.round(Number(a.score||0))}% match · ${esc(a.status_label||'Action needed')}</div></div><button class="secondary record-action" onclick="openJob(${Number(a.job_id)})">Open</button></div>`).join(''):'<div class="empty-inline">No applications need your action.</div>';
  }else{
    let rows=[...applicationsCache];
    if(currentAppTab==='submitted')rows=rows.filter(a=>['APPLIED','APPLIED_CONFIRMED'].includes(a.status));
    if(currentAppTab==='interviews')rows=rows.filter(a=>['INTERVIEW','ASSESSMENT'].includes(a.status));
    if(currentAppTab==='closed')rows=rows.filter(a=>['REJECTED','OFFER','WITHDRAWN','EXPIRED'].includes(a.status));
    html=rows.length?rows.map(a=>`<div class="record-row"><div class="activity-icon">↗</div><div><div class="record-title">${esc(a.title||'Application')}</div><div class="record-sub">${esc(a.company||'')} · ${esc(humanStatus(a.status))} · ${esc(formatDate(a.application_date||a.created_at))}${a.recruiter_email?` · ${esc(a.recruiter_email)}`:''}</div></div>${a.job_id?`<button class="secondary record-action" onclick="openJob(${Number(a.job_id)})">Open</button>`:''}</div>`).join(''):'<div class="empty-inline">Nothing in this stage yet.</div>';
  }
  $('#applicationList').innerHTML=html;
}

$$('#applicationTabs button').forEach(b=>b.onclick=()=>{currentAppTab=b.dataset.tab;$$('#applicationTabs button').forEach(x=>x.classList.toggle('active',x===b));renderApplicationTab();});

function renderInbox(messages){
  $('#inboxList').innerHTML=messages.length?messages.map(m=>`<div class="record-row"><div class="activity-icon">✉</div><div><div class="record-title">${esc(m.subject||'Job-related email')}</div><div class="record-sub">${esc(m.from_address||m.sender||'')} · ${esc(relativeTime(m.received_at))}</div></div></div>`).join(''):'<div class="empty-inline">No job-related messages synced yet.</div>';
}

async function syncGmail(){
  try{toast('Syncing Gmail…');const r=await api('/api/gmail/sync',{method:'POST'});toast(`${r.messages_saved||0} job-related messages synced.`);loadApplications();loadIntegrations();}catch(e){ if(e.status===401) location.hash='#integrations'; toast(`Google connection needs attention: ${e.message}`,'error'); }
}
$('#syncGmail').onclick=syncGmail;
$('#syncGmailIntegrations').onclick=syncGmail;

async function loadDocuments(){
  const [groupR,cvR]=await Promise.allSettled([api('/api/document-groups'),api('/api/cv')]);
  if(cvR.status==='fulfilled'){
    const c=cvR.value;
    $('#masterCvState').innerHTML=c.available?`<b>✓ Master CV ready</b><p>${esc(c.master_cv.original_name)} · version ${esc(c.master_cv.version)}</p><a class="button secondary" href="/api/cv/download">Download master CV</a>`:'<b>Master CV required</b><p>Upload your verified CV from Profile.</p>';
  }else $('#masterCvState').innerHTML=errorBlock(cvR.reason.message,'loadDocuments()');
  if(groupR.status!=='fulfilled'){ $('#documentGroups').innerHTML=errorBlock(groupR.reason.message,'loadDocuments()'); return; }
  $('#documentGroups').innerHTML=groupR.value.length?groupR.value.map(g=>`<article class="document-group"><h3>${esc(g.title)}</h3><small>${esc(g.company||'')} ${g.score?`· ${Math.round(Number(g.score))}% match`:''}</small><div class="document-files">${g.documents.map(d=>`<div class="document-file"><div><b>${esc(d.document_type==='CV_PDF'?'Tailored CV · PDF':d.document_type==='CV_DOCX'?'Tailored CV · DOCX':d.document_type==='COVER_LETTER'?'Cover Letter':d.document_type)}</b><small>${esc(formatDate(d.created_at))}</small></div><div class="button-row"><a class="button secondary" href="/api/documents/${Number(d.id)}/download">Download</a><button class="secondary" onclick="saveToDrive(${Number(d.id)})">Save to Drive</button></div></div>`).join('')}</div></article>`).join(''):'<div class="empty-inline">No tailored documents yet. Open a strong job match and prepare a CV.</div>';
}
window.loadDocuments=loadDocuments;

async function saveToDrive(id){try{toast('Saving to Drive…');const r=await api(`/api/documents/${id}/drive`,{method:'POST'});toast(r.id?'Saved to Drive.':'Drive upload complete.');}catch(e){if(e.status===401)location.hash='#integrations';toast(e.message,'error');}}
window.saveToDrive=saveToDrive;

async function loadProfile(){
  try{
    const c=await api('/api/config'); const p=c.profile||{},s=c.preferences||{};
    const items=[['Name',p.name],['Email',p.email],['Phone',p.phone],['Location',p.location],['Target roles',(s.job_categories||[]).join(', ')],['Preferred locations',(s.priority_locations||[]).join(', ')],['Skills',(p.skills||[]).join(', ')],['Salary expectation',p.salary_expectations],['Application mode',humanMode(s.application_mode)]];
    $('#profileSummary').innerHTML=items.map(([label,value])=>`<div class="profile-item"><small>${esc(label)}</small><b>${esc(value||'Not set')}</b></div>`).join('');
  }catch(e){$('#profileSummary').innerHTML=errorBlock(e.message,'loadProfile()');}
}
window.loadProfile=loadProfile;

function humanMode(mode){return {AUTO_EMAIL:'Automatically send eligible email applications',PREPARE:'Prepare documents',DISCOVER_ONLY:'Discover only',ASSISTED_APPLY:'Assisted apply'}[mode]||mode||'Not set';}

async function openProfileEditor(){
  try{
    const c=await api('/api/config'),p=c.profile||{},s=c.preferences||{},f=$('#profileForm');
    for(const n of ['name','email','phone','location','work_authorization']) if(f[n])f[n].value=p[n]||'';
    f.salary.value=p.salary_expectations||'';f.skills.value=(p.skills||[]).join(', ');f.categories.value=(s.job_categories||[]).join(', ');f.locations.value=(s.priority_locations||[]).join(', ');$('#profileEditor').showModal();
  }catch(e){toast(e.message,'error');}
}
$('#editProfile').onclick=openProfileEditor;

$('#profileForm').onsubmit=async e=>{
  e.preventDefault(); const f=e.target; const submit=f.querySelector('button[type="submit"],button.primary'); submit.disabled=true; submit.textContent='Saving…';
  try{
    const c=await api('/api/config'),p=c.profile||{},s=c.preferences||{};
    for(const n of ['name','email','phone','location','work_authorization'])p[n]=f[n].value.trim();
    p.salary_expectations=f.salary.value.trim();p.skills=f.skills.value.split(',').map(x=>x.trim()).filter(Boolean);s.job_categories=f.categories.value.split(',').map(x=>x.trim()).filter(Boolean);s.priority_locations=f.locations.value.split(',').map(x=>x.trim()).filter(Boolean);
    await api('/api/setup',json('POST',{profile:p,preferences:s}));
    if(f.cv.files[0]){const data=new FormData();data.append('file',f.cv.files[0]);await api('/api/cv',{method:'POST',body:data});}
    $('#profileEditor').close();toast('Profile saved. Job-fit cache will refresh from the verified profile.');loadProfile();loadDashboard();
  }catch(err){toast(err.message,'error');}finally{submit.disabled=false;submit.textContent='Save profile';}
};

async function loadIntegrations(){
  const [gR,inboxR,driveR]=await Promise.allSettled([api('/api/google/status'),api('/api/inbox?limit=5'),api('/api/drive/files')]);
  if(gR.status==='fulfilled'){
    const g=gR.value, connected=!!g.connected, scopes=g.scopes||[];
    $('#googleState').className=`status-banner ${connected?'':'off'}`;$('#googleState').textContent=connected?'✓ Google account connected':'Google connection needs attention';
    const has=x=>scopes.some(s=>String(s).includes(x));
    $('#googleCards').innerHTML=[['Gmail',connected&&(has('gmail.')||has('gmail/')),'Send applications and sync replies'],['Drive',connected&&has('drive.file'),'Save Job Agent documents'],['Calendar',connected&&has('calendar.events'),'Schedule interviews']].map(([n,on,sub])=>`<div class="integration-card-item"><div class="integration-icon">${n==='Gmail'?'G':n==='Drive'?'△':'31'}</div><b>${n}</b><small>${sub}</small><span class="status-dot ${on?'':'off'}">● ${on?'Connected':'Needs attention'}</span></div>`).join('');
    $('#gmailStatus').innerHTML=`<p>${connected?'Connected':'Reconnect Google to sync job-related messages.'}</p><small>${g.expires_at?`Token expires ${formatDate(g.expires_at)}`:''}</small>`;
  } else { $('#googleState').className='status-banner off';$('#googleState').textContent='Google status could not be loaded.'; }
  if(inboxR.status==='fulfilled'&&inboxR.value.length) $('#gmailStatus').insertAdjacentHTML('beforeend',`<p>${inboxR.value.length} recent synced message${inboxR.value.length===1?'':'s'}.</p>`);
  if(driveR.status==='fulfilled') $('#driveFiles').innerHTML=driveR.value.length?driveR.value.slice(0,8).map(f=>`<div class="integration-status-line"><span>${esc(f.name||'Job Agent file')}</span><small>${esc(f.modifiedTime?formatDate(f.modifiedTime):'')}</small></div>`).join(''):'<div class="empty-inline">No Job Agent files in Drive yet.</div>';
  else $('#driveFiles').innerHTML='<div class="empty-inline">Connect Google to view app-created Drive files.</div>';
}
window.loadIntegrations=loadIntegrations;

$('#connectGoogle').onclick=async()=>{try{const r=await api('/api/google/connect',json('POST',{features:['gmail','drive','calendar']}));location.href=r.authorization_url;}catch(e){toast(e.message,'error');}};
$('#disconnectGoogle').onclick=async()=>{const ok=await confirmAction('Disconnect Google?','Gmail, Drive and Calendar actions will stop until you reconnect.');if(!ok)return;try{await api('/api/google',{method:'DELETE'});toast('Google disconnected.');loadIntegrations();loadDashboard();}catch(e){toast(e.message,'error');}};
$('#refreshDrive').onclick=loadIntegrations;

async function loadSettings(){
  try{
    const s=await api('/api/settings'),f=$('#settingsForm');
    f.minimum_score.value=s.minimum_score??68;f.priority_locations.value=(s.priority_locations||[]).join(', ');f.job_categories.value=(s.job_categories||[]).join(', ');f.allow_other_sa_locations.checked=!!s.allow_other_sa_locations;f.email_minimum_score.value=Math.max(80,Number(s.email_minimum_score||80));f.email_duplicate_window_days.value=s.email_duplicate_window_days||365;f.application_mode.value=s.application_mode||'PREPARE';f.schedule_times.value=(s.schedule_times||[]).join(', ');
  }catch(e){toast(e.message,'error');}
}
window.loadSettings=loadSettings;

$('#settingsForm').onsubmit=async e=>{
  e.preventDefault();const f=e.target,b=$('#saveSettings');b.disabled=true;b.textContent='Saving…';
  try{const s=await api('/api/settings');s.minimum_score=Number(f.minimum_score.value);s.priority_locations=f.priority_locations.value.split(',').map(x=>x.trim()).filter(Boolean);s.job_categories=f.job_categories.value.split(',').map(x=>x.trim()).filter(Boolean);s.allow_other_sa_locations=f.allow_other_sa_locations.checked;s.email_minimum_score=Math.max(80,Number(f.email_minimum_score.value||80));s.email_duplicate_window_days=Number(f.email_duplicate_window_days.value||365);s.application_mode=f.application_mode.value;s.schedule_times=f.schedule_times.value.split(',').map(x=>x.trim()).filter(Boolean);await api('/api/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(s)});toast('Settings saved.');loadDashboard();}catch(err){toast(err.message,'error');}finally{b.disabled=false;b.textContent='Save settings';}
};

async function loadDiagnostics(){
  try{
    const d=await api('/api/diagnostics');
    $('#diagnosticCards').innerHTML=[metric('DB',d.database?.ready?'Ready':'Issue','Database',`Schema ${d.database?.schema_version??'?'}`),metric('G',d.google?.connected?'Connected':'Action','Google','OAuth connection'),metric('CV',d.master_cv?'Ready':'Missing','Master CV',d.master_cv?.original_name||'Upload required'),metric('↻',d.scheduler?.configured?'Ready':'Issue','Scheduler','Production cron')].join('');
    $('#sourceList').innerHTML=(d.sources||[]).map(s=>`<div class="record-row"><div class="activity-icon">↗</div><div><div class="record-title">${esc(s.source_name)}</div><div class="record-sub">Search: ${s.search_supported?'Connected':'Unavailable'} · Application: ${s.application_supported?'Automated':'Employer/manual'}${s.last_success?` · Last success ${relativeTime(s.last_success)}`:''}</div>${s.last_error?`<div class="record-sub">Last error: ${esc(s.last_error)}</div>`:''}</div><span class="record-status">${esc(s.status||'UNKNOWN')}</span></div>`).join('')||'<div class="empty-inline">No source diagnostics yet.</div>';
    $('#latestRunDetails').textContent=JSON.stringify(d.latest_run||{state:'No runs yet'},null,2);
  }catch(e){$('#diagnosticCards').innerHTML=errorBlock(e.message,'loadDiagnostics()');}
}
window.loadDiagnostics=loadDiagnostics;
$('#refreshDiagnostics').onclick=loadDiagnostics;

function openInterview(id){
  if(!currentJob)return;const f=$('#interviewForm');f.company.value=currentJob.company||'';f.role.value=currentJob.title||'';f.dataset.jobId=id;$('#interviewDialog').showModal();
}
window.openInterview=openInterview;

$('#interviewForm').onsubmit=async e=>{
  e.preventDefault();const f=e.target;const date=f.date.value,start=f.start.value,end=f.end.value;const event={summary:`Interview: ${f.role.value} at ${f.company.value}`,start:{dateTime:`${date}T${start}:00+02:00`},end:{dateTime:`${date}T${end}:00+02:00`},location:f.location.value,description:f.notes.value,job_id:Number(f.dataset.jobId),event_type:'INTERVIEW'};
  const ok=await confirmAction('Add interview to Google Calendar?',`${date} ${start}–${end} · ${f.company.value}`);if(!ok)return;
  try{await api('/api/calendar/events',json('POST',{event,confirmed:true}));toast('Interview added to Calendar.');$('#interviewDialog').close();loadDashboard();}catch(err){toast(err.message,'error');}
};

function confirmAction(title,text){
  $('#confirmTitle').textContent=title;$('#confirmText').textContent=text;$('#confirmDialog').showModal();
  return new Promise(resolve=>{confirmResolve=resolve;});
}
$('#confirmCancel').onclick=()=>{if(confirmResolve)confirmResolve(false);confirmResolve=null;$('#confirmDialog').close();};
$('#confirmOk').onclick=()=>{if(confirmResolve)confirmResolve(true);confirmResolve=null;$('#confirmDialog').close();};

$('#notificationButton').onclick=()=>$('#notificationDialog').showModal();
$('#profileButton').onclick=()=>$('#profileMenu').showModal();
$$('[data-close]').forEach(b=>b.onclick=()=>document.getElementById(b.dataset.close)?.close());
$('#profileMenu').querySelectorAll('a').forEach(a=>a.onclick=()=>$('#profileMenu').close());
$('#logout').onclick=async()=>{try{await api('/api/auth/logout',{method:'POST'});location.reload();}catch(e){toast(e.message,'error');}};

let searchTimer;
$('#jobSearch').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(loadJobs,220);};
$('#minScore').onchange=loadJobs;$('#jobStatus').onchange=loadJobs;$('#workMode').onchange=renderJobs;$('#jobSort').onchange=renderJobs;
$('#globalSearch').onkeydown=e=>{if(e.key==='Enter'){location.hash='#jobs';$('#jobSearch').value=e.target.value;setTimeout(loadJobs,10);}};
$('#mobileFilters').onclick=()=>document.querySelector('.filter-panel')?.scrollIntoView({behavior:'smooth'});

setGreeting();
route();
api('/api/health').then(h=>document.title=`Tumelo Job Agent ${h.version||''}`.trim()).catch(()=>{});
