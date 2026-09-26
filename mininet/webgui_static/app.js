// Mininet Lab GUI: a topology editor (MiniEdit in the browser) over the
// mn-gui JSON API. No external scripts; all server data is inserted with
// textContent, never as HTML.
'use strict';

const SVG_NS = 'http://www.w3.org/2000/svg';
const TOKEN_KEY = 'mn-gui-token';
const LEVEL_TITLES = {
  edit: 'Edit freely',
  care: 'Advanced: edit only if you know why',
  fixed: 'Do not edit',
};
const HOST_FIELDS = [
  { key: 'name', label: 'Name', placeholder: 'h1' },
  { key: 'ip', label: 'IP address', placeholder: '10.0.0.1/24' },
  { key: 'mac', label: 'MAC (advanced)', placeholder: '00:00:00:00:00:01' },
  { key: 'gateway', label: 'Gateway (advanced)', placeholder: '10.0.0.254' },
];
const SWITCH_FIELDS = [
  { key: 'name', label: 'Name', placeholder: 's1' },
  { key: 'dpid', label: 'DPID (advanced)', placeholder: '0000000000000001' },
  { key: 'protocols', label: 'OpenFlow (advanced)', placeholder: 'OpenFlow13' },
];
const LINK_FIELDS = [
  { key: 'bw', label: 'Bandwidth (Mbit/s)', placeholder: '10', number: true },
  { key: 'delay', label: 'Delay', placeholder: '5ms' },
  { key: 'loss', label: 'Loss (%)', placeholder: '0', number: true },
  { key: 'max_queue', label: 'Queue (packets)', placeholder: '100', number: true },
];

