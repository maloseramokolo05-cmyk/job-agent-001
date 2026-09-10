const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cookie = n => document.cookie.split('; ').find(x => x.startsWith(n + '='))?.split('=')[1] || '';
const json = (method, body) => ({ method, headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });

let activeJob = null;
let jobsCache = [];
let overviewCache = {};
let activeMode = 'all';
let toastTimer = null;

function toast(message, type = 'success') {
  const el = $('#toast');
  if (!el) return;
  clearTimeout(toastTimer);
  el.textContent = message;
  el.className = `toast show ${type}`;
  toastTimer = setTimeout(() => { el.className = 'toast'; }, 3600);
}

function showLogin(message = '') {
  const d = $('#loginDialog');
  if ($('#loginError')) $('#loginError').textContent = message;
  if (d && !d.open) d.showModal();
  googleBootstrapStatus();
}

async function api(u, o = {}) {
  o.headers = { ...(o.headers || {}) };
  if (!['GET', 'HEAD'].includes(o.method || 'GET')) o.headers['X-CSRF-Token'] = decodeURIComponent(cookie('job_agent_csrf'));
  const r = await fetch(u, o);
  const d = await r.json().catch(() => ({}));
  if (r.status === 401) showLogin(d.error?.message || d.detail || 'Owner authentication required');
  if (!r.ok) throw Error(d.error?.message || d.detail || 'Request failed');
  return d;
}

function initials(value = '') {
  const parts = String(value).trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return 'JOB';
  return parts.slice(0, 2).map(x => x[0]).join('').toUpperCase();
}

function formatDate(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return new Intl.DateTimeFormat('en-ZA', {day:'numeric', month:'short', year:'numeric'}).format(d);
}

