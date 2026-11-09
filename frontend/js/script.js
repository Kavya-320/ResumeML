'use strict';

const API_BASE = String(window.RESUMEML_API_BASE || '').replace(/\/+$/, '');
const VIEWS = ['home', 'how-it-works', 'features', 'screening', 'architecture', 'about'];
const VALID_EXT = /\.(pdf|docx|txt|png|jpe?g|webp)$/i;
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const MAX_FILES = 200;
const STATUS = {
  strong: { label: 'Strong match', cls: 'st-acc', pct: 'pct-hi', color: '#22c55e' },
  possible: { label: 'Possible match', cls: 'st-rev', pct: 'pct-md', color: '#eab308' },
  weak: { label: 'Weak match', cls: 'st-rej', pct: 'pct-lo', color: '#ef4444' },
};

const state = { files: [], result: null, ranked: [], filter: 'all', running: false, zipping: false, healthTimer: null, toastTimer: null };
const $ = id => document.getElementById(id);

document.addEventListener('DOMContentLoaded', () => {
  initRouter();
  initUpload();
  initScreening();
  initResultsControls();
  $('jdText').addEventListener('input', () => {
    $('charCount').textContent = $('jdText').value.length.toLocaleString() + ' characters';
  });
  $('toastX').addEventListener('click', closeToast);
  $('navBurger').addEventListener('click', toggleMenu);
  window.addEventListener('scroll', () => $('navbar').classList.toggle('scrolled', window.scrollY > 20), { passive: true });
});