const state = {
  token: null,
  status: null,
  config: null,        // the configuration being edited
  graph: null,         // { nodes, links, editable }
  positions: new Map(),  // laid-out positions, id -> { x, y }
  savedText: '',
  editable: false,
  valid: true,
  validateTimer: null,
  busy: false,
  tool: 'select',
  selection: null,     // { kind: 'node'|'link', id } / { from, to }
  linkStart: null,
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
  // The server only accepts JSON for POST (part of its CSRF protection),
  // so actions without parameters send an empty JSON object
  if (method === 'POST' && body === undefined) body = {};
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

// Actions run one at a time, in the order they were triggered: clicking
// Save while another change is still being applied must not lose it
let queue = Promise.resolve();

function action(button, fn) {
  queue = queue.then(() => runAction(button, fn)).catch(() => {});
  return queue;
}

async function runAction(button, fn) {
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
  // Don't overwrite the summary of unsaved edits with the file's
  if ($('editor').value === state.savedText) $('summary').textContent = status.summary;
  fillNodeLists(status);
  updateEditHint();
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

// ------------------------------------------------------------ edit mode

function canEdit() {
  return state.editable && !(state.status && state.status.running);
}

function updateEditHint() {
  const hint = $('edit-hint');
  const arrange = $('btn-arrange');
  if (state.status && state.status.running) {
    hint.textContent = 'The network is running: stop it to edit the topology.';
  } else if (!state.status || !state.status.editable) {
    hint.textContent = 'Read-only: start mn-gui with --config mylab.yaml to edit.';
  } else if (!state.editable) {
    hint.textContent = 'Built-in topology - convert it below to edit nodes.';
  } else if (state.tool === 'link') {
    hint.textContent = state.linkStart ? 'Click the second node (Esc to cancel).'
      : 'Click two nodes to link them.';
  } else if (state.tool === 'host' || state.tool === 'switch') {
    hint.textContent = 'Click the canvas to place a ' + state.tool + '.';
  } else if (state.tool === 'delete') {
    hint.textContent = 'Click a node or link to delete it.';
  } else {
    hint.textContent = 'Drag to move, click to edit, or pick a tool.';
  }
  arrange.disabled = !canEdit();
  for (const button of document.querySelectorAll('.tool')) {
    const active = button.dataset.tool === state.tool;
    button.setAttribute('aria-pressed', String(active));
    button.disabled = !canEdit() && button.dataset.tool !== 'select';
  }
}

function setTool(tool) {
  state.tool = tool;
  state.linkStart = null;
  drawGraph(state.graph);
  updateEditHint();
}

function uniqueName(prefix) {
  const taken = new Set((state.graph ? state.graph.nodes : []).map((n) => n.id));
  for (let i = 1; i < 1000; i++) {
    if (!taken.has(prefix + i)) return prefix + i;
  }
  return prefix + Date.now();
}

// Apply a change to the configuration: the server turns it back into
// file text, so the editor and the canvas always agree
async function applyConfig(config, message) {
  const result = await api('POST', 'format', { config });
  showIssues(result.issues || []);
  if (!result.ok) {
    state.valid = false;
    notify('That change is not valid; see the problems listed.', true);
    updateButtons();
    return false;
  }
  state.config = result.config;
  state.valid = true;
  state.editable = !!(result.graph && result.graph.editable) &&
    !!(state.status && state.status.editable);
  $('props').hidden = true;
  $('editor').value = result.text;
  $('summary').textContent = result.summary;
  drawGraph(result.graph);
  $('valid-state').textContent = 'Valid - not saved yet';
  $('valid-state').className = 'small';
  if (message) notify(message);
  updateEditHint();
  showProperties();
  showConvertBanner();
  updateButtons();
  return true;
}

function configCopy() {
  return JSON.parse(JSON.stringify(state.config));
}

function nodeList(config, kind) {
  return kind === 'host' ? config.hosts : config.switches;
}

async function addNode(kind, x, y) {
  const config = configCopy();
  const name = uniqueName(kind === 'host' ? 'h' : 's');
  nodeList(config, kind).push({ name, x: Math.round(x), y: Math.round(y) });
  await applyConfig(config);
  select({ kind: 'node', id: name });
}

async function addLink(from, to) {
  if (from === to) return;
  const config = configCopy();
  const exists = config.links.some((l) =>
    (l.from === from && l.to === to) || (l.from === to && l.to === from));
  if (exists) {
    notify('Those nodes are already linked.');
    return;
  }
  config.links.push({ from, to });
  await applyConfig(config);
  select({ kind: 'link', from, to });
}

async function deleteNode(id) {
  const config = configCopy();
  for (const kind of ['hosts', 'switches']) {
    config[kind] = config[kind].filter((n) => n.name !== id);
  }
  config.links = config.links.filter((l) => l.from !== id && l.to !== id);
  config.run = (config.run || []).filter((c) => c.split(' ')[0] !== id);
  state.selection = null;
  await applyConfig(config);
}

async function deleteLink(from, to) {
  const config = configCopy();
  config.links = config.links.filter((l) =>
    !((l.from === from && l.to === to) || (l.from === to && l.to === from)));
  state.selection = null;
  await applyConfig(config);
}

async function moveNode(id, x, y) {
  const config = configCopy();
  for (const kind of ['hosts', 'switches']) {
    for (const node of config[kind]) {
      if (node.name === id) { node.x = Math.round(x); node.y = Math.round(y); }
    }
  }
  await applyConfig(config);
}

async function autoArrange() {
  const config = configCopy();
  const box = $('graph').getBoundingClientRect();
  const laid = layout({ nodes: state.graph.nodes.map((n) => ({ id: n.id, kind: n.kind })),
                        links: state.graph.links },
                      Math.max(Math.round(box.width), 320),
                      Math.max(Math.round(box.height), 300), true);
  const byId = new Map(laid.nodes.map((n) => [n.id, n]));
  for (const kind of ['hosts', 'switches']) {
    for (const node of config[kind]) {
      const placed = byId.get(node.name);
      if (placed) { node.x = Math.round(placed.x); node.y = Math.round(placed.y); }
    }
  }
  await applyConfig(config);
}

async function convertToNodes() {
  const config = configCopy();
  const graph = state.graph;
  const positions = state.positions;
  const nodeOf = (id) => {
    const p = positions.get(id);
    return p ? { name: id, x: Math.round(p.x), y: Math.round(p.y) } : { name: id };
  };
  config.hosts = graph.nodes.filter((n) => n.kind === 'host').map((n) => nodeOf(n.id));
  config.switches = graph.nodes.filter((n) => n.kind === 'switch').map((n) => nodeOf(n.id));
  const shaping = (config.topology && config.topology.link) || {};
  config.links = graph.links.filter((l) => !l.control)
    .map((l) => Object.assign({ from: l.from, to: l.to }, shaping));
  config.topology = null;
  await applyConfig(config, 'Converted to editable hosts, switches and links.');
}

// ------------------------------------------------------------ selection

function select(selection) {
  state.selection = selection;
  drawGraph(state.graph);
  showProperties();
}

function findNode(id) {
  for (const kind of ['hosts', 'switches']) {
    const found = (state.config[kind] || []).find((n) => n.name === id);
    if (found) return { node: found, kind: kind === 'hosts' ? 'host' : 'switch' };
  }
  return null;
}

function findLink(from, to) {
  return (state.config.links || []).find((l) =>
    (l.from === from && l.to === to) || (l.from === to && l.to === from));
}

function propertyForm(title, fields, values, onApply, onDelete) {
  const form = el('form', { class: 'prop-form' });
  form.append(el('h3', {}, title));
  const grid = el('div', { class: 'prop-grid' });
  for (const field of fields) {
    const id = 'prop-' + field.key;
    const input = el('input', {
      id, type: 'text', autocomplete: 'off',
      placeholder: field.placeholder || '',
    });
    input.value = values[field.key] === undefined ? '' : String(values[field.key]);
    input.disabled = !canEdit();
    grid.append(el('label', { for: id }, field.label), input);
  }
  form.append(grid);
  const buttons = el('div', { class: 'row' });
  const apply = el('button', { class: 'primary', type: 'submit' }, 'Apply');
  const remove = el('button', { type: 'button' }, 'Delete');
  apply.disabled = !canEdit();
  remove.disabled = !canEdit();
  buttons.append(apply, remove);
  form.append(buttons);
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const values2 = {};
    for (const field of fields) {
      const raw = $('prop-' + field.key).value.trim();
      if (raw === '') continue;
      values2[field.key] = field.number ? Number(raw) : raw;
    }
    action(apply, () => onApply(values2));
  });
  remove.addEventListener('click', () => action(remove, onDelete));
  return form;
}

