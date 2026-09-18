// Mininet Lab GUI. Talks to the mn-gui JSON API; no external scripts.
// All server data is inserted with textContent, never as HTML.
'use strict';

const SVG_NS = 'http://www.w3.org/2000/svg';
const TOKEN_KEY = 'mn-gui-token';
const LEVEL_TITLES = {
  edit: 'Edit freely',
  care: 'Advanced: edit only if you know why',
  fixed: 'Do not edit',
};

const state = {
  token: null,
  status: null,
  savedText: '',
  editable: false,
  valid: true,
  validateTimer: null,
  busy: false,
  graph: null,
};

const $ = (id) => document.getElementById(id);

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (key === 'class') node.className = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) {
    if (child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function svg(tag, attrs, text) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}

// ---------------------------------------------------------------- token

function readToken() {
  const match = location.hash.match(/token=([^&]+)/);
  if (match) {
    state.token = decodeURIComponent(match[1]);
    try { sessionStorage.setItem(TOKEN_KEY, state.token); } catch (e) { /* private mode */ }
    // Remove the token from the address bar and history
    history.replaceState(null, '', location.pathname);
  } else {
    try { state.token = sessionStorage.getItem(TOKEN_KEY); } catch (e) { state.token = null; }
  }
}

function askToken() {
  const dialog = $('token-dialog');
  if (!dialog.open) dialog.showModal();
}

// ------------------------------------------------------------------ api

async function api(method, name, body) {
  if (!state.token) {
    askToken();
    throw new Error('access token needed');
  }
  const options = { method, headers: { Authorization: 'Bearer ' + state.token } };
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  const response = await fetch('/api/' + name, options);
  let data;
  try { data = await response.json(); } catch (e) { data = { error: response.statusText }; }
  if (response.status === 401) askToken();
  if (!response.ok) {
    const error = new Error(data.error || response.statusText);
    error.data = data;
    throw error;
  }
  return data;
}

function notify(message, isError) {
  const box = $('notice');
  box.textContent = message;
  box.className = 'notice' + (isError ? ' error' : '');
  box.hidden = !message;
}

async function action(button, fn) {
  if (state.busy) return;
  state.busy = true;
  const label = button ? button.textContent : '';
  if (button) { button.disabled = true; button.textContent = label + '...'; }
  try {
    notify('');
    await fn();
  } catch (e) {
    notify(e.message, true);
    if (e.data && e.data.issues) showIssues(e.data.issues);
  } finally {
    state.busy = false;
    if (button) button.textContent = label;
    await refreshStatus().catch(() => {});
  }
}

// --------------------------------------------------------------- status

async function refreshStatus() {
  const status = await api('GET', 'status');
  state.status = status;
  $('lab-name').textContent = (status.name || 'invalid configuration') + ' - ' + status.path;
  const pill = $('status-pill');
  if (status.running) { pill.textContent = 'Running'; pill.className = 'pill running'; }
  else if (!status.name) { pill.textContent = 'Config has errors'; pill.className = 'pill invalid'; }
  else { pill.textContent = 'Stopped'; pill.className = 'pill'; }
  $('btn-start').disabled = status.running || !status.name || !status.root;
  $('btn-start').title = status.root ? '' : 'Run mn-gui with sudo to start networks';
  $('btn-stop').disabled = !status.running;
  $('btn-pingall').disabled = !status.running;
  $('summary').textContent = status.summary;
  fillNodeLists(status);
  markRunning(status.running);
}

function fillSelect(select, names) {
  const previous = select.value;
  select.replaceChildren(...names.map((name) => el('option', { value: name }, name)));
  if (names.includes(previous)) select.value = previous;
}

function fillNodeLists(status) {
  const nodes = status.running ? status.nodes : [];
  fillSelect($('exec-node'), nodes);
  fillSelect($('iperf-src'), status.running ? status.hosts : []);
  fillSelect($('iperf-dst'), status.running ? status.hosts : []);
  if (status.running && status.hosts.length > 1 && $('iperf-dst').selectedIndex === 0) {
    $('iperf-dst').selectedIndex = status.hosts.length - 1;
  }
  for (const form of ['exec-form', 'iperf-form']) {
    for (const control of $(form).elements) control.disabled = !status.running;
  }
}

// ---------------------------------------------------------------- graph

function layout(graph, width, height) {
  // Small force-directed layout; starts from a circle so it is stable
  const nodes = graph.nodes.map((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(graph.nodes.length, 1);
    return { ...n, x: width / 2 + Math.cos(angle) * width / 3, y: height / 2 + Math.sin(angle) * height / 3 };
  });
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const edges = graph.links.map((l) => [byId.get(l.from), byId.get(l.to), l]).filter((e) => e[0] && e[1]);
  const k = Math.sqrt((width * height) / Math.max(nodes.length, 1)) * 0.55;
  for (let step = 0; step < 300; step++) {
    const temperature = 30 * (1 - step / 300) + 0.5;
    for (const n of nodes) { n.dx = 0; n.dy = 0; }
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        let dx = a.x - b.x, dy = a.y - b.y;
        const d = Math.max(Math.hypot(dx, dy), 0.01);
        const force = (k * k) / d;
        dx /= d; dy /= d;
        a.dx += dx * force; a.dy += dy * force;
        b.dx -= dx * force; b.dy -= dy * force;
      }
    }
    for (const [a, b, link] of edges) {
      let dx = a.x - b.x, dy = a.y - b.y;
      const d = Math.max(Math.hypot(dx, dy), 0.01);
      const force = ((d * d) / k) * (link.control ? 0.15 : 1);
      dx /= d; dy /= d;
      a.dx -= dx * force; a.dy -= dy * force;
      b.dx += dx * force; b.dy += dy * force;
    }
    for (const n of nodes) {
      n.dx += (width / 2 - n.x) * 0.02;
      n.dy += (height / 2 - n.y) * 0.02;
      const d = Math.max(Math.hypot(n.dx, n.dy), 0.01);
      n.x += (n.dx / d) * Math.min(d, temperature);
      n.y += (n.dy / d) * Math.min(d, temperature);
    }
  }
  // Fit into the view box
  const pad = 48;
  const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const scale = Math.min((width - 2 * pad) / Math.max(maxX - minX, 1), (height - 2 * pad) / Math.max(maxY - minY, 1), 1.5);
  for (const n of nodes) {
    n.x = width / 2 + (n.x - (minX + maxX) / 2) * scale;
    n.y = height / 2 + (n.y - (minY + maxY) / 2) * scale;
  }
  return { nodes, edges };
}

