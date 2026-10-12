// Reception modes as LG names them (chan_mode_name); IP = LG Channels (table ip, read-only).
const MODE_LABELS = {Satellite: 'Satellit', Cable: 'Kabel', Terrestrial: 'Antenne', IP: 'LG Channels (IP)'};
const modeLabel = mode => MODE_LABELS[mode] || mode;

'use strict';

class AdminClient {
  constructor() {
    try { this.token = sessionStorage.getItem('simToken') || ''; } catch { this.token = ''; }
    this.login = null;   // one shared login dialog, however many requests got a 401 at the same time
  }

  async request(path, body) {
    const options = { headers: { 'Content-Type': 'application/json' } };
    if (this.token) options.headers['X-Sim-Token'] = this.token;
    if (body !== undefined) { options.method = 'POST'; options.body = JSON.stringify(body); }
    const response = await fetch(path, options);
    if (response.status === 401) {
      await this.askToken(Boolean(options.headers['X-Sim-Token']));
      return this.request(path, body);
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail ? JSON.stringify(data.detail) : response.statusText);
    return data;
  }

  askToken(rejected) {
    if (this.login) return this.login;
    const dialog = document.getElementById('login');
    const input = document.getElementById('login-token');
    document.getElementById('login-error').hidden = !rejected;
    this.login = new Promise(resolve => {
      dialog.oncancel = event => event.preventDefault();   // the page is useless without the token
      document.getElementById('login-form').onsubmit = () => {
        this.token = input.value.trim();
        try { sessionStorage.setItem('simToken', this.token); } catch { /* ignore */ }
        this.login = null;
        resolve();
      };
      input.value = '';
      dialog.showModal();
      input.focus();
    });
    return this.login;
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
    this.el('scenario').onchange = () => this.renderScenario();
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
    scenarioSelect.replaceChildren(new Option('none – normales Verhalten', 'none'),
      ...scenarios.map(s => new Option(s.id, s.id)));
    this.scenarios = Object.fromEntries(scenarios.map(s => [s.id, s]));
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
    if (this.activeScenario !== s.scenario) this.el('scenario').value = s.scenario;
    this.activeScenario = s.scenario;
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
    this.ruleCounts = Object.fromEntries(s.faults.rules.map(r => [r.id, r]));
    this.renderScenario();
  }