function showProperties() {
  const box = $('props');
  const selection = state.selection;
  if (!selection || !state.config) { box.hidden = true; box.replaceChildren(); return; }
  box.hidden = false;
  if (selection.kind === 'node') {
    const found = findNode(selection.id);
    if (!found) { box.hidden = true; return; }
    const fields = found.kind === 'host' ? HOST_FIELDS : SWITCH_FIELDS;
    box.replaceChildren(propertyForm(
      (found.kind === 'host' ? 'Host ' : 'Switch ') + selection.id, fields, found.node,
      async (values) => {
        const config = configCopy();
        const list = nodeList(config, found.kind);
        const index = list.findIndex((n) => n.name === selection.id);
        const position = { x: list[index].x, y: list[index].y };
        const renamed = values.name && values.name !== selection.id;
        list[index] = Object.assign({}, position, values);
        if (renamed) {
          for (const link of config.links) {
            if (link.from === selection.id) link.from = values.name;
            if (link.to === selection.id) link.to = values.name;
          }
          config.run = (config.run || []).map((c) =>
            c.split(' ')[0] === selection.id ? values.name + c.slice(selection.id.length) : c);
        }
        if (await applyConfig(config)) select({ kind: 'node', id: values.name || selection.id });
      },
      () => deleteNode(selection.id)));
  } else {
    const link = findLink(selection.from, selection.to);
    if (!link) { box.hidden = true; return; }
    box.replaceChildren(propertyForm(
      'Link ' + link.from + ' - ' + link.to, LINK_FIELDS, link,
      async (values) => {
        const config = configCopy();
        const index = config.links.findIndex((l) =>
          (l.from === link.from && l.to === link.to));
        config.links[index] = Object.assign({ from: link.from, to: link.to }, values);
        if (await applyConfig(config)) select(selection);
      },
      () => deleteLink(link.from, link.to)));
  }
}

// ---------------------------------------------------------------- graph