function esc(value) {
  return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function toggleMenu() {
  const open = $('navLinks').classList.toggle('open');
  $('navBurger').setAttribute('aria-expanded', String(open));
}

function initRouter() {
  const route = () => {
    const id = location.hash.replace('#', '');
    showView(VIEWS.includes(id) ? id : 'home');
  };
  window.addEventListener('hashchange', route);
  route();
}

function showView(id) {
  VIEWS.forEach(v => $('view-' + v).classList.toggle('active', v === id));
  document.querySelectorAll('.nav-link').forEach(link => {
    const active = link.dataset.view === id;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
  $('navLinks').classList.remove('open');
  $('navBurger').setAttribute('aria-expanded', 'false');
  window.scrollTo(0, 0);
  if (id === 'screening') checkHealth();
}

async function checkHealth() {
  clearTimeout(state.healthTimer);
  const pill = $('healthPill');
  try {
    const res = await fetch(API_BASE + '/api/health');
    if (!res.ok) throw new Error('bad status');
    const h = await res.json();
    if (!h.model_loaded) {
      setHealth('warn', 'Backend online · loading ML model…');
      state.healthTimer = setTimeout(checkHealth, 3000);
      return;
    }
    setHealth(h.ocr_available ? 'ok' : 'warn',
      h.ocr_available ? 'Backend online · model ready' : 'Backend online · model ready · OCR unavailable (scanned files will fail)');
  } catch {
    setHealth('down', 'Backend unreachable');
    state.healthTimer = setTimeout(checkHealth, 8000);
  }
  pill.hidden = false;
}

function setHealth(stateName, text) {
  $('healthPill').dataset.state = stateName;
  $('healthText').textContent = text;
}

function fileKey(f) {
  return [f.webkitRelativePath || f.name, f.size, f.lastModified].join('|');
}

function formatSize(bytes) {
  return bytes > 1048576 ? (bytes / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(bytes / 1024)) + ' KB';
}

function initUpload() {
  const zone = $('dropZone');
  const supportsFolders = 'webkitdirectory' in $('folderInput');
  if (!supportsFolders) {
    $('folderBtn').disabled = true;
    $('folderBtn').title = 'Folder selection is not supported by this browser';
    showUploadNote('Your browser does not support folder selection. Use Select Files or drag and drop instead.');
  }
  $('folderBtn').addEventListener('click', () => $('folderInput').click());
  $('fileBtn').addEventListener('click', () => $('fileInput').click());
  $('folderInput').addEventListener('change', e => { addFiles(Array.from(e.target.files)); e.target.value = ''; });
  $('fileInput').addEventListener('change', e => { addFiles(Array.from(e.target.files)); e.target.value = ''; });
  $('clearBtn').addEventListener('click', clearFiles);
  $('fileList').addEventListener('click', e => {
    const btn = e.target.closest('[data-remove]');
    if (btn) removeFile(btn.dataset.remove);
  });
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('over'));
  zone.addEventListener('drop', async e => {
    e.preventDefault();
    zone.classList.remove('over');
    addFiles(await filesFromDrop(e.dataTransfer));
  });
}

async function filesFromDrop(dt) {
  const items = dt.items ? Array.from(dt.items) : [];
  if (!items.length || !items[0].webkitGetAsEntry) return Array.from(dt.files);
  const entries = items.map(i => i.webkitGetAsEntry()).filter(Boolean);
  const out = [];
  const walk = async entry => {
    if (entry.isFile) {
      out.push(await new Promise((resolve, reject) => entry.file(resolve, reject)));
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      let batch;
      do {
        batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
        for (const child of batch) await walk(child);
      } while (batch.length);
    }
  };
  try {
    for (const entry of entries) await walk(entry);
  } catch {
    return Array.from(dt.files);
  }
  return out;
}

function showUploadNote(text) {
  $('uploadNote').textContent = text;
  $('uploadNote').hidden = !text;
}

function addFiles(list) {
  const notes = [];
  const known = new Set(state.files.map(fileKey));
  let skippedType = 0, skippedSize = 0, duplicates = 0, overflow = 0;
  for (const f of list) {
    if (!VALID_EXT.test(f.name)) { skippedType++; continue; }
    if (f.size === 0) { skippedType++; continue; }
    if (f.size > MAX_FILE_BYTES) { skippedSize++; continue; }
    if (known.has(fileKey(f))) { duplicates++; continue; }
    if (state.files.length >= MAX_FILES) { overflow++; continue; }
    known.add(fileKey(f));
    state.files.push(f);
  }
  if (skippedType) notes.push(`${skippedType} unsupported or empty file(s) skipped`);
  if (skippedSize) notes.push(`${skippedSize} file(s) over 10 MB skipped`);
  if (duplicates) notes.push(`${duplicates} duplicate(s) ignored`);
  if (overflow) notes.push(`${overflow} file(s) beyond the ${MAX_FILES}-file limit skipped`);
  showUploadNote(notes.join(' · '));
  renderFileList();
}

function removeFile(key) {
  state.files = state.files.filter(f => fileKey(f) !== key);
  renderFileList();
}

function clearFiles() {
  state.files = [];
  showUploadNote('');
  renderFileList();
}

function renderFileList() {
  const has = state.files.length > 0;
  $('fileSummary').hidden = !has;
  if (!has) return;
  $('fileCount').textContent = state.files.length;
  $('fileSize').textContent = formatSize(state.files.reduce((s, f) => s + f.size, 0));
  const shown = state.files.slice(0, 50);
  $('fileList').innerHTML = shown.map(f => {
    const ext = f.name.split('.').pop().toLowerCase();
    const cls = ext === 'pdf' ? 'ext-pdf' : ext === 'docx' ? 'ext-docx' : ext === 'txt' ? 'ext-txt' : 'ext-img';
    const label = f.webkitRelativePath || f.name;
    return `<div class="file-row"><span class="f-ext ${cls}">${esc(ext.toUpperCase())}</span><span class="f-name" title="${esc(label)}">${esc(label)}</span><span class="f-sz">${formatSize(f.size)}</span><button type="button" class="f-del" data-remove="${esc(fileKey(f))}" title="Remove" aria-label="Remove ${esc(f.name)}">✕</button></div>`;
  }).join('') + (state.files.length > shown.length ? `<div class="f-sz" style="text-align:center;padding:4px">… and ${state.files.length - shown.length} more</div>` : '');
}

function initScreening() {
  $('runBtn').addEventListener('click', runScreening);
  $('editBtn').addEventListener('click', () => { $('resultsSection').hidden = true; $('inputPanel').hidden = false; });
  $('newBtn').addEventListener('click', () => {
    if (!confirm('Start a new screening? The current results will be cleared.')) return;
    state.result = null; state.ranked = []; state.files = [];
    $('jdText').value = ''; $('charCount').textContent = '0 characters';
    showUploadNote(''); renderFileList();
    $('resultsSection').hidden = true; $('inputPanel').hidden = false;
    window.scrollTo(0, 0);
  });
}

function setProgress(percent, message, hint, indeterminate) {
  const fill = $('spinFill');
  fill.classList.toggle('indeterminate', !!indeterminate);
  if (!indeterminate) fill.style.width = percent + '%';
  $('spinMsg').textContent = message;
  $('spinHint').textContent = hint || '';
}

function setBusy(on) {
  state.running = on;
  $('runBtn').disabled = on;
  $('spinnerOverlay').classList.toggle('show', on);
}

function sendScreening(formData, onUpload) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', API_BASE + '/api/screen');
    xhr.responseType = 'text';
    xhr.upload.onprogress = e => { if (e.lengthComputable) onUpload(e.loaded / e.total); };
    xhr.upload.onload = () => onUpload(1);
    xhr.onerror = () => reject(new Error('Cannot reach the server. Check that the backend is running and try again.'));
    xhr.ontimeout = () => reject(new Error('The request timed out.'));
    xhr.onload = () => {
      let body = null;
      try { body = JSON.parse(xhr.responseText); } catch { body = null; }
      if (xhr.status >= 200 && xhr.status < 300 && body) return resolve(body);
      reject(new Error((body && body.error) || `Server returned status ${xhr.status}.`));
    };
    xhr.send(formData);
  });
}

