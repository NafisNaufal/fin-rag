const $ = (id) => document.getElementById(id);
let busy = false;
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    const message = typeof data.detail === 'string' ? data.detail : 'Please check your input.';
    throw new Error(message);
  }
  return data;
}
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function status(id, message, error = false) {
  $(id).textContent = message;
  $(id).classList.toggle('error', error);
}
async function refresh() {
  const docs = await api('/api/documents');
  $('report-count').textContent = docs.length;
  const active = docs.filter(d => d.indexed);
  $('stat-reports').textContent = active.length;
  $('stat-pages').textContent = active.reduce((n, d) => n + d.pages, 0);
  $('stat-chunks').textContent = active.reduce((n, d) => n + d.chunk_count, 0);
  const selected = $('scope').value;
  $('scope').replaceChildren(new Option('All indexed reports', ''));
  $('documents').replaceChildren();
  for (const doc of docs) {
    if (doc.indexed) $('scope').add(new Option(doc.filename, doc.id));
    const card = element('div', 'document');
    card.append(element('div', 'doc-name', doc.filename));
    card.append(element('div', 'doc-meta', `${doc.pages} pages · ${doc.chunk_count} passages${doc.indexed ? '' : ' · Re-upload to reindex'}`));
    const links = element('div', 'doc-links');
    for (const [suffix, label] of [['pdf', 'View PDF ↗'], ['markdown', 'Markdown ↓']]) {
      const link = element('a', '', label);
      link.href = `/api/documents/${doc.id}/${suffix}`;
      link.target = '_blank'; link.rel = 'noopener'; links.append(link);
    }
    card.append(links);
    if (doc.warnings.length) card.append(element('p', 'warnings', doc.warnings.join(' ')));
    $('documents').append(card);
  }
  if (!docs.length) $('documents').append(element('p', 'muted', 'Your reports will appear here.'));
  if (active.some(d => d.id === selected)) $('scope').value = selected;
}
$('pdf').addEventListener('change', () => {
  $('file-label').textContent = $('pdf').files[0]?.name || 'Choose a PDF · up to 50 MB';
});
$('upload-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = $('pdf').files[0];
  if (!file) return;
  $('upload-button').disabled = true;
  status('upload-status', 'Extracting pages and indexing evidence… The first upload downloads a small embedding model.');
  const form = new FormData();
  form.append('file', file); form.append('company', $('company').value);
  if ($('year').value) form.append('year', $('year').value);
  try {
    const doc = await api('/api/documents', {method: 'POST', body: form});
    status('upload-status', `Ready · ${doc.pages} pages, ${doc.chunk_count} passages.${doc.warnings.length ? ' ' + doc.warnings.join(' ') : ''}`);
    await refresh(); $('scope').value = doc.id;
  } catch (error) {status('upload-status', error.message, true);}
  finally {$('upload-button').disabled = false;}
});
$('ask-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const question = $('question').value.trim();
  if (!question || busy) return;
  busy = true; $('ask-button').disabled = true;
  $('answer-section').hidden = true;
  status('question-status', 'Finding evidence and preparing your answer…');
  try {
    const data = await api('/api/ask', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question, document_id: $('scope').value || null, top_k: 5})});
    showAnswer(data);
    status('question-status', '');
  } catch (error) {status('question-status', error.message, true);}
  finally {busy = false; $('ask-button').disabled = false;}
});
function showAnswer(data) {
    $('answer').textContent = data.answer;
    $('answer-title').textContent = data.mode === 'excerpts' ? 'Retrieved passages' : 'Answer';
    $('answer-mode').textContent = {ollama: 'Cited answer', excerpts: 'Evidence view', no_evidence: 'Insufficient evidence', calculated: 'Verified arithmetic'}[data.mode] || data.mode;
    $('warnings').textContent = data.warnings.join(' ');
    $('sources').replaceChildren();
    for (const source of data.sources) {
      const c = source.chunk;
      const card = element('article', 'source');
      const head = element('div', 'source-head');
      head.append(element('span', 'source-tag', source.label));
      const link = element('a', '', `${c.filename} · p. ${c.page} ↗`);
      link.href = `/api/documents/${c.document_id}/pdf#page=${c.page}`;
      link.target = '_blank'; link.rel = 'noopener'; head.append(link);
      card.append(head, element('div', 'source-section', `${c.section || 'Report passage'} · ${c.kind === 'table' ? 'Table' : 'Text'}${data.mode === 'calculated' ? '' : ' · similarity ' + source.score.toFixed(3)}`), element('pre', '', c.content));
      $('sources').append(card);
    }
    $('answer-section').hidden = false; $('empty-state').hidden = true;
}
$('growth-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const documentId = $('scope').value;
  if (!documentId) {status('question-status', 'Select an indexed report above first.', true); return;}
  $('growth-button').disabled = true;
  status('question-status', 'Checking table rows and calculating…');
  try {
    const data = await api('/api/calculate/growth', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({document_id: documentId, metric: $('growth-metric').value.trim(), from_year: Number($('growth-from').value), to_year: Number($('growth-to').value)})});
    showAnswer(data);
    status('question-status', '');
  } catch (error) {status('question-status', error.message, true);}
  finally {$('growth-button').disabled = false;}
});
for (const button of document.querySelectorAll('[data-question]')) {
  button.addEventListener('click', () => {$('question').value = button.dataset.question; $('question').focus();});
}
(async () => {
  try {
    const config = await api('/api/status');
    $('mode').textContent = config.answer_mode === 'ollama' ? 'Local AI · ' + config.generation_model : 'Local · evidence view';
    await refresh();
  } catch (error) {status('question-status', 'Unable to connect. ' + error.message, true);}
})();