function layout(graph, width, height, force) {
  // Nodes with saved positions stay where they are; the rest get a
  // small force-directed layout, starting from a circle so it is stable
  const nodes = graph.nodes.map((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(graph.nodes.length, 1);
    const fixed = !force && typeof n.x === 'number' && typeof n.y === 'number';
    return {
      ...n, fixed,
      x: fixed ? n.x : width / 2 + Math.cos(angle) * width / 3,
      y: fixed ? n.y : height / 2 + Math.sin(angle) * height / 3,
    };
  });
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const edges = graph.links.map((l) => [byId.get(l.from), byId.get(l.to), l]).filter((e) => e[0] && e[1]);
  const loose = nodes.filter((n) => !n.fixed);
  if (loose.length) {
    const k = Math.sqrt((width * height) / Math.max(nodes.length, 1)) * 0.55;
    for (let step = 0; step < 300; step++) {
      const temperature = 30 * (1 - step / 300) + 0.5;
      for (const n of nodes) { n.dx = 0; n.dy = 0; }
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          let dx = a.x - b.x, dy = a.y - b.y;
          const d = Math.max(Math.hypot(dx, dy), 0.01);
          const f = (k * k) / d;
          dx /= d; dy /= d;
          a.dx += dx * f; a.dy += dy * f;
          b.dx -= dx * f; b.dy -= dy * f;
        }
      }
      for (const [a, b, link] of edges) {
        let dx = a.x - b.x, dy = a.y - b.y;
        const d = Math.max(Math.hypot(dx, dy), 0.01);
        const f = ((d * d) / k) * (link.control ? 0.15 : 1);
        dx /= d; dy /= d;
        a.dx -= dx * f; a.dy -= dy * f;
        b.dx += dx * f; b.dy += dy * f;
      }
      for (const n of nodes) {
        if (n.fixed) continue;
        n.dx += (width / 2 - n.x) * 0.02;
        n.dy += (height / 2 - n.y) * 0.02;
        const d = Math.max(Math.hypot(n.dx, n.dy), 0.01);
        n.x += (n.dx / d) * Math.min(d, temperature);
        n.y += (n.dy / d) * Math.min(d, temperature);
      }
    }
    if (!nodes.some((n) => n.fixed)) {
      const pad = 56;
      const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y);
      const minX = Math.min(...xs), maxX = Math.max(...xs);
      const minY = Math.min(...ys), maxY = Math.max(...ys);
      const scale = Math.min((width - 2 * pad) / Math.max(maxX - minX, 1),
        (height - 2 * pad) / Math.max(maxY - minY, 1), 1.5);
      for (const n of nodes) {
        n.x = width / 2 + (n.x - (minX + maxX) / 2) * scale;
        n.y = height / 2 + (n.y - (minY + maxY) / 2) * scale;
      }
    }
  }
  for (const n of nodes) {
    n.x = Math.min(Math.max(n.x, 28), width - 28);
    n.y = Math.min(Math.max(n.y, 28), height - 34);
  }
  return { nodes, edges };
}

function isSelectedNode(id) {
  return state.selection && state.selection.kind === 'node' && state.selection.id === id;
}

function isSelectedLink(link) {
  const s = state.selection;
  return s && s.kind === 'link' &&
    ((s.from === link.from && s.to === link.to) || (s.from === link.to && s.to === link.from));
}

function drawGraph(graph) {
  const canvas = $('graph');
  state.graph = graph;
  const box = canvas.getBoundingClientRect();
  const width = Math.max(Math.round(box.width), 320);
  const height = Math.max(Math.round(box.height), 300);
  canvas.setAttribute('viewBox', `0 0 ${width} ${height}`);
  canvas.replaceChildren();
  canvas.dataset.tool = state.tool;
  if (!graph || !graph.nodes.length) {
    canvas.append(svg('text', { x: width / 2, y: height / 2, 'text-anchor': 'middle', class: 'empty' },
      state.config ? 'Empty lab - pick the host tool and click here' :
        'Fix the configuration to see the topology'));
    return;
  }
  const { nodes, edges } = layout(graph, width, height);
  state.positions = new Map(nodes.map((n) => [n.id, { x: n.x, y: n.y }]));

  const edgeLayer = svg('g'), labelLayer = svg('g'), nodeLayer = svg('g');
  for (const [a, b, link] of edges) {
    const line = svg('line', {
      x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      class: 'edge' + (link.control ? ' control' : '') + (isSelectedLink(link) ? ' selected' : ''),
    });
    if (!link.control) {
      line.classList.add('clickable');
      line.addEventListener('click', (e) => {
        e.stopPropagation();
        if (state.tool === 'delete') action(null, () => deleteLink(link.from, link.to));
        else select({ kind: 'link', from: link.from, to: link.to });
      });
    }
    edgeLayer.append(line);
    if (link.label) {
      labelLayer.append(svg('text', {
        x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 6, 'text-anchor': 'middle', class: 'edge-label',
      }, link.label));
    }
  }
  for (const n of nodes) {
    const group = svg('g', {
      'data-node': n.id, 'data-kind': n.kind,
      class: 'node' + (isSelectedNode(n.id) ? ' selected' : '') +
        (state.linkStart === n.id ? ' linking' : ''),
    });
    group.append(svg('title', {}, n.kind + ' ' + n.id));
    if (n.kind === 'host') {
      group.append(svg('circle', { class: 'halo', cx: n.x, cy: n.y, r: 20, visibility: 'hidden' }));
      group.append(svg('circle', { class: 'host', cx: n.x, cy: n.y, r: 14 }));
    } else if (n.kind === 'switch') {
      group.append(svg('rect', { class: 'switch', x: n.x - 17, y: n.y - 12, width: 34, height: 24, rx: 5 }));
    } else {
      group.append(svg('rect', {
        class: 'controller', x: n.x - 11, y: n.y - 11, width: 22, height: 22,
        transform: `rotate(45 ${n.x} ${n.y})`,
      }));
    }
    group.append(svg('text', { x: n.x, y: n.y + 32, 'text-anchor': 'middle', class: 'node-label' }, n.id));
    if (n.kind !== 'controller') wireNode(group, n);
    nodeLayer.append(group);
  }
  canvas.append(edgeLayer, labelLayer, nodeLayer);
  canvas.onclick = (event) => {
    if (event.target !== canvas) return;
    if ((state.tool === 'host' || state.tool === 'switch') && canEdit()) {
      const point = canvasPoint(event);
      action(null, () => addNode(state.tool, point.x, point.y));
    } else {
      select(null);
    }
  };
  markRunning(state.status && state.status.running);
}