async function runScreening() {
  if (state.running) return;
  const jd = $('jdText').value.trim();
  if (jd.length < 30) return showToast('Job description needed', 'Paste a job description of at least 30 characters.');
  if (!state.files.length) return showToast('No resumes', 'Add at least one resume file or folder.');

  const form = new FormData();
  form.append('job_description', jd);
  state.files.forEach(f => form.append('resumes', f, f.name));

  setBusy(true);
  setProgress(0, `Uploading ${state.files.length} resume${state.files.length === 1 ? '' : 's'}…`, '0%');
  try {
    const data = await sendScreening(form, ratio => {
      if (ratio < 1) setProgress(Math.round(ratio * 100), `Uploading ${state.files.length} resume(s)…`, Math.round(ratio * 100) + '%');
      else setProgress(100, 'Extracting text and scoring resumes…', 'This can take a while for scanned files', true);
    });
    state.result = data;
    state.ranked = data.candidates.map((c, i) => ({ ...c, rank: i + 1 }));
    state.filter = 'all';
    document.querySelectorAll('.ftab').forEach(t => t.classList.toggle('on', t.dataset.filter === 'all'));
    $('searchInp').value = '';
    setBusy(false);
    showResults(jd);
  } catch (err) {
    setBusy(false);
    showToast('Screening failed', err.message);
  }
}

