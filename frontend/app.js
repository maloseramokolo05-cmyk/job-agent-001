const $ = s => document.querySelector(s);
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cookie = n => document.cookie.split('; ').find(x => x.startsWith(n + '='))?.split('=')[1] || '';
const showLogin = () => { const d = $('#loginDialog'); if (d && !d.open) d.showModal(); };
const api = async (u, o = {}) => {
  o.headers = { ...(o.headers || {}) };
  if (!['GET', 'HEAD'].includes(o.method || 'GET')) o.headers['X-CSRF-Token'] = decodeURIComponent(cookie('job_agent_csrf'));
  const r = await fetch(u, o);
  const d = await r.json().catch(() => ({}));
  if (r.status === 401) showLogin();
  if (!r.ok) throw Error(d.error?.message || d.detail || 'Request failed');
  return d;
};
const json = (method, body) => ({ method, headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });

let activeJob = null;

$('#googleLogin').onclick = () => { location.href = '/api/google/callback'; };
$('#menu').onclick = () => $('#nav').classList.toggle('open');
document.querySelectorAll('nav a').forEach(a => a.onclick = () => $('#nav').classList.remove('open'));
$('#filterToggle').onclick = () => $('#filters').classList.toggle('open');
document.querySelectorAll('.close').forEach(x => x.onclick = () => x.closest('dialog').close());

const metrics = {jobs_found:'Jobs discovered',high_match:'High matches',prepared:'Prepared',submitted:'Submitted',needs_input:'Needs action',interviews:'Interviews',rejected:'Rejected',awaiting_response:'Awaiting response',runs_today:'Runs today',last_run:'Last run'};

async function load() {
  try {
    const m = await api('/api/overview');
    $('#metrics').innerHTML = Object.entries(metrics).map(([k,v]) => `<div class=metric><b>${esc(m[k] || 0)}</b><span>${v}</span></div>`).join('');
    const jobs = await api(`/api/jobs?q=${encodeURIComponent($('#search').value)}&status=${encodeURIComponent($('#status').value)}`);
    $('#empty').hidden = jobs.length;
    $('#jobcards').innerHTML = jobs.map(j => `<article class=card><div class=cardtop><div class=score>${Math.round(j.score || 0)}</div><div><div class=title>${esc(j.title)}</div><div class=sub>${esc(j.company)} · ${esc(j.location || 'Location unstated')}</div></div></div><span class=pill>${esc(j.status)}</span>${j.email_verified ? '<small>✓ Verified email application route</small>' : ''}<button onclick="detail(${j.id})">Review</button></article>`).join('');
    const apps = await api('/api/applications');
    const docs = await api('/api/documents');
    $('#applicationList').innerHTML = apps.length ? apps.map(a => `<p><b>${esc(a.title)}</b> · ${esc(a.company)}<br><small>${esc(a.status)} · ${esc(a.application_date || a.created_at)}${a.recruiter_email ? ' · ' + esc(a.recruiter_email) : ''}</small></p>`).join('') : '<p>No applications tracked yet.</p>';
    $('#documentList').innerHTML = docs.length ? docs.map(d => `<p><b>${esc(d.document_type)}</b><br><small>${esc(d.created_at)}</small><br><a class="button" href="/api/documents/${d.id}/download">Download</a></p>`).join('') : '<p>No generated documents yet.</p>';
    const cv = await api('/api/cv');
    $('#masterCvState').innerHTML = cv.available ? `<p><b>Master CV v${esc(cv.master_cv.version)}</b><br><small>${esc(cv.master_cv.original_name)}</small></p><a class="button" href="/api/cv/download">Download master CV</a>` : '<p><b>No master CV uploaded</b></p>';
    const g = await api('/api/google/status');
    $('#googleState').innerHTML = `<p><b>${g.connected ? 'CONNECTED' : 'NOT CONNECTED'}</b></p><small>Scopes: ${esc((g.scopes || []).join(', ') || 'none')}</small>`;
    const sources = await api('/api/sources');
    $('#sourceList').innerHTML = sources.map(s => `<p><b>${esc(s.source_name)}</b> · ${esc(s.status)}<br><small>Search ${s.search_supported ? 'supported' : 'unavailable'} · verified published email routes may be automated</small></p>`).join('');
    const c = await api('/api/config');
    $('#scheduleList').textContent = (c.preferences.schedule_times || []).map(x => x + ' SAST').join(' · ');
    const logs = await api('/api/logs');
    $('#logLines').textContent = logs.lines.join('\n') || 'No logs yet.';
    if ($('#loginDialog').open) $('#loginDialog').close();
  } catch (e) {
    if (!String(e.message).includes('Authentication')) console.error(e);
  }
}

