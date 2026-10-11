// Reception modes as LG names them (chan_mode_name); IP = LG Channels (table ip, read-only).
const MODE_LABELS = {Satellite: 'Satellit', Cable: 'Kabel', Terrestrial: 'Antenne', IP: 'LG Channels (IP)'};
const modeLabel = mode => MODE_LABELS[mode] || mode;

'use strict';

class AdminClient {
  constructor() {
    try { this.token = sessionStorage.getItem('simToken') || ''; } catch { this.token = ''; }
  }

  async request(path, body) {
    const options = { headers: { 'Content-Type': 'application/json' } };
    if (this.token) options.headers['X-Sim-Token'] = this.token;
    if (body !== undefined) { options.method = 'POST'; options.body = JSON.stringify(body); }
    const response = await fetch(path, options);
    if (response.status === 401) {
      const token = window.prompt('Admin-Token (X-Sim-Token):') || '';
      this.token = token;
      try { sessionStorage.setItem('simToken', token); } catch { /* ignore */ }
      if (token) return this.request(path, body);
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail ? JSON.stringify(data.detail) : response.statusText);
    return data;
  }
}

class AdminPage {
  constructor() {
    this.client = new AdminClient();
    this.channels = [];
    this.lastSeq = 0;
    this.journalRows = [];
    this.el = id => document.getElementById(id);
  }

  async start() {
    this.bind();
    await this.loadLists();
    await this.refresh();
    setInterval(() => this.refresh().catch(e => this.message(e.message, true)), 2000);
  }

  bind() {
    this.el('reset').onclick = () => this.confirmed('Simulator auf die gewählte Fixture zurücksetzen?', () =>
      this.client.request('/api/reset', { confirm: true, fixture: this.el('fixture').value }));
    this.el('activate').onclick = () => this.confirmed('Szenario aktivieren und Simulator zurücksetzen?', () =>
      this.client.request('/api/scenarios/activate', { confirm: true, scenario: this.el('scenario').value }));
    this.el('snapshot').onclick = () => this.run(() => this.client.request('/api/snapshots', { label: '' }));
    this.el('restore').onclick = () => {
      const snapshot = this.el('snapshots').value;
      if (!snapshot) return this.message('Kein Snapshot vorhanden.', true);
      this.confirmed(`Zustand ${snapshot} wiederherstellen? Der aktuelle Simulatorzustand wird überschrieben.`, () =>
        this.client.request('/api/snapshots/restore', { confirm: true, snapshot }));
    };
    for (const id of ['search', 'mode-filter', 'group-filter']) this.el(id).oninput = () => this.renderChannels();
    this.el('show-sim').onchange = e => document.body.classList.toggle('show-sim', e.target.checked);
    const groups = this.el('group-filter');
    for (const g of 'ABCDEFGH') groups.append(new Option(`Gruppe ${g}`, g));
  }

  async confirmed(question, action) {
    if (!window.confirm(question)) return;
    await this.run(action);
  }

  async run(action) {
    try {
      const result = await action();
      this.message('OK' + (result && result.snapshot ? `: ${result.snapshot}` : ''));
      this.lastSeq = 0; this.journalRows = [];
      await this.refresh();
    } catch (e) { this.message(e.message, true); }
  }

  message(text, error = false) {
    const node = this.el('message');
    node.textContent = text;
    node.className = error ? 'bad' : 'muted';
  }

  async loadLists() {
    const [fixtures, scenarios] = await Promise.all([this.client.request('/api/fixtures'),
                                                    this.client.request('/api/scenarios')]);
    const fixtureSelect = this.el('fixture');
    fixtureSelect.replaceChildren(...fixtures.map(f => new Option(f, f)));
    const scenarioSelect = this.el('scenario');
    scenarioSelect.replaceChildren(new Option('none – keine Fehlerinjektion', 'none'),
      ...scenarios.map(s => new Option(`${s.id} – ${s.description}`, s.id)));
  }

  async refresh() {
    const status = await this.client.request('/api/status');
    this.renderStatus(status);
    if (status.events < this.lastSeq || status.run_id !== this.runId) {
      this.lastSeq = 0; this.journalRows = []; this.runId = status.run_id;
      this.channelsHash = null;
    }
    if (status.state_hash !== this.channelsHash) {
      this.channels = await this.client.request('/api/channels');
      this.channelsHash = status.state_hash;
      this.renderModes();
      this.renderChannels();
    }
    const events = await this.client.request(`/api/journal?since=${this.lastSeq}`);
    if (events.length) {
      this.lastSeq = events[events.length - 1].seq;
      this.journalRows = this.journalRows.concat(events).slice(-1000);
      this.renderJournal();
    }
  }

  card(label, value, title) {
    const card = document.createElement('div'); card.className = 'card';
    const b = document.createElement('b'); b.textContent = label;
    const span = document.createElement('span'); span.textContent = value;
    if (title) span.title = title;
    card.append(b, span); return card;
  }