function relativeTime(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  const diff = Date.now() - d.getTime();
  const mins = Math.max(0, Math.floor(diff / 60000));
  if (mins < 60) return mins <= 1 ? 'just now' : `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return formatDate(value);
}

function workMode(job) {
  const text = `${job.location || ''} ${job.work_mode || ''} ${job.description || ''}`.toLowerCase();
  if (/\bhybrid\b/.test(text)) return 'hybrid';
  if (/\bremote\b|work from home|wfh/.test(text)) return 'remote';
  if (/on[- ]?site|office[- ]?based|in[- ]?office/.test(text)) return 'on-site';
  return '';
}

function matchLabel(score) {
  const n = Number(score || 0);
  if (n >= 80) return ['High Match', 'success'];
  if (n >= 70) return ['Good Match', ''];
  return ['Possible Match', 'warning'];
}

function statusClass(status = '') {
  return /APPLIED|INTERVIEW|PREPARED|SHORTLISTED/.test(String(status)) ? 'success' : /NEEDS_USER_ACTION/.test(String(status)) ? 'warning' : '';
}

function setGreeting() {
  try {
    const parts = new Intl.DateTimeFormat('en-ZA', {hour:'numeric', hour12:false, timeZone:'Africa/Johannesburg'}).formatToParts(new Date());
    const hour = Number(parts.find(x => x.type === 'hour')?.value || 12);
    const part = hour < 12 ? 'MORNING' : hour < 18 ? 'AFTERNOON' : 'EVENING';
    $('#greeting').textContent = `GOOD ${part}, TUMELO`;
  } catch (_) {}
}

function updateActiveNav() {
  const hash = location.hash || '#dashboard';
  $$('.sidebar nav a, .mobile-nav a').forEach(a => a.classList.toggle('active', a.getAttribute('href') === hash));
}

async function googleBootstrapStatus() {
  const box = $('#googleBootstrapState');
  if (!box) return;
  try {
    const r = await fetch('/api/google/bootstrap');
    const d = await r.json();
    if (d.stored_credentials) {
      box.textContent = 'Google OAuth credentials are already stored securely.';
      const details = $('#googleBootstrap');
      if (details) details.open = false;
    } else {
      box.textContent = `Required redirect: ${d.redirect_uri}`;
    }
  } catch (_) {
    box.textContent = 'Google setup status could not be loaded.';
  }
}

$('#uploadGoogleCredentials').onclick = async () => {
  const input = $('#googleCredentialsFile'), state = $('#googleBootstrapState'), file = input?.files?.[0];
  if (!file) { state.textContent = 'Choose the Google OAuth JSON file first.'; return; }
  state.textContent = 'Saving securely…';
  const data = new FormData(); data.append('file', file);
  try {
    const r = await fetch('/api/google/bootstrap', {method:'POST', body:data});
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(d.error?.message || 'Could not save Google credentials');
    state.textContent = 'Saved. Opening Google sign-in…';
    location.href = '/api/google/callback';
  } catch (e) {
    state.textContent = e.message;
  }
};

$('#googleLogin').onclick = () => { location.href = '/api/google/callback'; };
$('#menu').onclick = () => $('.sidebar')?.classList.toggle('open');
$$('.sidebar nav a, .mobile-nav a').forEach(a => a.onclick = () => { $('.sidebar')?.classList.remove('open'); setTimeout(updateActiveNav); });
$$('.close').forEach(x => x.onclick = () => x.closest('dialog').close());
window.addEventListener('hashchange', updateActiveNav);

const metricSpec = [
  ['jobs_found','⌕','Jobs Found','Discovered opportunities'],
  ['high_match','☆','High Matches','Strongest fit scores'],
  ['prepared','▧','Prepared','CVs and documents ready'],
  ['submitted','↗','Submitted','Applications sent']
];

function renderMetrics(m) {
  $('#metrics').innerHTML = metricSpec.map(([key,icon,label,sub]) => `<div class="metric"><span class="metric-icon">${icon}</span><b>${esc(m[key] ?? 0)}</b><span>${label}</span><small>${sub}</small></div>`).join('');
}

function renderPipeline(m) {
  const steps = [
    ['Found', m.jobs_found || 0],
    ['Matched', m.high_match || 0],
    ['Prepared', m.prepared || 0],
    ['Submitted', m.submitted || 0],
    ['Interviewing', m.interviews || 0]
  ];
  $('#pipeline').innerHTML = steps.map(([label,value]) => `<div class="pipeline-step ${Number(value) ? '' : 'pending'}"><i>${Number(value) ? '✓' : '·'}</i><b>${esc(value)}</b><small>${label}</small></div>`).join('');
}

function renderCompactJobs(jobs) {
  const top = [...jobs].filter(j => Number(j.score || 0) >= 75).sort((a,b) => Number(b.score || 0) - Number(a.score || 0)).slice(0,4);
  $('#topMatches').innerHTML = top.length ? top.map(j => `<div class="compact-job"><div class="company-badge">${esc(initials(j.company))}</div><div class="compact-job-copy"><b>${esc(j.title)}</b><small>${esc(j.company)} · ${esc(j.location || 'Location unstated')}${workMode(j) ? ' · ' + esc(workMode(j)) : ''}</small></div><span class="match">${Math.round(Number(j.score || 0))}%</span><button class="row-action" onclick="detail(${Number(j.id)})" aria-label="Review ${esc(j.title)}">›</button></div>`).join('') : `<div class="empty-state"><p>No strong matches yet. Run an RSA job search and the agent will only surface roles that fit your verified CV.</p></div>`;
}

function visibleJobs() {
  if (activeMode === 'all') return jobsCache;
  return jobsCache.filter(j => workMode(j) === activeMode);
}

function renderJobs() {
  const jobs = visibleJobs();
  $('#jobCount').textContent = `${jobs.length} job${jobs.length === 1 ? '' : 's'}`;
  $('#empty').hidden = jobs.length > 0;
  $('#jobcards').innerHTML = jobs.map(j => {
    const mode = workMode(j), score = Math.round(Number(j.score || 0)), [label,labelClass] = matchLabel(score);
    return `<article class="job-card"><div class="company-badge">${esc(initials(j.company))}</div><div class="job-main"><h3>${esc(j.title)}</h3><p>${esc(j.company)} · ${esc(j.location || 'Location unstated')}</p><div class="job-meta">${mode ? `<span class="pill">${esc(mode[0].toUpperCase()+mode.slice(1))}</span>` : ''}<span class="pill ${statusClass(j.status)}">${esc(j.status || 'NEW')}</span>${j.email_verified ? '<span class="pill success">✓ Verified email route</span>' : ''}</div></div><div class="job-score"><b>${score}% match</b><small class="${labelClass}">${label}</small></div><button class="review-button" onclick="detail(${Number(j.id)})">Review</button></article>`;
  }).join('');
}

function renderApplications(apps) {
  $('#applicationList').innerHTML = apps.length ? apps.map(a => `<div class="record-row"><div class="activity-icon">↗</div><div><div class="record-title">${esc(a.title || 'Application')}</div><div class="record-sub">${esc(a.company || 'Company')} ${a.recruiter_email ? '· ' + esc(a.recruiter_email) : ''}<br>${esc(formatDate(a.application_date || a.created_at))}</div></div><span class="record-status">${esc(a.status || 'TRACKED')}</span></div>`).join('') : `<div class="empty-state"><h3>No applications tracked yet</h3><p>Applications you prepare or send will appear here automatically.</p></div>`;
}

function renderDocuments(docs, cv) {
  const rows = [];
  if (cv.available) rows.push(`<article class="document-card"><div class="doc-icon">CV</div><div><b>Master CV v${esc(cv.master_cv.version)}</b><small>${esc(cv.master_cv.original_name)}</small><a class="button secondary" href="/api/cv/download">Download</a></div></article>`);
  rows.push(...docs.map(d => `<article class="document-card"><div class="doc-icon">▧</div><div><b>${esc(d.document_type || 'Document')}</b><small>${esc(formatDate(d.created_at))}</small><a class="button secondary" href="/api/documents/${Number(d.id)}/download">Download</a></div></article>`));
  $('#documentList').innerHTML = rows.length ? rows.join('') : `<div class="empty-state"><h3>No documents yet</h3><p>Generate a job-specific CV or cover letter from a job match to see it here.</p></div>`;
  $('#masterCvState').innerHTML = cv.available ? `<p><b>✓ Master CV ready</b><br><small>${esc(cv.master_cv.original_name)} · version ${esc(cv.master_cv.version)}</small></p><a class="button secondary" href="/api/cv/download">Download master CV</a>` : `<p><b>Master CV needed</b><br><small>Upload your verified CV before generating truthful job-specific documents.</small></p>`;
}

function scopeConnected(scopes, fragment) {
  return (scopes || []).some(s => String(s).includes(fragment));
}

function renderGoogle(g) {
  const scopes = g.scopes || [];
  const cards = [
    ['Gmail','G', g.connected && (scopeConnected(scopes,'gmail.') || scopeConnected(scopes,'gmail/')), 'Send applications and track replies'],
    ['Drive','△', g.connected && scopeConnected(scopes,'drive.file'), 'Store app-created documents'],
    ['Calendar','31', g.connected && scopeConnected(scopes,'calendar.events'), 'Keep track of interviews']
  ];
  $('#googleSummary').innerHTML = cards.map(([name,icon,on,sub]) => `<div class="integration-row"><div class="integration-icon">${icon}</div><div><b>${name}</b><small>${sub}</small></div><span class="status-dot ${on?'':'off'}">● ${on?'Connected':'Not connected'}</span></div>`).join('');
  $('#googleCards').innerHTML = cards.map(([name,icon,on,sub]) => `<div class="integration-card-item"><div class="integration-icon">${icon}</div><b>${name}</b><small>${sub}</small><span class="status-dot ${on?'':'off'}">● ${on?'Connected':'Not connected'}</span></div>`).join('');
  const state = $('#googleState');
  state.className = `status-banner ${g.connected ? '' : 'off'}`;
  state.textContent = g.connected ? '✓ Google account connected' : 'Google account is not connected yet';
}

function renderProfile(c) {
  const p = c.profile || {}, prefs = c.preferences || {};
  const items = [
    ['Name',p.name || 'Not set'],['Email',p.email || 'Not set'],['Phone',p.phone || 'Not set'],['Location',p.location || 'Not set'],
    ['Target roles',(prefs.job_categories || []).join(', ') || 'Not set'],['Preferred locations',(prefs.priority_locations || []).join(', ') || 'Not set'],
    ['Skills',(p.skills || []).slice(0,8).join(', ') || 'Not set'],['Salary expectation',p.salary_expectations || 'Not set'],['Application mode',prefs.application_mode || 'Not set']
  ];
  $('#profileSummary').innerHTML = items.map(([label,value]) => `<div class="profile-item"><small>${esc(label)}</small><b>${esc(value)}</b></div>`).join('');
  $('#scheduleList').innerHTML = (prefs.schedule_times || []).length ? (prefs.schedule_times || []).map(x => `<span class="schedule-chip">${esc(x)} SAST</span>`).join('') : '<span class="section-copy">No automatic schedule times configured.</span>';
}

function renderSources(sources) {
  $('#sourceList').innerHTML = sources.length ? sources.map(s => `<div class="record-row"><div class="activity-icon">↗</div><div><div class="record-title">${esc(s.source_name)}</div><div class="record-sub">Search ${s.search_supported ? 'supported' : 'currently unavailable'}</div></div><span class="record-status source-state">${esc(s.status || 'UNKNOWN')}</span></div>`).join('') : `<div class="empty-state"><p>No source status available.</p></div>`;
}

function renderActivity(jobs, apps, docs) {
  const events = [];
  apps.forEach(a => { const date = a.application_date || a.created_at; if (date) events.push({date,icon:'↗',title:'Application updated',sub:`${a.title || 'Role'} at ${a.company || 'company'}`}); });
  docs.forEach(d => { if (d.created_at) events.push({date:d.created_at,icon:'▧',title:'Document prepared',sub:d.document_type || 'Application document'}); });
  jobs.forEach(j => { if (j.created_at) events.push({date:j.created_at,icon:'☆',title:'Job match found',sub:`${j.title || 'Role'} at ${j.company || 'company'}`}); });
  events.sort((a,b) => new Date(b.date) - new Date(a.date));
  $('#recentActivity').innerHTML = events.length ? events.slice(0,5).map(e => `<div class="activity-row"><div class="activity-icon">${e.icon}</div><div><b>${esc(e.title)}</b><small>${esc(e.sub)}</small></div><span class="activity-time">${esc(relativeTime(e.date))}</span></div>`).join('') : `<div class="empty-state"><p>Your latest searches and application activity will appear here.</p></div>`;
}

async function loadJobs() {
  const q = $('#search')?.value || '';
  const status = $('#status')?.value || '';
  jobsCache = await api(`/api/jobs?min_score=65&q=${encodeURIComponent(q)}&status=${encodeURIComponent(status)}`);
  renderJobs();
  renderCompactJobs(jobsCache);
}

async function load() {
  try {
    const [m, jobs, apps, docs, cv, g, sources, c, logs] = await Promise.all([
      api('/api/overview'), api(`/api/jobs?min_score=65&q=${encodeURIComponent($('#search')?.value || '')}&status=${encodeURIComponent($('#status')?.value || '')}`),
      api('/api/applications'), api('/api/documents'), api('/api/cv'), api('/api/google/status'), api('/api/sources'), api('/api/config'), api('/api/logs')
    ]);
    overviewCache = m; jobsCache = jobs;
    renderMetrics(m); renderPipeline(m); renderJobs(); renderCompactJobs(jobs); renderApplications(apps); renderDocuments(docs,cv); renderGoogle(g); renderProfile(c); renderSources(sources); renderActivity(jobs,apps,docs);
    $('#logLines').textContent = logs.lines?.join('\n') || 'No logs yet.';
    if ($('#loginDialog').open) $('#loginDialog').close();
  } catch (e) {
    if (!String(e.message).toLowerCase().includes('auth')) console.error(e);
  }
}

async function detail(id) {
  try {
    const j = await api('/api/jobs/' + id);
    activeJob = j;
    const score = Math.round(Number(j.score || 0));
    const email = j.email_verified && j.application_email ? `<div class="notice"><b>✓ Verified email application route</b><p>${esc(j.application_email)}</p></div><div class="actions"><button class="secondary" onclick="emailPreview(${id})">Review email</button><button class="primary" onclick="emailApply(${id})">Send application + PDF CV</button></div><div id="emailReview"></div>` : '';
    $('#detail').innerHTML = `<p class="eyebrow">${score}% MATCH</p><h2>${esc(j.title)}</h2><p class="section-copy">${esc(j.company)} · ${esc(j.location || 'Location unstated')}</p><span class="pill ${statusClass(j.status)}">${esc(j.status || 'NEW')}</span><h3>Why it matches</h3><p>${esc(j.reasoning || 'No match explanation available.')}</p><h3>Missing requirements / concerns</h3><p>${esc(j.missing_requirements || 'None recorded.')}</p>${email}<h3>Description</h3><div class="description">${esc(j.description || 'No description available.')}</div><div class="actions"><button class="secondary" onclick="action(${id},'cv')">Generate CV</button><button class="secondary" onclick="action(${id},'cover-letter')">Cover letter</button><button class="primary" onclick="openApplication()">Open original application</button></div>`;
    $('#detailModal').showModal();
  } catch (e) { toast(e.message, 'error'); }
}
window.detail = detail;

async function emailPreview(id) {
  try {
    const p = await api(`/api/jobs/${id}/email-preview`);
    const box = $('#emailReview');
    box.innerHTML = p.eligible ? `<div class="notice"><b>Email preview</b><p><b>To:</b> ${esc(p.recipient)}<br><b>Subject:</b> ${esc(p.subject)}<br><b>Attachment:</b> ${esc(p.cv_filename)}</p></div><pre>${esc(p.body)}</pre>` : `<div class="notice"><b>Send blocked</b><p>${esc(p.reason)}</p></div>`;
  } catch (e) { toast(e.message, 'error'); }
}
window.emailPreview = emailPreview;

function openApplication() { if (activeJob) window.open(activeJob.application_url || activeJob.vacancy_url, '_blank', 'noopener'); }
window.openApplication = openApplication;

async function emailApply(id) {
  if (!confirm('Send this verified email application now with the job-specific PDF CV?')) return;
  try {
    const r = await api(`/api/jobs/${id}/apply-email`, json('POST', {confirmed:true}));
    toast(r.duplicate ? 'Duplicate prevented — a matching sent application already exists.' : 'Application email sent successfully.');
    await detail(id); await load();
  } catch (e) { toast(e.message, 'error'); }
}
window.emailApply = emailApply;

async function action(id, name) {
  try { await api(`/api/jobs/${id}/${name}`, {method:'POST'}); toast(name === 'cv' ? 'Job-specific CV generated.' : 'Cover letter generated.'); await detail(id); await load(); }
  catch (e) { toast(e.message, 'error'); }
}
window.action = action;

async function setStatus(id, status) { await api(`/api/jobs/${id}/status`, json('POST', {status})); await detail(id); await load(); }
window.setStatus = setStatus;

$('#run').onclick = async () => {
  try {
    await api('/api/runs', {method:'POST'});
    $('#progress').classList.remove('hidden');
    poll();
  } catch (e) { toast(e.message, 'error'); }
};

async function poll() {
  try {
    const r = await api('/api/runs/latest');
    $('#runmsg').textContent = r.message || 'Searching South African vacancies…';
    $('#runstate').textContent = r.state || 'RUNNING';
    if (r.state === 'RUNNING') setTimeout(poll,1500);
    else { setTimeout(() => $('#progress').classList.add('hidden'),2200); toast(r.message || 'Job search complete.'); load(); }
  } catch (e) { $('#progress').classList.add('hidden'); toast(e.message, 'error'); }
}

let searchTimer;
$('#search').oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => loadJobs().catch(e => toast(e.message,'error')), 220); };
$('#status').onchange = () => loadJobs().catch(e => toast(e.message,'error'));
$('#globalSearch').oninput = e => { $('#search').value = e.target.value; clearTimeout(searchTimer); searchTimer = setTimeout(() => loadJobs().catch(err => toast(err.message,'error')), 220); };
$('#globalSearch').onkeydown = e => { if (e.key === 'Enter') location.hash = '#jobs'; };
$('#filterToggle').onclick = () => $('#filters').classList.toggle('open');
$$('.chip').forEach(chip => chip.onclick = () => { activeMode = chip.dataset.mode; $$('.chip').forEach(x => x.classList.toggle('active', x === chip)); renderJobs(); });

$('#connectGoogle').onclick = async () => { try { const r = await api('/api/google/connect', json('POST', {features:['gmail','drive','calendar']})); location.href = r.authorization_url; } catch (e) { toast(e.message,'error'); } };
$('#syncGmail').onclick = async () => { try { const r = await api('/api/gmail/sync', {method:'POST'}); toast(`${r.messages_saved || 0} job-related Gmail messages synced.`); load(); } catch (e) { toast(e.message,'error'); } };
$('#disconnectGoogle').onclick = async () => { if (confirm('Disconnect Google from this Job Agent?')) { try { await api('/api/google', {method:'DELETE'}); toast('Google disconnected.'); load(); } catch (e) { toast(e.message,'error'); } } };

$('#setup').onclick = async () => {
  try {
    const c = await api('/api/config'), f = $('#form'), p = c.profile || {}, s = c.preferences || {};
    for (const n of ['name','email','phone','location','work_authorization']) if (f[n]) f[n].value = p[n] || '';
    f.skills.value = (p.skills || []).join(', '); f.categories.value = (s.job_categories || []).join(', '); f.locations.value = (s.priority_locations || []).join(', '); f.salary.value = p.salary_expectations || ''; f.score.value = s.minimum_score || 68; f.schedule.value = (s.schedule_times || []).join(', '); f.mode.value = s.application_mode || 'AUTO_EMAIL';
    $('#wizard').showModal();
  } catch (e) { toast(e.message,'error'); }
};

$('#form').onsubmit = async e => {
  e.preventDefault();
  try {
    const f = e.target, c = await api('/api/config'), p = c.profile || {}, s = c.preferences || {};
    for (const n of ['name','email','phone','location','work_authorization']) p[n] = f[n].value;
    p.skills = f.skills.value.split(',').map(x => x.trim()).filter(Boolean); p.salary_expectations = f.salary.value;
    s.job_categories = f.categories.value.split(',').map(x => x.trim()).filter(Boolean); s.priority_locations = f.locations.value.split(',').map(x => x.trim()).filter(Boolean); s.minimum_score = +f.score.value; s.schedule_times = f.schedule.value.split(',').map(x => x.trim()).filter(Boolean); s.application_mode = f.mode.value;
    await api('/api/setup', json('POST', {profile:p,preferences:s}));
    if (f.cv.files[0]) { const data = new FormData(); data.append('file', f.cv.files[0]); await api('/api/cv', {method:'POST',body:data}); }
    $('#wizard').close(); toast('Profile and setup saved.'); load();
  } catch (err) { toast(err.message,'error'); }
};

setGreeting();
updateActiveNav();
googleBootstrapStatus();
api('/api/health').then(h => { document.title = `Tumelo Job Agent ${h.version || ''}`.trim(); if (!location.hash) location.hash = 'dashboard'; }).catch(() => {});
load();