function canvasPoint(event) {
  const canvas = $('graph');
  const rect = canvas.getBoundingClientRect();
  const viewBox = canvas.viewBox.baseVal;
  return {
    x: (event.clientX - rect.left) * (viewBox.width / rect.width),
    y: (event.clientY - rect.top) * (viewBox.height / rect.height),
  };
}

function wireNode(group, node) {
  let drag = null;
  group.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    event.stopPropagation();
    if (state.tool === 'delete' && canEdit()) {
      action(null, () => deleteNode(node.id));
      return;
    }
    if (state.tool === 'link' && canEdit()) {
      if (!state.linkStart) {
        state.linkStart = node.id;
        drawGraph(state.graph);
        updateEditHint();
      } else {
        const from = state.linkStart;
        state.linkStart = null;
        updateEditHint();
        action(null, () => addLink(from, node.id));
      }
      return;
    }
    if (!canEdit()) { select({ kind: 'node', id: node.id }); return; }
    const start = canvasPoint(event);
    drag = { moved: false, dx: node.x - start.x, dy: node.y - start.y };
    group.setPointerCapture(event.pointerId);
  });
  group.addEventListener('pointermove', (event) => {
    if (!drag) return;
    const point = canvasPoint(event);
    const x = point.x + drag.dx, y = point.y + drag.dy;
    if (Math.hypot(x - node.x, y - node.y) > 2) drag.moved = true;
    node.x = x; node.y = y;
    moveNodeShapes(group, node);
  });
  group.addEventListener('pointerup', (event) => {
    if (!drag) return;
    group.releasePointerCapture(event.pointerId);
    const moved = drag.moved;
    drag = null;
    if (moved) action(null, () => moveNode(node.id, node.x, node.y));
    else select({ kind: 'node', id: node.id });
  });
}

function moveNodeShapes(group, node) {
  for (const shape of group.children) {
    if (shape.tagName === 'circle') { shape.setAttribute('cx', node.x); shape.setAttribute('cy', node.y); }
    else if (shape.tagName === 'rect') {
      const w = Number(shape.getAttribute('width')), h = Number(shape.getAttribute('height'));
      shape.setAttribute('x', node.x - w / 2);
      shape.setAttribute('y', node.y - h / 2);
    } else if (shape.tagName === 'text') {
      shape.setAttribute('x', node.x); shape.setAttribute('y', node.y + 32);
    }
  }
  state.positions.set(node.id, { x: node.x, y: node.y });
  redrawEdges();
}

function redrawEdges() {
  const graph = state.graph;
  if (!graph) return;
  const lines = $('graph').querySelectorAll('line');
  const edges = graph.links.filter((l) => state.positions.has(l.from) && state.positions.has(l.to));
  edges.forEach((link, i) => {
    const a = state.positions.get(link.from), b = state.positions.get(link.to);
    const line = lines[i];
    if (!line) return;
    line.setAttribute('x1', a.x); line.setAttribute('y1', a.y);
    line.setAttribute('x2', b.x); line.setAttribute('y2', b.y);
  });
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
  $('btn-save').disabled = !(state.status && state.status.editable) || !dirty || !state.valid;
  $('btn-validate').disabled = !(state.status && state.status.editable);
}