  renderScenario() {
    const id = this.el('scenario').value;
    const active = id === this.activeScenario;
    const box = this.el('scenario-info');
    const node = (tag, text, cls) => {
      const n = document.createElement(tag);
      if (text !== undefined) n.textContent = text;
      if (cls) n.className = cls;
      return n;
    };
    const head = node('p');
    head.append(node('b', id), node('span', active ? ' · aktiv' : ' · nicht aktiv (zum Ausprobieren oben aktivieren)',
                                    active ? 'ok' : 'muted'));
    if (id === 'none' || !this.scenarios || !this.scenarios[id]) {
      box.replaceChildren(head, node('p', 'Keine Fehlerinjektion: Der simulierte TV antwortet korrekt und ändert genau '
                                           + 'das, was der Editor verlangt.', 'muted'));
      return;
    }
    const sc = this.scenarios[id];
    const facts = node('ul', undefined, 'facts');
    const fact = (label, text) => { const li = node('li'); li.append(node('b', `${label}: `), text); facts.append(li); };
    fact('Was passiert', sc.description || '–');
    fact('Startliste', sc.fixture ? `Fixture ${sc.fixture} (wird beim Aktivieren geladen)` : 'aktuelle Fixture bleibt');
    fact('Herkunft', EVIDENCE[sc.evidence] || sc.evidence);
    if (sc.read_after_write_stale_reads != null) {
      fact('Verzögerte Sicht', `Jede Änderung erscheint in der Liste erst nach ${sc.read_after_write_stale_reads} `
                               + 'weiteren Lesezugriffen.');
    }
    const parts = [head, facts];
    if (sc.rules.length) {
      parts.push(node('h3', 'Fehlerregeln'));
      const list = node('ol', undefined, 'rules');
      for (const r of sc.rules) {
        const li = node('li');
        li.append(node('b', r.id), node('span', r.description ? ` – ${r.description}` : ''));
        const counts = this.ruleCounts && this.ruleCounts[r.id];
        if (active && counts) li.append(node('span', `  ·  Treffer ${counts.matched}×, ausgelöst ${counts.fired}×`, 'muted'));
        li.append(node('div', `Auslöser: ${describeMatch(r.match)}`), node('div', `Wirkung: ${describeAction(r.action, r.times)}`));
        list.append(li);
      }
      parts.push(list);
    }
    if (sc.expectations.length) {
      parts.push(node('h3', 'Erwartung an den Editor'));
      const list = node('ul');
      for (const e of sc.expectations) {
        for (const [key, value] of Object.entries(e)) {
          list.append(node('li', EXPECTATIONS[`${key}:${value}`] || `${key}: ${JSON.stringify(value)}`));
        }
      }
      parts.push(list);
    }
    box.replaceChildren(...parts);
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
      for (const [value, cls] of [[c.number, 'num'], [c.name], [modeLabel(c.mode)], [c.channel_id, 'mono'], [c.dvb, 'mono'],
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

const EVIDENCE = {
  HARDWARE_CONFIRMED: 'am echten TV bestätigt', TRACE_CONFIRMED: 'durch Mitschnitt belegt',
  HISTORICAL_REPORTED: 'früher von Nutzern gemeldet', CURRENT_CLIENT_CONFIRMED: 'mit aktuellem Editor beobachtet',
  SIMULATOR_ASSUMPTION: 'Annahme des Simulators (nicht am TV belegt)', UNSUPPORTED: 'nicht unterstützt',
};
const COMMANDS = {
  login_check: 'Verbindungstest beim Login', backup: 'Datenbank-Sicherung (.backup)', select: 'SQL-Abfrage',
  rm: 'Löschen einer Datei', luna: 'Luna-Aufruf', sftp_read: 'SFTP-Download',
};
const EFFECTS = {
  MOVE: 'Nummer wird verschoben', SWAP: 'Nummern werden getauscht', COPY: 'statt Verschieben entsteht eine Kopie',
  REUSE_COPY: 'eine vorhandene Kopie wird wiederverwendet', DENY: 'Nummernwechsel wird abgelehnt',
};
// Keyed by "name:value" as written in the scenario files' expectations.
const EXPECTATIONS = {
  'actual_favorite_order_changed:true': 'Die Favoriten-Reihenfolge hat sich trotz Fehlermeldung tatsächlich geändert.',
  'additional_entry_on_target:true': 'Auf der Zielnummer steht zusätzlich ein neuer Eintrag (Kopie).',
  'automatic_rollback:false': 'Es gibt kein automatisches Zurückrollen bereits ausgeführter Schritte.',
  'client_gets_error:true': 'Der Editor bekommt einen Fehler gemeldet.',
  'client_needs_bounded_read_back_retries:true': 'Der Editor muss mehrfach (begrenzt) nachlesen, bis die Änderung sichtbar ist.',
  'editor_must_read_back:true': 'Der Editor muss nach dem Schreiben nachlesen, statt der Antwort zu trauen.',
  'first_two_steps_applied:true': 'Die ersten beiden Schritte sind geschrieben.',
  'fixture_unchanged:true': 'Die Senderliste bleibt unverändert.',
  'membership_changed:true': 'Die Favoriten-Zugehörigkeit hat sich trotz Fehlermeldung geändert.',
  'membership_changed:false': 'Die Favoriten-Zugehörigkeit bleibt unverändert.',
  'original_still_on_old_number:true': 'Der ursprüngliche Sender steht weiterhin auf seiner alten Nummer.',
  'state_changed:true': 'Der TV-Zustand hat sich geändert.',
  'state_unchanged:true': 'Der TV-Zustand ist unverändert.',
  'write_status_uncertain:true': 'Der Editor kann nicht wissen, ob geschrieben wurde, und muss nachlesen.',
};

function describeMatch(m) {
  const what = m.method ? `Luna-Aufruf ${m.method}` : COMMANDS[m.command || (m.service ? 'luna' : '')] || 'jeder Aufruf';
  const extra = [
    m.service && !m.method ? `Dienst ${m.service}` : '',
    m.channel_id ? `Sender ${m.channel_id}` : '', m.sim_tag ? `Sender mit Markierung „${m.sim_tag}“` : '',
    m.target_number != null ? `Zielnummer ${m.target_number}` : '', m.group ? `Favoritengruppe ${m.group}` : '',
  ].filter(Boolean);
  const nth = m.nth_call ? `der ${m.nth_call}. passende Aufruf: ` : '';
  return nth + what + (extra.length ? ` (${extra.join(', ')})` : '');
}

function describeAction(a, times) {
  const parts = [];
  if (a.disconnect === 'before') parts.push('Verbindung bricht ab, bevor etwas geschrieben wird');
  else if (a.disconnect === 'after') {
    parts.push(a.mutate === false ? 'Verbindung bricht ohne Antwort ab, nichts wird geschrieben'
      : 'Änderung wird geschrieben, dann bricht die Verbindung ohne Antwort ab');
  }
  else parts.push(a.mutate === false ? 'Änderung wird NICHT ausgeführt' : 'Änderung wird ausgeführt');
  if (a.effect) parts.push(EFFECTS[a.effect] || a.effect);
  if (a.response) parts.push(`${a.response_mode === 'merge' ? 'Antwort ergänzt um' : 'Antwort lautet'} ${JSON.stringify(a.response)}`);
  if (a.stale_reads != null) parts.push(`erst nach ${a.stale_reads} Lesezugriffen sichtbar`);
  if (a.stale_ms != null) parts.push(`erst nach ${a.stale_ms} ms (virtuell) sichtbar`);
  if (a.exit_status != null) parts.push(`Exit-Status ${a.exit_status}`);
  if (a.stderr) parts.push(`Fehlerausgabe „${a.stderr.trim()}“`);
  if (a.hang_ms) parts.push(`Antwort kommt erst nach ${a.hang_ms / 1000} s`);
  if (a.sftp_abort_after_bytes != null) parts.push(`Download bricht nach ${a.sftp_abort_after_bytes} Bytes ab`);
  const freq = times == null ? 'bei jedem Treffer' : times === 1 ? 'einmalig' : `bis zu ${times}-mal`;
  return `${parts.join('; ')} (${freq})`;
}

function fmt(snapshot) {
  if (!snapshot) return '–';
  if (snapshot.channelId === undefined) return JSON.stringify(snapshot);
  return `${snapshot.number} ${snapshot.channelId} [${snapshot.groups.join('')}]`;
}

new AdminPage().start().catch(e => { document.getElementById('message').textContent = e.message; });