async function detail(id) {
  const j = await api('/api/jobs/' + id);
  activeJob = j;
  const email = j.email_verified && j.application_email ? `<h3>Verified email route</h3><p>${esc(j.application_email)}</p><div class="actions"><button onclick="emailPreview(${id})">Review email</button><button class="primary" onclick="emailApply(${id})">Send application email + PDF CV</button></div><div id="emailReview"></div>` : '';
  $('#detail').innerHTML = `<p class=eyebrow>MATCH SCORE ${esc(j.score || 0)}</p><h2>${esc(j.title)}</h2><p>${esc(j.company)} · ${esc(j.location)}</p><span class=pill>${esc(j.status)}</span><h3>Why it matches</h3><p>${esc(j.reasoning)}</p><h3>Missing requirements / concerns</h3><p>${esc(j.missing_requirements)}</p>${email}<h3>Description</h3><div class=description>${esc(j.description)}</div><div class=actions><button onclick="action(${id},'cv')">Generate CV</button><button onclick="action(${id},'cover-letter')">Cover letter</button><button onclick="openApplication()">Open original application</button></div>`;
  $('#detailModal').showModal();
}

async function emailPreview(id) {
  try {
    const p = await api(`/api/jobs/${id}/email-preview`);
    const box = $('#emailReview');
    box.innerHTML = p.eligible ? `<h3>Email preview</h3><p><b>To:</b> ${esc(p.recipient)}<br><b>Subject:</b> ${esc(p.subject)}<br><b>Attachment:</b> ${esc(p.cv_filename)}</p><pre>${esc(p.body)}</pre>` : `<p><b>Send blocked:</b> ${esc(p.reason)}</p>`;
  } catch (e) { alert(e.message); }
}

function openApplication() { if (activeJob) window.open(activeJob.application_url || activeJob.vacancy_url, '_blank', 'noopener'); }

async function emailApply(id) {
  if (!confirm('Send this verified email application now with the job-specific PDF CV?')) return;
  try {
    const r = await api(`/api/jobs/${id}/apply-email`, json('POST', {confirmed:true}));
    alert(r.duplicate ? 'Duplicate application prevented. A matching sent application already exists.' : 'Application email sent successfully.');
    await detail(id); load();
  } catch (e) { alert(e.message); }
}

async function action(id, name) { try { await api(`/api/jobs/${id}/${name}`, {method:'POST'}); await detail(id); load(); } catch (e) { alert(e.message); } }
async function setStatus(id, status) { await api(`/api/jobs/${id}/status`, json('POST', {status})); await detail(id); load(); }

$('#run').onclick = async () => { try { await api('/api/runs', {method:'POST'}); $('#progress').classList.remove('hidden'); poll(); } catch (e) { alert(e.message); } };
async function poll() { const r = await api('/api/runs/latest'); $('#runmsg').textContent = r.message; $('#runstate').textContent = r.state; if (r.state === 'RUNNING') setTimeout(poll,1500); else { setTimeout(() => $('#progress').classList.add('hidden'),2500); load(); } }

$('#search').oninput = load;
$('#status').onchange = load;
$('#connectGoogle').onclick = async () => { try { const r = await api('/api/google/connect', json('POST', {features:['gmail','drive','calendar']})); location.href = r.authorization_url; } catch (e) { alert(e.message); } };
$('#syncGmail').onclick = async () => { try { const r = await api('/api/gmail/sync', {method:'POST'}); alert(`${r.messages_saved} job-related messages saved`); load(); } catch (e) { alert(e.message); } };
$('#disconnectGoogle').onclick = async () => { if (confirm('Disconnect Google from this Job Agent?')) { await api('/api/google', {method:'DELETE'}); load(); } };

$('#setup').onclick = async () => {
  const c = await api('/api/config'), f = $('#form'), p = c.profile, s = c.preferences;
  for (const n of ['name','email','phone','location','work_authorization']) if (f[n]) f[n].value = p[n] || '';
  f.skills.value = (p.skills || []).join(', '); f.categories.value = (s.job_categories || []).join(', '); f.locations.value = (s.priority_locations || []).join(', '); f.salary.value = p.salary_expectations || ''; f.score.value = s.minimum_score || 68; f.schedule.value = (s.schedule_times || []).join(', '); f.mode.value = s.application_mode || 'AUTO_EMAIL'; $('#wizard').showModal();
};

$('#form').onsubmit = async e => {
  e.preventDefault(); const f = e.target, c = await api('/api/config'), p = c.profile, s = c.preferences;
  for (const n of ['name','email','phone','location','work_authorization']) p[n] = f[n].value;
  p.skills = f.skills.value.split(',').map(x => x.trim()).filter(Boolean); p.salary_expectations = f.salary.value; s.job_categories = f.categories.value.split(',').map(x => x.trim()).filter(Boolean); s.priority_locations = f.locations.value.split(',').map(x => x.trim()).filter(Boolean); s.minimum_score = +f.score.value; s.schedule_times = f.schedule.value.split(',').map(x => x.trim()).filter(Boolean); s.application_mode = f.mode.value;
  await api('/api/setup', json('POST', {profile:p,preferences:s}));
  if (f.cv.files[0]) { const data = new FormData(); data.append('file', f.cv.files[0]); await api('/api/cv', {method:'POST',body:data}); }
  $('#wizard').close(); alert('Setup saved.'); load();
};

api('/api/health').then(h => { document.title = `Tumelo Job Agent ${h.version}`; if (!location.hash) location.hash = 'dashboard'; }).catch(() => {});
load();