function drawGraph(graph) {
  const canvas = $('graph');
  state.graph = graph;
  // Draw at the element's real size so text stays readable
  const box = canvas.getBoundingClientRect();
  const width = Math.max(Math.round(box.width), 320), height = Math.max(Math.round(box.height), 300);
  canvas.setAttribute('viewBox', `0 0 ${width} ${height}`);
  canvas.replaceChildren();
  if (!graph || !graph.nodes.length) {
    canvas.append(svg('text', { x: width / 2, y: height / 2, 'text-anchor': 'middle', class: 'empty' },
      'Fix the configuration to see the topology'));
    return;
  }
  const { nodes, edges } = layout(graph, width, height);
  const edgeLayer = svg('g'), labelLayer = svg('g'), nodeLayer = svg('g');
  for (const [a, b, link] of edges) {
    edgeLayer.append(svg('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: link.control ? 'edge control' : 'edge' }));
    if (link.label) {
      labelLayer.append(svg('text', { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 6, 'text-anchor': 'middle', class: 'edge-label' }, link.label));
    }
  }
  for (const n of nodes) {
    const group = svg('g', { 'data-node': n.id, 'data-kind': n.kind });
    group.append(svg('title', {}, n.kind + ' ' + n.id));
    if (n.kind === 'host') {
      group.append(svg('circle', { class: 'halo', cx: n.x, cy: n.y, r: 20, visibility: 'hidden' }));
      group.append(svg('circle', { class: 'host', cx: n.x, cy: n.y, r: 14 }));
    } else if (n.kind === 'switch') {
      group.append(svg('rect', { class: 'switch', x: n.x - 17, y: n.y - 12, width: 34, height: 24, rx: 5 }));
    } else {
      group.append(svg('rect', { class: 'controller', x: n.x - 11, y: n.y - 11, width: 22, height: 22, transform: `rotate(45 ${n.x} ${n.y})` }));
    }
    group.append(svg('text', { x: n.x, y: n.y + 32, 'text-anchor': 'middle', class: 'node-label' }, n.id));
    nodeLayer.append(group);
  }
  canvas.append(edgeLayer, labelLayer, nodeLayer);
  markRunning(state.status && state.status.running);
}

function markRunning(running) {
  for (const halo of $('graph').querySelectorAll('.halo')) {
    halo.setAttribute('visibility', running ? 'visible' : 'hidden');
  }
}

// --------------------------------------------------------------- config

function showIssues(issues) {
  const list = $('issues');
  list.replaceChildren(...(issues || []).map((issue) =>
    el('li', {}, el('strong', {}, issue.path || 'config'), ': ', issue.message,
      issue.hint ? el('span', { class: 'hint' }, 'Hint: ' + issue.hint) : null)));
}

function updateButtons() {
  const dirty = $('editor').value !== state.savedText;
  $('btn-save').disabled = !state.editable || !dirty || !state.valid;
  $('btn-validate').disabled = !state.editable;
}

async function loadConfig() {
  const config = await api('GET', 'config');
  state.savedText = config.text;
  state.editable = config.editable;
  const editor = $('editor');
  editor.value = config.text;
  editor.readOnly = !config.editable;
  const status = state.status || {};
  $('config-info').textContent = config.editable
    ? `${status.language} file ${status.path}. Changes are checked as you type; Save writes the file.`
    : (status.editable === false && ['yaml', 'json'].includes(config.format)
      ? 'Read-only example. Start mn-gui with --config mylab.yaml to create and edit your own lab.'
      : `${status.language} program ${status.path}: edit it in your editor, then press Reload from disk.`);
  showIssues(status.issues);
  state.valid = !(status.issues && status.issues.length);
  $('valid-state').textContent = '';
  drawGraph(await api('GET', 'graph'));
  updateButtons();
}

async function validateNow() {
  if (!state.editable) return;
  const result = await api('POST', 'validate', { text: $('editor').value });
  state.valid = result.ok;
  showIssues(result.issues);
  const badge = $('valid-state');
  badge.textContent = result.ok ? 'Valid' : `${result.issues.length} problem(s)`;
  badge.className = 'small ' + (result.ok ? 'ok' : 'bad');
  if (result.ok) {
    drawGraph(result.graph);
    $('summary').textContent = result.summary;
  }
  updateButtons();
}

function scheduleValidate() {
  updateButtons();
  clearTimeout(state.validateTimer);
  state.validateTimer = setTimeout(() => validateNow().catch((e) => notify(e.message, true)), 500);
}

async function save() {
  const text = $('editor').value;
  const result = await api('POST', 'save', { text });
  showIssues(result.issues);
  if (result.ok) {
    state.savedText = text;
    notify('Saved. Stop and start the network to apply changes.');
  }
  updateButtons();
}

// -------------------------------------------------------------- console

function appendConsole(command, output, extra) {
  const box = $('console');
  box.append(el('span', { class: 'cmd' }, command + '\n'), output, extra ? extra + '\n' : '', '\n');
  box.scrollTop = box.scrollHeight;
}

async function runCommand(event) {
  event.preventDefault();
  const node = $('exec-node').value;
  const command = $('exec-cmd').value.trim();
  if (!command) return;
  await action(null, async () => {
    const result = await api('POST', 'exec', { node, command });
    appendConsole(`${node}$ ${command}`, result.output,
      result.timedOut ? '[stopped after 30 s]' : (result.exitCode ? `[exit code ${result.exitCode}]` : ''));
    $('exec-cmd').select();
  });
}

async function runIperf(event) {
  event.preventDefault();
  const src = $('iperf-src').value, dst = $('iperf-dst').value;
  await action(event.submitter, async () => {
    const result = await api('POST', 'iperf', { src, dst });
    appendConsole(`iperf ${src} -> ${dst}`, `server ${result.server}, client ${result.client}\n`);
  });
}

// -------------------------------------------------------------- results

function showPing(result) {
  const head = el('tr', {}, el('th', {}, 'from \\ to'), ...result.hosts.map((h) => el('th', {}, h)));
  const rows = result.rows.map((row) => el('tr', {}, el('th', {}, row.host),
    ...row.reached.map((ok) => ok === null ? el('td', {}, '-')
      : el('td', { class: ok ? 'yes' : 'no' }, ok ? 'yes' : 'no'))));
  const verdict = result.loss === 0 ? el('p', { class: 'ok' }, 'All hosts can reach each other (0% loss).')
    : el('p', { class: 'bad' }, `${result.loss}% of pings were lost.`);
  $('ping-result').replaceChildren(verdict,
    el('div', { class: 'matrix-wrap' }, el('table', { class: 'matrix' }, el('thead', {}, head), el('tbody', {}, ...rows))),
    result.truncated ? el('p', { class: 'muted small' }, 'Only the first 32 hosts are shown.') : null);
  selectTab('results');
}

// ---------------------------------------------------------------- guide

async function loadGuide() {
  const schema = await api('GET', 'schema');
  const groups = ['edit', 'care', 'fixed'].map((level) => {
    const fields = schema.fields.filter((f) => f.level === level);
    const list = el('dl', {});
    for (const f of fields) list.append(el('dt', {}, el('code', {}, f.path)), el('dd', {}, f.text));
    return el('div', { class: 'guide-group' }, el('h3', {}, LEVEL_TITLES[level]), list);
  });
  $('guide').replaceChildren(...groups);
}

// ----------------------------------------------------------------- tabs

function selectTab(name) {
  for (const tab of document.querySelectorAll('[role=tab]')) {
    const selected = tab.dataset.tab === name;
    tab.setAttribute('aria-selected', String(selected));
    $('pane-' + tab.dataset.tab).hidden = !selected;
  }
}

// ----------------------------------------------------------------- init

async function start() {
  readToken();
  if (!state.token) { askToken(); return; }
  try {
    await refreshStatus();
    await Promise.all([loadConfig(), loadGuide()]);
    if (!state.status.root) {
      notify('Edit-only mode: mn-gui is not running as root, so you can edit and validate but not start networks. Restart it with sudo.');
    }
  } catch (e) {
    notify(e.message, true);
  }
}

function wire() {
  for (const tab of document.querySelectorAll('[role=tab]')) {
    tab.addEventListener('click', () => selectTab(tab.dataset.tab));
  }
  $('btn-start').addEventListener('click', (e) => action(e.currentTarget, async () => {
    const result = await api('POST', 'start');
    for (const item of result.startup) appendConsole(item.command, item.output);
    notify('Network started. Try Ping all, or run commands in the Console tab.');
  }));
  $('btn-stop').addEventListener('click', (e) => action(e.currentTarget, () => api('POST', 'stop')));
  $('btn-pingall').addEventListener('click', (e) => action(e.currentTarget, async () => showPing(await api('POST', 'pingall'))));
  $('btn-validate').addEventListener('click', (e) => action(e.currentTarget, validateNow));
  $('btn-save').addEventListener('click', (e) => action(e.currentTarget, save));
  $('btn-reload').addEventListener('click', (e) => action(e.currentTarget, async () => {
    if ($('editor').value !== state.savedText && !confirm('Discard your unsaved changes?')) return;
    state.status = await api('POST', 'reload');
    await loadConfig();
  }));
  $('editor').addEventListener('input', scheduleValidate);
  $('editor').addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      if (!$('btn-save').disabled) action($('btn-save'), save);
    }
  });
  $('exec-form').addEventListener('submit', runCommand);
  $('iperf-form').addEventListener('submit', runIperf);
  $('token-form').addEventListener('submit', () => {
    state.token = $('token-input').value.trim();
    try { sessionStorage.setItem(TOKEN_KEY, state.token); } catch (e) { /* private mode */ }
    start();
  });
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (state.graph) drawGraph(state.graph); }, 200);
  });
  window.addEventListener('beforeunload', (e) => {
    if ($('editor').value !== state.savedText) e.preventDefault();
  });
}

wire();
start();