  renderStatus(s) {
    this.el('conn').textContent = s.ssh ? `SSH/SFTP: ${s.username}@${s.ssh.host}:${s.ssh.port}` : 'SSH nicht gestartet';
    this.el('fixture').value = s.fixture;
    this.el('scenario').value = s.scenario;
    const cards = [
      ['Fixture', s.fixture], ['Profil', s.profile], ['Szenario', s.scenario],
      ['Sender', `${s.channels + s.ip.channels} (${[...Object.entries(s.modes), ['IP', s.ip.channels]]
        .filter(([, n]) => n).map(([m, n]) => `${modeLabel(m)} ${n}`).join(', ')})`],
      ['Favoriten', Object.entries(s.favorites).filter(([, n]) => n).map(([g, n]) => `${g}:${n}`).join(' ') || '–'],
      ['SSH-Sitzungen', `${s.connections} (schreibend: ${s.active_writers.length})`],
      ['Verzögerte Sicht', s.stale_view ? `${s.stale_view.remaining_reads} Reads / bis ${s.stale_view.until_virtual_ms} ms` : 'nein'],
    ];
    const details = [
      ['Run-ID', s.run_id], ['Fixture-Hash', s.fixture_hash.slice(0, 16), s.fixture_hash],
      ['Zustands-Hash', s.state_hash.slice(0, 16), s.state_hash], ['Event-Hash', s.event_hash.slice(0, 16), s.event_hash],
      ['Virtuelle Zeit', `${s.virtual_ms} ms`],
    ];
    this.el('cards').replaceChildren(...cards.map(card => this.card(...card)));
    this.el('detail-cards').replaceChildren(...details.map(card => this.card(...card)));
    const snaps = this.el('snapshots');
    const current = snaps.value;
    snaps.replaceChildren(...s.snapshots.map(id => new Option(id, id)));
    if (s.snapshots.includes(current)) snaps.value = current;
    const rules = s.faults.rules;
    this.el('faults').textContent = rules.length
      ? rules.map(r => `${r.id}: ${r.description || ''} (passend ${r.matched}×, ausgelöst ${r.fired}×)`).join('\n')
      : 'Keine Fehlerregeln aktiv.';
    this.el('faults').style.whiteSpace = 'pre-line';
  }

  renderModes() {
    const select = this.el('mode-filter');
    const current = select.value;
    const counts = {};
    for (const c of this.channels) counts[c.mode] = (counts[c.mode] || 0) + 1;
    const modes = [...Object.keys(MODE_LABELS), ...Object.keys(counts).filter(m => !(m in MODE_LABELS)).sort()];
    select.replaceChildren(new Option('alle Modi', ''),
      ...modes.map(m => new Option(`${modeLabel(m)} (${counts[m] || 0})`, m)));
    select.value = modes.includes(current) ? current : '';
  }

  renderChannels() {
    const query = this.el('search').value.trim().toLowerCase();
    const mode = this.el('mode-filter').value;
    const group = this.el('group-filter').value;
    const rows = this.channels.filter(c =>
      (!mode || c.mode === mode) && (!group || c.groups.includes(group)) &&
      (!query || `${c.number} ${c.name} ${c.channel_id}`.toLowerCase().includes(query)));
    const body = this.el('channels');
    body.replaceChildren(...rows.map(c => {
      const tr = document.createElement('tr');
      const groups = c.groups.map(g => `${g}${c.index[g] + 1}`).join(' ');
      const origin = [c.copy_of ? 'Kopie' : '', c.id_history.length > 1 ? `IDs: ${c.id_history.length}` : '',
                      ...c.tags].filter(Boolean).join(', ');
      if (c.read_only) tr.className = 'read-only';
      const name = c.read_only ? `${c.name} · nur lesbar` : c.name;
      for (const [value, cls] of [[c.number, 'num'], [name], [modeLabel(c.mode)], [c.channel_id, 'mono'], [c.dvb, 'mono'],
                                  [groups], [c.satellite_lcn ? 'ja' : ''], [origin], [c.sim_entry_id, 'mono sim']]) {
        const td = document.createElement('td');
        td.textContent = value ?? '';
        if (cls) td.className = cls;
        tr.append(td);
      }
      return tr;
    }));
  }

  renderJournal() {
    const body = this.el('journal');
    const rows = this.journalRows.slice().reverse().slice(0, 400);
    body.replaceChildren(...rows.map(e => {
      const tr = document.createElement('tr');
      const call = e.kind === 'luna' ? `${e.method || ''} ${JSON.stringify(e.params ?? '')}`
        : (e.command || e.op || e.fixture || e.snapshot || '');
      const response = e.response !== undefined ? JSON.stringify(e.response) : (e.exit_status ?? '');
      const truth = e.true_response ? ` (wahr: ${JSON.stringify(e.true_response)})` : '';
      const effect = [e.effect, e.rule, e.fault ? `FEHLER: ${e.fault}` : ''].filter(Boolean).join(' · ');
      const changes = (e.mutations || []).map(m => `${m.note}: ${fmt(m.before)} → ${fmt(m.after)}`)
        .concat((e.suppressed_mutations || []).map(m => `unterdrückt: ${m.note}`)).join('\n');
      for (const [value, cls] of [[e.seq, 'num'], [e.virtual_ms, 'num'], [e.kind], [call, 'mono'],
                                  [String(response).slice(0, 300) + truth, 'mono'], [effect, e.fault ? 'fault' : ''],
                                  [changes, 'mono']]) {
        const td = document.createElement('td');
        td.textContent = value ?? '';
        if (cls) td.className = cls;
        td.style.whiteSpace = 'pre-line';
        tr.append(td);
      }
      return tr;
    }));
  }
}

function fmt(snapshot) {
  if (!snapshot) return '–';
  if (snapshot.channelId === undefined) return JSON.stringify(snapshot);
  return `${snapshot.number} ${snapshot.channelId} [${snapshot.groups.join('')}]`;
}

new AdminPage().start().catch(e => { document.getElementById('message').textContent = e.message; });