function showConvertBanner() {
  const box = $('props');
  if (state.editable || !state.config || !state.config.topology ||
      !(state.status && state.status.editable) ||
      (state.status && state.status.running)) {
    return;
  }
  const button = el('button', { class: 'primary', type: 'button' },
    'Convert to editable nodes');
  button.addEventListener('click', (e) => action(e.currentTarget, convertToNodes));
  box.hidden = false;
  box.replaceChildren(el('div', { class: 'prop-form' },
    el('h3', {}, 'Built-in topology'),
    el('p', { class: 'small muted' },
      'This lab uses the built-in "' + state.config.topology.type +
      '" topology. Convert it into hosts, switches and links to edit it here.'),
    el('div', { class: 'row' }, button)));
}

async function loadConfig() {
  const config = await api('GET', 'config');
  state.savedText = config.text;
  const editor = $('editor');
  editor.value = config.text;
  editor.readOnly = !config.editable;
  const status = state.status || {};
  $('config-info').textContent = config.editable
    ? `${status.language} file ${status.path}. Edit the topology on the left or the file here; both stay in step.`
    : (status.editable === false && ['yaml', 'json'].includes(config.format)
      ? 'Read-only example. Start mn-gui with --config mylab.yaml to create and edit your own lab.'
      : `${status.language} program ${status.path}: edit it in your editor, then press Reload from disk.`);
  await validateNow(true);
}

async function validateNow(quiet) {
  const result = await api('POST', 'validate', { text: $('editor').value });
  state.valid = result.ok;
  showIssues(result.issues);
  const badge = $('valid-state');
  badge.textContent = result.ok ? (quiet ? '' : 'Valid') : `${result.issues.length} problem(s)`;
  badge.className = 'small ' + (result.ok ? 'ok' : 'bad');
  if (result.ok) {
    state.config = result.config;
    state.editable = !!(result.graph && result.graph.editable) &&
      !!(state.status && state.status.editable);
    drawGraph(result.graph);
    $('summary').textContent = result.summary;
    state.selection = null;
    $('props').hidden = true;
    showConvertBanner();
  }
  updateEditHint();
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
    notify('Saved.' + (state.status && state.status.running
      ? ' Stop and start the network to apply the changes.' : ''));
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
  const parts = [verdict,
    el('div', { class: 'matrix-wrap' }, el('table', { class: 'matrix' }, el('thead', {}, head), el('tbody', {}, ...rows)))];
  if (result.truncated) parts.push(el('p', { class: 'muted small' }, 'Only the first 32 hosts are shown.'));
  $('ping-result').replaceChildren(...parts);
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
    const dialog = $('token-dialog');
    if (dialog.open) dialog.close();
    notify('');
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
  for (const button of document.querySelectorAll('.tool')) {
    button.addEventListener('click', () => setTool(button.dataset.tool));
  }
  $('btn-arrange').addEventListener('click', (e) => action(e.currentTarget, autoArrange));
  $('btn-start').addEventListener('click', (e) => action(e.currentTarget, async () => {
    const result = await api('POST', 'start');
    for (const item of result.startup) appendConsole(item.command, item.output);
    notify('Network started. Try Ping all, or run commands in the Console tab.');
  }));
  $('btn-stop').addEventListener('click', (e) => action(e.currentTarget, () => api('POST', 'stop')));
  $('btn-pingall').addEventListener('click', (e) => action(e.currentTarget, async () => showPing(await api('POST', 'pingall'))));
  $('btn-validate').addEventListener('click', (e) => action(e.currentTarget, () => validateNow()));
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
  document.addEventListener('keydown', (e) => {
    if (e.target.matches('input, textarea')) return;
    if (e.key === 'Escape') { state.linkStart = null; setTool('select'); select(null); }
    else if (e.key === 'h') setTool('host');
    else if (e.key === 's') setTool('switch');
    else if (e.key === 'l') setTool('link');
    else if ((e.key === 'Delete' || e.key === 'Backspace') && state.selection && canEdit()) {
      e.preventDefault();
      const selection = state.selection;
      action(null, () => selection.kind === 'node'
        ? deleteNode(selection.id) : deleteLink(selection.from, selection.to));
    }
  });
  // Pasting a new #token=... URL only changes the hash: no page reload
  window.addEventListener('hashchange', () => {
    if (/token=/.test(location.hash)) start();
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