function showResults(jd) {
  const r = state.result;
  $('inputPanel').hidden = true;
  $('resultsSection').hidden = false;
  $('rbJd').textContent = jd.replace(/\s+/g, ' ').slice(0, 160);
  $('rbMeta').textContent = `${r.summary.total} uploaded · ${r.summary.screened} screened · ${r.summary.failed} failed`;
  $('resultsMeta').textContent = 'Ranked by resume match score (0–100). The score reflects fit to this job description, not a hiring decision.';
  const count = s => state.ranked.filter(c => c.status === s).length;
  $('statPills').innerHTML =
    `<div class="spill sp-total"><span class="sp-n">${r.summary.screened}</span> Screened</div>` +
    `<div class="spill sp-acc"><span class="sp-n">${count('strong')}</span> Strong</div>` +
    `<div class="spill sp-rev"><span class="sp-n">${count('possible')}</span> Possible</div>` +
    `<div class="spill sp-rej"><span class="sp-n">${count('weak')}</span> Weak</div>`;
  const skills = r.job.skills;
  $('jobSkills').innerHTML = skills.length
    ? 'Skills detected in job description: ' + skills.map(s => `<span class="sk sk-m">${esc(s)}</span>`).join('')
    : 'No catalog skills were detected in the job description, so the score uses semantic similarity' + (r.job.required_months ? ' and experience.' : ' only.');
  const failed = $('failedPanel');
  failed.hidden = !r.failed.length;
  failed.innerHTML = r.failed.length
    ? `<h4>${r.failed.length} file(s) could not be screened</h4><ul>${r.failed.map(f => `<li><strong>${esc(f.filename)}</strong> — ${esc(f.error)}</li>`).join('')}</ul>`
    : '';
  renderTable();
  $('resultsSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function initResultsControls() {
  $('searchInp').addEventListener('input', renderTable);
  $('sortSel').addEventListener('change', renderTable);
  $('topN').addEventListener('change', () => { $('topNResults').value = $('topN').value; renderTable(); });
  $('topNResults').addEventListener('change', () => { $('topN').value = $('topNResults').value; renderTable(); });
  $('zipBtn').addEventListener('click', downloadZip);
  $('csvBtn').addEventListener('click', exportCsv);
  $('filterGroup').addEventListener('click', e => {
    const tab = e.target.closest('.ftab');
    if (!tab) return;
    state.filter = tab.dataset.filter;
    document.querySelectorAll('.ftab').forEach(t => t.classList.toggle('on', t === tab));
    renderTable();
  });
}

function visibleRows() {
  const q = $('searchInp').value.trim().toLowerCase();
  const sort = $('sortSel').value;
  let rows = [...state.ranked];
  if (state.filter !== 'all') rows = rows.filter(c => c.status === state.filter);
  if (q) {
    rows = rows.filter(c => [c.name, c.email || '', c.filename, ...c.matched_skills, ...c.missing_skills, ...c.other_skills]
      .some(v => v.toLowerCase().includes(q)));
  }
  const months = c => (c.experience.months ?? -1);
  const sorters = {
    score_d: (a, b) => b.score - a.score || a.rank - b.rank,
    score_a: (a, b) => a.score - b.score || b.rank - a.rank,
    sim_d: (a, b) => b.semantic_similarity - a.semantic_similarity,
    exp_d: (a, b) => months(b) - months(a),
    name_a: (a, b) => a.name.localeCompare(b.name),
  };
  rows.sort(sorters[sort] || sorters.score_d);
  const limit = parseInt($('topNResults').value, 10);
  return limit > 0 ? rows.slice(0, limit) : rows;
}

function skillChips(list, cls) {
  if (!list.length) return null;
  const extra = list.length > 3 ? `<span class="sk sk-more" title="${esc(list.slice(3).join(', '))}">+${list.length - 3}</span>` : '';
  return list.slice(0, 3).map(s => `<span class="sk ${cls}">${esc(s)}</span>`).join('') + extra;
}

function resumeUrl(c) {
  return `${API_BASE}/api/resumes/${encodeURIComponent(c.resume_id)}`;
}

function renderTable() {
  if (!state.result) return;
  const rows = visibleRows();
  const tbody = $('tbody');
  if (!rows.length) {
    tbody.innerHTML = `<tr><td class="empty-td" colspan="10">${state.ranked.length ? 'No candidates match the current filters.' : 'No resumes could be screened. See the errors below.'}</td></tr>`;
    $('tblFooter').textContent = '';
    updateZipControls(rows);
    return;
  }
  tbody.innerHTML = rows.map(c => {
    const st = STATUS[c.status];
    const rankCls = c.rank <= 3 ? 'rank-' + c.rank : 'rank-n';
    const openTip = /\.docx$/i.test(c.filename) ? 'Opens a readable view of this Word resume, with a link to the original file' : 'Open the original resume';
    const missing = skillChips(c.missing_skills, 'sk-x') || (state.result.job.skills.length ? '<span style="color:#22c55e;font-size:.68rem">✓ None missing</span>' : '<span class="na">—</span>');
    const matched = skillChips(c.matched_skills, 'sk-m') || '<span class="na">—</span>';
    const sim = Math.max(0, Math.min(100, Math.round(c.semantic_similarity * 100)));
    const b = c.breakdown;
    const tip = `Semantic ${b.semantic}%` + (b.skills !== null ? ` · Skills ${b.skills}%` : '') + (b.experience !== null ? ` · Experience ${b.experience}%` : '');
    const expTitle = c.experience.source === 'unavailable' ? 'Experience could not be determined' : c.experience.source === 'dates' ? 'Calculated from employment dates' : 'Stated in the resume';
    return `<tr>
      <td><span class="rank-b ${rankCls}">${c.rank}</span></td>
      <td><a class="open-link" href="${resumeUrl(c)}" target="_blank" rel="noopener" title="${openTip}">🔗 Open</a></td>
      <td><a class="cname" href="${resumeUrl(c)}" target="_blank" rel="noopener" title="${openTip}">${esc(c.name)}</a>${c.ocr_used ? '<span class="ocr-tag" title="Text read with OCR">OCR</span>' : ''}<div class="cfile" title="${esc(c.filename)}">${esc(c.filename)}</div></td>
      <td class="mono">${c.email ? esc(c.email) : '<span class="na">Not found</span>'}</td>
      <td class="mono" title="${expTitle}">${c.experience.source === 'unavailable' ? '<span class="na">Not stated</span>' : esc(c.experience.label)}</td>
      <td><div class="sbar"><div class="sb"><div class="sb-f" style="width:${sim}%;background:linear-gradient(90deg,#3b82f6,#06b6d4)"></div></div><span class="sb-v">${c.semantic_similarity.toFixed(3)}</span></div></td>
      <td title="${esc(tip)}"><div class="score-cell"><div class="sbar" style="min-width:70px"><div class="sb"><div class="sb-f" style="width:${c.score}%;background:${st.color}"></div></div></div><span class="pct-badge ${st.pct}">${c.score.toFixed(1)}</span></div></td>
      <td><span class="status-b ${st.cls}"><span class="st-d"></span>${st.label}</span></td>
      <td><div class="skills">${missing}</div></td>
      <td><div class="skills">${matched}</div></td></tr>`;
  }).join('');
  $('tblFooter').textContent = `Showing ${rows.length} of ${state.ranked.length} screened candidates`;
  updateZipControls(rows);
}

function updateZipControls(rows) {
  if (state.zipping) return;
  $('zipBtn').disabled = !rows.length;
  $('zipBtn').textContent = '⬇ Download Selected Resumes (.zip)';
  $('zipNote').className = 'zip-note';
  $('zipNote').textContent = rows.length ? `Includes the ${rows.length} resume${rows.length === 1 ? '' : 's'} shown above, in ranked order.` : 'No resumes in the current view.';
}

async function downloadZip() {
  if (state.zipping) return;
  const rows = visibleRows();
  if (!rows.length) return;
  state.zipping = true;
  $('zipBtn').disabled = true;
  $('zipBtn').textContent = '⏳ Preparing ZIP…';
  $('zipNote').className = 'zip-note';
  $('zipNote').textContent = `Packing ${rows.length} resume${rows.length === 1 ? '' : 's'}…`;
  let note = null;
  try {
    const res = await fetch(API_BASE + '/api/resumes/zip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resume_ids: rows.map(c => c.resume_id) }),
    });
    if (!res.ok) {
      let message = `Server returned status ${res.status}.`;
      try { message = (await res.json()).error || message; } catch { message = `Server returned status ${res.status}.`; }
      throw new Error(message);
    }
    const missing = parseInt(res.headers.get('X-Missing-Resumes') || '0', 10);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'resumeml_selected_resumes.zip';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    if (missing > 0) note = { cls: 'warn', text: `${missing} resume(s) were no longer available and are not in the ZIP.` };
  } catch (err) {
    note = { cls: 'err', text: err.message };
    showToast('ZIP download failed', err.message);
  }
  state.zipping = false;
  updateZipControls(visibleRows());
  if (note) { $('zipNote').className = 'zip-note ' + note.cls; $('zipNote').textContent = note.text; }
}

function csvCell(value) {
  let s = String(value ?? '');
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return `"${s.replace(/"/g, '""')}"`;
}

function exportCsv() {
  const rows = visibleRows();
  if (!rows.length) return showToast('Nothing to export', 'There are no candidates in the current view.');
  const header = ['Rank', 'File', 'Name', 'Email', 'Experience', 'Experience Source', 'Match Score', 'Semantic Similarity', 'Skill Match %', 'Status', 'Matched Skills', 'Missing Skills'];
  const lines = rows.map(c => [
    c.rank, c.filename, c.name, c.email || '', c.experience.source === 'unavailable' ? 'Not stated' : c.experience.label, c.experience.source,
    c.score.toFixed(1), c.semantic_similarity.toFixed(4), c.skill_match_percent ?? '', STATUS[c.status].label,
    c.matched_skills.join('; '), c.missing_skills.join('; '),
  ]);
  const csv = '\ufeff' + [header, ...lines].map(r => r.map(csvCell).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  const d = new Date();
  a.href = url;
  a.download = `resumeml_results_${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function showToast(title, message) {
  $('toastTitle').textContent = title;
  $('toastBody').textContent = message;
  $('toast').classList.add('show');
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(closeToast, 8000);
}

function closeToast() {
  $('toast').classList.remove('show');
}
