const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num = n => Math.round(n).toLocaleString();
const dps = n => n >= 100 ? num(n) : (n || 0).toFixed(1);
const clock = t => new Date(t * 1000).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
const dt = t => new Date(t * 1000).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'});
const mmss = s => `${Math.floor(s / 60)}:${String(Math.round(s) % 60).padStart(2, '0')}`;

let char = '';          // '' = follow active log
let tab = 'parser';
let selFight = null;
let followLive = true;
let skySrc = 'all';
let skyRunes = [];
const collapsed = new Set(JSON.parse(localStorageGet('eqlc-collapsed') || '[]'));

function localStorageGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function localStorageSet(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
const q = () => char ? `char=${encodeURIComponent(char)}` : '';
async function get(path) { const r = await fetch(path, {cache:'no-store'}); return r.ok ? r.json() : null; }
async function post(path, body) {
  const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  return r.json();
}

// ---------- tabs / character ----------
$$('nav button').forEach(b => b.onclick = () => {
  tab = b.dataset.tab;
  $$('nav button').forEach(x => x.classList.toggle('on', x === b));
  $$('.tab').forEach(t => t.classList.toggle('on', t.id === 'tab-' + tab));
  refresh();
});
$('#charsel').onchange = e => { char = e.target.value; selFight = null; followLive = true; refresh(); };
$$('[data-open]').forEach(b => b.onclick = async () => {
  const label = b.textContent;
  const r = await post('/api/overlay/open', {kind: b.dataset.open});
  b.textContent = r.ok ? 'Opened ✓' : 'Could not open';
  setTimeout(() => b.textContent = label, 2000);
});

// characters are per server: "Sahkage_rivervale" is shown as "Sahkage (rivervale)"
const charLabel = c => { if (!c) return '—'; const i = c.indexOf('_'); return i < 0 ? c : `${c.slice(0, i)} (${c.slice(i + 1)})`; };
function fillChars(list, active) {
  const sel = $('#charsel');
  const want = ['', ...list];
  const cur = [...sel.options].map(o => o.value);
  if (JSON.stringify(cur) !== JSON.stringify(want) || sel.options[0]?.text !== `Active: ${charLabel(active)}`) {
    sel.innerHTML = want.map(v => `<option value="${esc(v)}">${v ? esc(charLabel(v)) : 'Active: ' + esc(charLabel(active))}</option>`).join('');
    sel.value = char;
  }
}

// ---------- parser ----------
async function refreshParser() {
  const o = await get('/api/overlay?' + q());
  if (o) {
    const c = o.current;
    $('#k-now').textContent = c ? dps(c.dps) : '—';
    $('#k-now').className = c && c.active ? 'green' : '';
    $('#k-now-sub').textContent = c ? `${c.target} · ${mmss(c.duration)} · ${num(c.dmg)} dmg${c.active ? '' : ' (last)'}` : 'no fights yet';
    $('#k-avg-lbl').textContent = `Last ${o.avg_target} avg`;
    $('#k-avg').textContent = o.avg_n ? dps(o.avg) : '—';
    $('#k-avg-sub').textContent = o.avg_n ? `${o.avg_n} fights counted` : '';
    $('#k-best').textContent = o.avg_n ? dps(o.best) : '—';
    if (o.motes) {
      const m = o.motes;
      $('#k-motes').textContent = m.count.toLocaleString();
      $('#k-motes-rate').textContent = m.count ? `· ${dps(m.per_hour)}/hr` : '';
      $('#k-tiers').innerHTML = m.tiers.map(t => `<span>${esc(t.label)}</span><span>${t.count.toLocaleString()}</span>`).join('');
      $('#k-motes-sub').textContent = 'this session, since the app opened at ' + clock(m.since);
    }
    updateTimerBadge(o.timers || []);
  }
  const f = await get('/api/fights?' + q());
  if (!f) return;
  const list = f.fights;
  if (followLive && list.length) selFight = list[0].id;
  $('#fights').innerHTML = list.length ? list.map(x => `
    <div class="fight ${x.id === selFight ? 'sel' : ''} ${x.done ? '' : 'live'}" data-id="${x.id}">
      <div class="n">${esc(x.name)}</div><div class="d">${dps(x.dps)}</div>
      <div class="m">${clock(x.start)} · ${mmss(x.duration)} · ${num(x.you)} dmg · raid ${dps(x.raid_dps)}</div>
    </div>`).join('') : '<div class="empty">No fights parsed yet.<br>Go hit something.</div>';
  $$('.fight').forEach(el => el.onclick = () => {
    selFight = +el.dataset.id; followLive = selFight === list[0].id; refreshParser();
  });
  if (selFight) renderFight(await get(`/api/fight?id=${selFight}&` + q()));
}

let logSide = 'all';
const TYPE_LABEL = {you: 'you', player: 'group', pet: 'pet'};

function renderFight(d) {
  if (!d || !d.id) { $('#fight-detail').innerHTML = '<div class="empty">Pick a fight on the left.</div>'; return; }
  const keepScroll = $('#fight-detail .log')?.scrollTop || 0;
  // ---- players & group
  const top = Math.max(1, ...d.players.map(c => c.total));
  const prow = d.players.map(c => `
    <tr class="click ${c.name === 'You' ? 'you' : ''}" data-bd-name="${esc(c.name)}" data-bd-side="friend" title="Click for misses, resists and tips">
      <td class="bar"><i style="width:${100 * c.total / top}%"></i><span>${esc(c.name)}<span class="tag-type ${c.type}">${TYPE_LABEL[c.type]}</span></span></td>
      <td>${num(c.total)}</td><td>${c.pct}%</td><td><b>${dps(c.dps)}</b></td><td>${dps(c.sdps)}</td>
      <td>${c.hits}</td><td>${c.acc == null ? '—' : c.acc + '%'}</td><td>${num(c.max)}</td><td>${c.crits}</td>
      <td class="red">${c.taken ? num(c.taken) : '—'}</td>
      <td>${c.total ? Object.entries(c.kinds).map(([k, v]) => `${k} ${Math.round(100 * v / c.total)}%`).join(' · ') : ''}</td>
    </tr>`).join('');
  // ---- NPCs
  const ntop = Math.max(1, ...d.npcs.map(c => c.taken));
  const nrow = d.npcs.map(c => `
    <tr class="npc-row click" data-bd-name="${esc(c.name)}" data-bd-side="npc" title="Click for its breakdown">
      <td class="bar npc"><i style="width:${100 * c.taken / ntop}%"></i><span>${esc(c.name)}</span></td>
      <td>${num(c.taken)}</td><td>${c.dead ? 'slain' : '<span class="muted">alive</span>'}</td>
      <td>${num(c.total)}</td><td><b>${dps(c.dps)}</b></td><td>${c.hits}</td><td>${c.avoid == null ? '—' : c.avoid + '%'}</td><td>${num(c.max)}</td>
      <td class="targets">${c.targets.map(t => `${esc(t.name)} ${num(t.dmg)}`).join(' · ') || '—'}</td>
    </tr>`).join('');
  const you = d.players.find(c => c.name === 'You');
  const spells = you && Object.keys(you.spells).length ? `<h3>Your spells / DoTs</h3><table>
    <tr><th>Spell</th><th>Damage</th><th>%</th></tr>
    ${Object.entries(you.spells).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${num(v)}</td><td>${Math.round(100 * v / you.total)}%</td></tr>`).join('')}</table>` : '';
  // ---- combat log
  const lines = d.log.filter(e => logSide === 'all' || e.side === logSide || e.side === 'death' ||
    (e.side === 'spell' && logSide === 'friend'))
    .slice(-500).reverse();
  const logHtml = lines.map(e => {
    if (e.side === 'spell') {
      const what = {cast: 'begins casting', resist: 'resisted', fizzle: 'fizzled', interrupt: 'interrupted',
        immune: 'target immune', nohold: 'did not take hold', 'you resisted': 'you resisted'}[e.kind] || e.kind;
      const txt = e.kind === 'you resisted' ? `You resisted ${esc(e.spell)}` :
        `You: ${esc(e.spell || 'spell')} <span class="muted">${what}${e.kind === 'resist' && e.tgt ? ' by ' + esc(e.tgt) : ''}</span>`;
      return `<div class="spell"><span class="ts">+${mmss(e.t)}</span><span class="who">${txt}</span><span></span></div>`;
    }
    if (!e.amt && e.kind !== 'death' && e.kind !== 'melee' && e.kind !== 'spell' && e.kind !== 'dot')
      return `<div class="${e.side} avoid"><span class="ts">+${mmss(e.t)}</span>
        <span class="who">${esc(e.src)} → ${esc(e.tgt)} <span class="muted">${esc(e.kind)}</span></span><span class="amt">—</span></div>`;
    if (e.side === 'death') return `<div class="death"><span class="ts">+${mmss(e.t)}</span><span class="who">${esc(e.tgt)} died${e.src ? ' (' + esc(e.src) + ')' : ''}</span><span></span></div>`;
    const how = e.spell ? esc(e.spell) : e.kind;
    return `<div class="${e.side} ${e.crit ? 'crit' : ''}"><span class="ts">+${mmss(e.t)}</span>
      <span class="who">${esc(e.src)} → ${esc(e.tgt)} <span class="muted">${how}${e.crit ? ' · crit' : ''}</span></span>
      <span class="amt">${num(e.amt)}</span></div>`;
  }).join('') || '<div><span></span><span class="muted">Nothing for this filter.</span><span></span></div>';

  $('#fight-detail').innerHTML = `
    <div class="panel-h"><span>${esc(d.name)} ${d.done ? '' : '<span class="badge">LIVE</span>'}</span>
      <span class="muted">${dt(d.start)} · ${mmss(d.duration)} · raid ${dps(d.raid_dps)} dps
        <button class="primary" id="deep-open" style="margin-left:10px" title="Every hit, miss, cast and resist, with percentages">Deep dive</button></span></div>
    <div class="side-h"><span class="dot" style="background:var(--blue)"></span>Players &amp; group</div>
    <table><tr><th>Name</th><th>Damage</th><th>%</th><th>DPS</th><th title="DPS over own active time">SDPS</th>
      <th>Hits</th><th title="Melee hits ÷ melee swings">Acc</th><th>Max</th><th>Crits</th><th>Taken</th><th>Type</th></tr>${prow}</table>
    <div class="side-h"><span class="dot" style="background:var(--red)"></span>NPCs</div>
    <table><tr><th>NPC</th><th>Damage taken</th><th>Status</th><th>Damage dealt</th><th>DPS</th><th>Hits</th><th title="Share of your side's swings it avoided">Avoids</th><th>Max</th><th style="text-align:left">Hit most</th></tr>${nrow}</table>
    ${spells}
    <div class="side-h">Combat log
      <span class="seg" id="logseg" style="margin:0 0 0 auto">
        <button data-side="all" class="${logSide === 'all' ? 'on' : ''}">All</button>
        <button data-side="friend" class="${logSide === 'friend' ? 'on' : ''}">Players &amp; group</button>
        <button data-side="npc" class="${logSide === 'npc' ? 'on' : ''}">NPCs</button></span></div>
    <div class="log">${logHtml}</div>`;
  $('#fight-detail .log').scrollTop = keepScroll;
  $('#deep-open').onclick = () => openDeep(d.id);
  $$('#logseg button').forEach(b => b.onclick = () => { logSide = b.dataset.side; renderFight(d); });
  $$('#fight-detail tr[data-bd-name]').forEach(tr => tr.onclick = () => openBreakdown(d.id, tr.dataset.bdName, tr.dataset.bdSide));
}

$('#clear-fights').onclick = async () => {
  if (confirm('Clear fight history for this character? (Sky tracking is not affected.)')) {
    await post('/api/fights/clear', {char}); selFight = null; refreshParser();
  }
};

// ---------- plane of sky ----------
$('#hide-done').onchange = $('#only-ready').onchange = () => refreshSky();
$$('.seg button').forEach(b => b.onclick = () => {
  skySrc = b.dataset.src; $$('.seg button').forEach(x => x.classList.toggle('on', x === b)); refreshSky();
});

let skyBusy = false;
async function refreshSky() {
  if (skyBusy) return;
  skyBusy = true;
  try {
    const d = await get('/api/sky?' + q());
    if (!d || !d.char) { $('#classes').innerHTML = '<div class="empty">No character yet — set your Logs folder in Settings.</div>'; return; }
    const unlocked = d.classes.filter(c => c.unlocked).length;
    $('#sky-sum').textContent = `${charLabel(d.char)}: ${d.done}/${d.total} tests done · ${unlocked}/${d.classes.length} classes unlocked` +
      (d.inventory ? ` · inventory: ${d.inventory.source}, ${dt(d.inventory.t)}` : ' · tip: /outputfile inventory, then Import inventory…');
    const hideDone = $('#hide-done').checked, onlyReady = $('#only-ready').checked;
    $('#classes').innerHTML = d.classes.filter(c => !(hideDone && c.unlocked)).map(c => {
      const qs = c.quests.filter(x => !onlyReady || x.ready);
      if (onlyReady && !qs.length) return '';
      const coll = collapsed.has(c.name) && !onlyReady;
      return `<div class="cls ${c.unlocked ? 'unlocked' : ''} ${coll ? 'collapsed' : ''}" data-cls="${esc(c.name)}">
        <div class="cls-h"><span class="nm">${esc(c.name)}<small>${esc(c.npc)}</small></span>
          ${c.unlocked ? '<span class="badge">UNLOCKED</span>' : ''}
          <span class="prog"><i style="width:${100 * c.done / c.total}%"></i></span><span class="cnt">${c.done}/${c.total}</span></div>
        <div class="cls-b">${qs.map(x => `
          <div class="q ${x.done ? 'done' : ''} ${x.ready ? 'ready' : ''}">
            <input type="checkbox" data-q="${esc(x.id)}" ${x.done ? 'checked' : ''} title="Mark turned in">
            <div class="t">${esc(x.name)} <span class="rw">→ ${esc(x.reward)}</span>
              ${x.ready ? '<span class="tag">READY TO TURN IN</span>' : ''}${x.how && x.how !== 'manual' ? `<span class="tag muted">(${{log: 'reward seen in log', history: 'reward found in older logs', inventory: 'reward in inventory'}[x.how] || x.how})</span>` : ''}</div>
            <div class="its">${x.items.map(i => `<span class="it ${i.held ? 'have' : ''}" title="${esc(i.source)}${i.where && i.where.length ? ' · you have it: ' + esc(i.where.join(', ')) : ''}">${esc(i.name)}${i.held > 1 ? ` <small>×${i.held}</small>` : ''}</span>`).join('')}</div>
          </div>`).join('')}
          <div class="cls-f"><span>Say “${esc(c.quests[0].trigger)}” etc. to ${esc(c.npc)}${c.wiki ? ` · <a href="${esc(c.wiki)}" target="_blank" rel="noopener">EQLWiki ↗</a>` : ''}</span>
            <label><input type="checkbox" data-unlock="${esc(c.name)}" ${c.manual_unlock ? 'checked' : ''}> unlocked via token</label></div>
        </div></div>`;
    }).join('');
    $$('.cls-h').forEach(h => h.onclick = () => {
      const n = h.parentElement.dataset.cls;
      collapsed.has(n) ? collapsed.delete(n) : collapsed.add(n);
      localStorageSet('eqlc-collapsed', JSON.stringify([...collapsed]));
      h.parentElement.classList.toggle('collapsed');
    });
    $$('[data-q]').forEach(b => b.onchange = async () => { await post('/api/sky/done', {char, id:b.dataset.q, done:b.checked}); refreshSky(); });
    $$('[data-unlock]').forEach(b => b.onchange = async () => { await post('/api/sky/unlock', {char, cls:b.dataset.unlock, unlocked:b.checked}); refreshSky(); });

    skyRunes = d.runes;
    $('#rune-info').textContent = d.currency_time
      ? `Wind Runes: from your Currency tab ${dt(d.currency_time)}, plus runes picked up since.`
      : 'Wind Runes are counted as you pick them up. Copy your Currency tab once for exact counts.';
    const shop = d.shopping.filter(s => skySrc === 'all' || (skySrc === 'rune') === s.name.startsWith('Wind Rune'));
    $('#shopping').innerHTML = shop.length ? shop.map(s => `
      <div class="need ${s.held >= s.need ? 'ok' : ''}" title="For: ${esc(s.for.join(', '))}">
        <span>${esc(s.name)}</span>
        <span class="c"><button class="adj" data-item="${esc(s.name)}" data-d="-1">−</button> ${s.held}/${s.need}
          <button class="adj" data-item="${esc(s.name)}" data-d="1">+</button></span>
        <span class="src">${esc(s.source)}</span></div>`).join('') : '<div class="muted">Nothing left — nice.</div>';
    $$('.adj').forEach(b => b.onclick = async () => { await post('/api/sky/adjust', {char, item:b.dataset.item, delta:+b.dataset.d}); refreshSky(); });

    $('#drops').innerHTML = d.drops.length ? d.drops.slice(0, 100).map(l => `
      <div class="drop"><span>${l.qty < 0 ? 'manual ' : ''}${esc(l.item)}${Math.abs(l.qty) > 1 || l.qty < 0 ? ` ×${l.qty}` : ''}</span>
        <span>${l.corpse && l.corpse !== 'manual' ? esc(l.corpse) + ' · ' : ''}${dt(l.t)}</span></div>`).join('')
      : '<div class="muted">No Plane of Sky items looted yet.</div>';
    $('#gdrops').innerHTML = d.group_drops.length ? d.group_drops.slice(0, 60).map(l => `
      <div class="drop"><span>${esc(l.who)}: ${esc(l.item)}</span><span>${dt(l.t)}</span></div>`).join('')
      : '<div class="muted">None seen.</div>';
  } finally { skyBusy = false; }
}

$('#rune-set').onclick = () => {
  openModal(`<h2>Wind Runes from your Currency tab</h2>
    <p class="muted">Wind Runes go to the <b>Currency</b> tab of your inventory window, so <code>/outputfile inventory</code> doesn't include them.
      Open that tab in game and copy each count here. From now on the app adds runes you pick up on top.</p>
    <div class="rune-grid">${skyRunes.map(r => `<label>${esc(r.name.replace('Wind Rune ', ''))}<input type="number" min="0" max="999" data-rune="${esc(r.name)}" value="${r.held}"></label>`).join('')}</div>
    <div class="modal-btns"><button class="ghost" onclick="closeModal()">Cancel</button><button class="primary" id="rune-save">Save counts</button></div>`);
  $('#rune-save').onclick = async () => {
    const counts = {};
    $$('[data-rune]').forEach(i => counts[i.dataset.rune] = Math.max(0, parseInt(i.value || '0', 10) || 0));
    await post('/api/sky/currency', {char, counts});
    closeModal(); refreshSky();
  };
};

// ---------- crawl log checks ----------
const PROOF_LABEL = {verified: '✓ Logged live', unverified: 'Not witnessed', suspicious: '⚠ Suspicious', pending: 'In progress'};
const proofBadge = p => !p ? '—' : `<span class="proof ${p.status}" title="${esc(p.reasons.join(' '))}">${PROOF_LABEL[p.status] || p.status}</span>`;
$('#proof-check').onclick = () => { $('#proof-file').value = ''; $('#proof-file').click(); };
$('#proof-file').onchange = async e => {
  const f = e.target.files[0];
  if (!f) return;
  const r = await post('/api/crawls/verify', {text: await f.text()});
  const v = r.verdict || {};
  openModal(`<h2>Proof check: ${esc(f.name)}</h2>
    ${r.char ? `<p><b>${esc(charLabel(r.char))}</b> · ${esc(r.zone || '')} ${esc(r.tier || '')} · ${r.duration != null ? hms(r.duration) : '—'} · ${r.lines || 0} log lines</p>` : ''}
    <div class="proof-box ${r.ok ? (v.status || 'unverified') : 'suspicious'}">
      <b>${r.ok ? 'File intact: the lines match the hash chain and the times.' : '⚠ This file has problems'}</b>
      <ul>${(r.problems || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
    ${v.status ? `<div class="proof-box ${v.status}" style="margin-top:10px"><b>What the player's app saw: ${PROOF_LABEL[v.status] || v.status}</b>
      <ul>${(v.reasons || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
    <p class="hint">A proof shows what the player's copy of EQL Assistant witnessed. The app is open source, so a determined
      cheater could fake one. Treat it as one piece of evidence next to video or screenshots.</p>
    <div class="modal-btns"><button class="primary" onclick="closeModal()">OK</button></div>`);
};

// ---------- fight deep dive ----------
const dp = {id: null, tab: 'overview', data: null, open: {}, f: {type: 'all', who: '', q: ''}, timer: null};
const pct = v => v == null ? '—' : `${v}%`;
const pbar = (v, cls = '') => v == null ? '—' : `<span class="pb ${cls}"><span class="tr"><i style="width:${Math.min(100, v)}%"></i></span><b>${v}%</b></span>`;
const OUTCOME_LABEL = {hit: 'Hit', miss: 'Miss', dodge: 'Dodge', parry: 'Parry', block: 'Block', riposte: 'Riposte',
  absorb: 'Absorb', invulnerable: 'Invulnerable'};
async function openDeep(id) {
  dp.id = id; dp.open = {}; dp.f = {type: 'all', who: '', q: ''};
  $('#deep').hidden = false; document.body.classList.add('noscroll');
  await loadDeep();
  clearInterval(dp.timer);
  dp.timer = setInterval(() => { if (dp.data && !dp.data.done && !$('#deep').hidden) loadDeep(); }, 3000);
}
function closeDeep() { $('#deep').hidden = true; document.body.classList.remove('noscroll'); clearInterval(dp.timer); }
$('#dp-close').onclick = closeDeep;
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('#deep').hidden && $('#modal').hidden) closeDeep(); });
$$('#dp-tabs button').forEach(b => b.onclick = () => { dp.tab = b.dataset.dp; $$('#dp-tabs button').forEach(x => x.classList.toggle('on', x === b)); renderDeep(); });
async function loadDeep() {
  const d = await get(`/api/fight/deep?id=${dp.id}&` + q());
  if (!d || !d.id) { $('#dp-body').innerHTML = '<div class="empty">That fight is no longer in the history.</div>'; return; }
  dp.data = d; renderDeep();
}
function deepTimeline(d) {
  const tl = d.timeline, n = tl.friend.length, W = 900, H = 70;
  const top = Math.max(1, ...tl.friend, ...tl.npc), bw = W / Math.max(n, 1);
  const bars = (arr, cls, off) => arr.map((v, i) => v ? `<rect class="${cls}" x="${i * bw + off}" y="${H - (H - 4) * v / top}" width="${Math.max(1, bw / 2 - 1)}" height="${(H - 4) * v / top}"><title>+${mmss(i * tl.step)}: ${num(v)}</title></rect>` : '').join('');
  return `<div class="dp-tl"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${bars(tl.friend, 'f', 0)}${bars(tl.npc, 'n', bw / 2)}</svg>
    <div class="dp-tl-k"><span><i class="f"></i>your side</span><span><i class="n"></i>NPCs</span><span class="muted">damage per ${tl.step}s</span></div></div>`;
}
function renderDeep() {
  const d = dp.data; if (!d) return;
  const c = d.counts, st = d.spell_totals;
  const swings = [...d.friends, ...d.npcs].reduce((a, r) => a + (r.melee ? r.melee.swings : 0), 0);
  const hits = [...d.friends, ...d.npcs].reduce((a, r) => a + (r.melee ? r.melee.hits : 0), 0);
  $('#dp-title').textContent = `${d.name} — deep dive`;
  $('#dp-sub').innerHTML = `${dt(d.start)} · ${mmss(d.duration)}${d.done ? '' : ' · <span class="badge">LIVE</span>'}${d.events_capped ? ' · very long fight: first 20,000 events' : ''}`;
  const stat = (label, val, sub = '') => `<div><label>${label}</label><b>${val}</b>${sub ? `<small>${sub}</small>` : ''}</div>`;
  $('#dp-stats').innerHTML = stat('Damage hits', num(c.hit || 0)) +
    stat('Melee swings', num(swings), swings ? `${pct(Math.round(1000 * hits / swings) / 10)} landed` : '') +
    stat('Misses &amp; avoids', num(c.avoid || 0)) +
    stat('Your casts', num(st.casts), st.casts ? `${pct(st.fizzle_pct)} fizzled · ${pct(st.interrupt_pct)} interrupted` : '') +
    stat('Your resists', num(st.resists), (st.landed + st.resists) ? `${pct(st.resist_pct)} of spells that reached a target` : '') +
    stat('You resisted', num(d.you_resisted.reduce((a, r) => a + r.count, 0))) +
    stat('Deaths', num(c.death || 0));
  const body = $('#dp-body');
  if (dp.tab === 'overview') body.innerHTML = deepTimeline(d) + deepWho(d.friends, 'Your side', 'friend') + deepWho(d.npcs, 'NPCs', 'npc');
  else if (dp.tab === 'melee') body.innerHTML = deepMelee(d);
  else if (dp.tab === 'spells') body.innerHTML = deepSpells(d);
  else if (dp.tab === 'defence') body.innerHTML = deepDefence(d);
  else body.innerHTML = deepLog(d);
  $$('#dp-body tr[data-dp-who]').forEach(tr => tr.onclick = () => { const k = tr.dataset.dpWho; dp.open[k] = !dp.open[k]; renderDeep(); });
  $$('#dp-body [data-dpf]').forEach(el => el.oninput = el.onchange = () => {
    dp.f[el.dataset.dpf] = el.value;
    const keep = el.dataset.dpf === 'q' ? el.selectionStart : null;
    renderDeep();
    if (keep != null) { const i = $('#dp-body [data-dpf=q]'); i.focus(); i.setSelectionRange(keep, keep); }
  });
}
function deepWho(rows, title, side) {
  if (!rows.length) return '';
  const tr = rows.map(r => {
    const k = side + ':' + r.name, open = dp.open[k];
    const m = r.melee;
    const detail = open ? `<tr class="dp-sub"><td colspan="11">
      <div class="dp-two">
        <div><h4>Damage by ability</h4><table><tr><th>Ability</th><th>Hits</th><th>Damage</th><th>Share</th><th>Avg</th><th>Min</th><th>Max</th><th>Crit %</th></tr>
          ${r.abilities.map(a => `<tr><td>${esc(a.name)}</td><td>${num(a.count)}</td><td>${num(a.dmg)}</td><td>${pbar(a.pct)}</td><td>${num(a.avg)}</td><td>${num(a.min || 0)}</td><td>${num(a.max)}</td><td>${pct(a.crit_pct)}</td></tr>`).join('') || '<tr><td colspan="8" class="muted">No damage.</td></tr>'}</table></div>
        <div><h4>Targets</h4><table><tr><th>Target</th><th>Damage</th><th>Share</th></tr>
          ${r.targets.map(t => `<tr><td>${esc(t.name)}</td><td>${num(t.dmg)}</td><td>${pbar(t.pct)}</td></tr>`).join('') || '<tr><td colspan="3" class="muted">—</td></tr>'}</table>
          ${m ? `<h4>Melee outcomes</h4><table><tr><th>Outcome</th><th>Count</th><th>%</th></tr>${m.outcomes.map(o => `<tr><td>${OUTCOME_LABEL[o.outcome] || o.outcome}</td><td>${num(o.count)}</td><td>${pbar(o.pct, o.outcome === 'hit' ? '' : 'bad')}</td></tr>`).join('')}</table>` : ''}
          ${r.avoided_total ? `<h4>Swings at ${esc(r.name)} that missed</h4><p class="muted">${r.avoided.map(a => `${OUTCOME_LABEL[a.outcome] || a.outcome} ${num(a.count)}`).join(' · ')}</p>` : ''}</div>
      </div></td></tr>` : '';
    return `<tr class="click ${r.name === 'You' ? 'you' : ''}" data-dp-who="${esc(k)}">
      <td><span class="caret">${open ? '▾' : '▸'}</span> ${esc(r.name)} ${side === 'friend' ? `<span class="tag-type ${r.type}">${TYPE_LABEL[r.type] || ''}</span>` : ''}</td>
      <td>${num(r.dmg)}</td><td>${pbar(r.share)}</td><td><b>${dps(r.dps)}</b></td><td>${num(r.hits)}</td><td>${num(r.avg)}</td><td>${num(r.max)}</td>
      <td>${pct(r.crit_pct)}</td><td>${m ? pbar(m.hit_pct) : '—'}</td><td>${m ? num(m.swings) : '—'}</td><td class="red">${r.taken ? num(r.taken) : '—'}</td></tr>${detail}`;
  }).join('');
  return `<h3>${title} <span class="muted">click a row for abilities, targets and misses</span></h3>
    <table class="dp-t"><tr><th>Name</th><th>Damage</th><th>Share</th><th>DPS</th><th>Hits</th><th>Avg</th><th>Max</th><th>Crit %</th><th>Melee hit %</th><th>Swings</th><th>Taken</th></tr>${tr}</table>`;
}
function deepMelee(d) {
  const cols = ['hit', 'miss', 'dodge', 'parry', 'block', 'riposte', 'absorb', 'invulnerable'];
  const tbl = (rows, title) => {
    rows = rows.filter(r => r.melee);
    if (!rows.length) return '';
    const used = cols.filter(o => rows.some(r => r.melee.outcomes.some(x => x.outcome === o)));
    return `<h3>${title}</h3><table class="dp-t"><tr><th>Attacker</th><th>Swings</th>${used.map(o => `<th>${OUTCOME_LABEL[o]}</th>`).join('')}<th>Melee dmg</th><th>Avg hit</th><th>Max</th><th>Crit %</th></tr>
      ${rows.map(r => { const m = r.melee, by = Object.fromEntries(m.outcomes.map(o => [o.outcome, o]));
        return `<tr class="${r.name === 'You' ? 'you' : ''}"><td>${esc(r.name)}</td><td>${num(m.swings)}</td>${used.map(o => `<td>${by[o] ? `${num(by[o].count)} <span class="muted">(${by[o].pct}%)</span>` : '—'}</td>`).join('')}
          <td>${num(m.dmg)}</td><td>${num(m.avg)}</td><td>${num(m.max)}</td><td>${pct(m.crit_pct)}</td></tr>`; }).join('')}</table>`;
  };
  return (tbl(d.friends, 'Your side swinging') + tbl(d.npcs, 'NPCs swinging')) || '<div class="empty">No melee in this fight.</div>';
}
function deepSpells(d) {
  const st = d.spell_totals;
  const rows = d.spells.map(s => `<tr><td>${esc(s.name)}</td><td>${num(s.casts)}</td><td>${num(s.landed)}</td><td>${num(s.ticks)}</td>
    <td>${num(s.resists)}</td><td>${pbar(s.resist_pct, 'bad')}</td><td>${num(s.fizzles)}</td><td>${pct(s.fizzle_pct)}</td>
    <td>${num(s.interrupts)}</td><td>${pct(s.interrupt_pct)}</td><td>${num(s.damage)}</td><td>${s.per_cast == null ? '—' : num(s.per_cast)}</td></tr>`).join('');
  const tot = `<tr class="tot"><td>All spells</td><td>${num(st.casts)}</td><td>${num(st.landed)}</td><td>${num(st.ticks)}</td><td>${num(st.resists)}</td>
    <td>${pbar(st.resist_pct, 'bad')}</td><td>${num(st.fizzles)}</td><td>${pct(st.fizzle_pct)}</td><td>${num(st.interrupts)}</td><td>${pct(st.interrupt_pct)}</td><td>${num(st.damage)}</td><td></td></tr>`;
  const others = d.friends.filter(r => r.name !== 'You' && r.abilities.some(a => a.kind !== 'melee'));
  return `<h3>Your spells</h3>
    ${d.spells.length ? `<table class="dp-t"><tr><th>Spell</th><th>Casts</th><th>Landed</th><th>DoT ticks</th><th>Resisted</th><th>Resist %</th><th>Fizzles</th><th>Fizzle %</th><th>Interrupts</th><th>Interrupt %</th><th>Damage</th><th>Dmg / cast</th></tr>${rows}${tot}</table>
      <p class="hint">Resist % is resists out of spells that reached a target (landed + resisted). Fizzle and interrupt % are out of casts.${st.immune || st.nohold ? ` Also: ${st.immune} immune, ${st.nohold} did not take hold.` : ''}</p>` : '<div class="muted">You didn\'t cast in this fight.</div>'}
    <div class="dp-two">
      <div><h4>Resisted by</h4>${d.resisted_by.length ? `<table><tr><th>NPC</th><th>Spell</th><th>Times</th></tr>${d.resisted_by.map(r => r.spells.map((s, i) => `<tr><td>${i ? '' : esc(r.npc)}</td><td>${esc(s.spell)}</td><td>${s.count}</td></tr>`).join('')).join('')}</table>` : '<p class="muted">Nothing resisted.</p>'}</div>
      <div><h4>Spells you resisted</h4>${d.you_resisted.length ? `<table><tr><th>Spell</th><th>Times</th></tr>${d.you_resisted.map(r => `<tr><td>${esc(r.spell)}</td><td>${r.count}</td></tr>`).join('')}</table>` : '<p class="muted">None.</p>'}</div>
    </div>
    ${others.length ? `<h3>Others' spell damage <span class="muted">(only landed hits show in your log)</span></h3><table class="dp-t"><tr><th>Who</th><th>Ability</th><th>Hits</th><th>Damage</th><th>Avg</th><th>Max</th></tr>
      ${others.map(r => r.abilities.filter(a => a.kind !== 'melee').map(a => `<tr><td>${esc(r.name)}</td><td>${esc(a.name)}</td><td>${num(a.count)}</td><td>${num(a.dmg)}</td><td>${num(a.avg)}</td><td>${num(a.max)}</td></tr>`).join('')).join('')}</table>` : ''}`;
}
function deepDefence(d) {
  if (!d.defence.length) return '<div class="empty">No NPC swings at your side in this fight.</div>';
  const cols = ['miss', 'dodge', 'parry', 'block', 'riposte', 'absorb', 'invulnerable'].filter(o => d.defence.some(r => r.outcomes.some(x => x.outcome === o)));
  return `<h3>NPC swings at your side</h3><table class="dp-t"><tr><th>Target</th><th>Swings</th><th>Hit</th><th>Hit %</th>${cols.map(o => `<th>${OUTCOME_LABEL[o]}</th>`).join('')}<th>Avoided %</th></tr>
    ${d.defence.map(r => { const by = Object.fromEntries(r.outcomes.map(o => [o.outcome, o]));
      return `<tr class="${r.name === 'You' ? 'you' : ''}"><td>${esc(r.name)}</td><td>${num(r.swings)}</td><td>${num(r.hits)}</td><td>${pbar(r.hit_pct, 'bad')}</td>
        ${cols.map(o => `<td>${by[o] ? `${num(by[o].count)} <span class="muted">(${by[o].pct}%)</span>` : '—'}</td>`).join('')}
        <td>${pct(r.hit_pct == null ? null : Math.round(10 * (100 - r.hit_pct)) / 10)}</td></tr>`; }).join('')}</table>`;
}
function deepLog(d) {
  const f = dp.f, ql = f.q.trim().toLowerCase();
  const who = [...new Set(d.events.flatMap(e => [e.src, e.tgt]).filter(Boolean))].sort();
  const keep = e => {
    if (f.type === 'hits' && e.type !== 'hit') return false;
    if (f.type === 'avoids' && e.type !== 'avoid') return false;
    if (f.type === 'spells' && e.type !== 'spell') return false;
    if (['cast', 'resist', 'fizzle', 'interrupt'].includes(f.type) && !(e.type === 'spell' && e.sub === f.type)) return false;
    if (f.type === 'crits' && !(e.type === 'hit' && e.crit)) return false;
    if (f.type === 'deaths' && e.type !== 'death') return false;
    if (f.who && e.src !== f.who && e.tgt !== f.who) return false;
    if (ql && ![e.src, e.tgt, e.spell, e.kind, e.outcome, e.sub].some(x => x && String(x).toLowerCase().includes(ql))) return false;
    return true;
  };
  const rows = d.events.filter(keep);
  const SUB = {cast: 'begins casting', resist: 'was resisted', fizzle: 'fizzled', interrupt: 'was interrupted', immune: 'target immune', nohold: 'did not take hold', 'you resisted': 'you resisted it'};
  const line = e => {
    if (e.type === 'hit') return `<tr class="${e.side} ${e.crit ? 'crit' : ''}"><td>+${mmss(e.t)}</td><td>${esc(e.src)}</td><td>${esc(e.tgt)}</td><td>${e.spell ? esc(e.spell) : esc(e.kind)}${e.crit ? ' · <b>crit</b>' : ''}</td><td class="amt">${num(e.amt)}</td></tr>`;
    if (e.type === 'avoid') return `<tr class="${e.side} avoid"><td>+${mmss(e.t)}</td><td>${esc(e.src)}</td><td>${esc(e.tgt)}</td><td>${OUTCOME_LABEL[e.outcome] || esc(e.outcome)}</td><td class="amt">—</td></tr>`;
    if (e.type === 'spell') return `<tr class="spell ${e.sub === 'resist' || e.sub === 'fizzle' || e.sub === 'interrupt' ? 'bad' : ''}"><td>+${mmss(e.t)}</td><td>${esc(e.src || '')}</td><td>${esc(e.tgt || '')}</td><td>${esc(e.spell || 'spell')} <span class="muted">${SUB[e.sub] || esc(e.sub)}</span></td><td class="amt"></td></tr>`;
    return `<tr class="death"><td>+${mmss(e.t)}</td><td>${esc(e.src || '')}</td><td>${esc(e.tgt)}</td><td>died</td><td class="amt"></td></tr>`;
  };
  const LIMIT = 3000;
  return `<div class="dp-filters">
      <select data-dpf="type">${[['all', 'Everything'], ['hits', 'Hits'], ['crits', 'Crits'], ['avoids', 'Misses & avoids'], ['spells', 'All spell messages'], ['cast', 'Casts'], ['resist', 'Resists'], ['fizzle', 'Fizzles'], ['interrupt', 'Interrupts'], ['deaths', 'Deaths']]
        .map(([v, l]) => `<option value="${v}" ${f.type === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <select data-dpf="who"><option value="">Anyone</option>${who.map(w => `<option ${f.who === w ? 'selected' : ''}>${esc(w)}</option>`).join('')}</select>
      <input data-dpf="q" placeholder="Search spell, name…" value="${esc(f.q)}">
      <span class="muted">${num(rows.length)} of ${num(d.events.length)} events${rows.length > LIMIT ? ` · showing the first ${LIMIT.toLocaleString()}` : ''}</span></div>
    <table class="dp-t dp-log"><tr><th>Time</th><th>From</th><th>To</th><th>What</th><th>Damage</th></tr>${rows.slice(0, LIMIT).map(line).join('') || '<tr><td colspan="5" class="muted">Nothing matches.</td></tr>'}</table>`;
}

// ---------- breakdown drawer ----------
const OUT_COLORS = {hit: '#5bd38a', miss: '#6b7079', dodge: '#6aa8ff', parry: '#b48cf2', block: '#4fc1b7',
  riposte: '#e5675e', absorb: '#7cc6e8', invulnerable: '#3a3f47'};
let bd = null;                     // {scope, fightScope, name, side}
let bdTimer = null;

function outcomeBar(counts, total, title) {
  if (!total) return '';
  const order = Object.keys(OUT_COLORS).filter(k => counts[k]);
  return `<h3>${title}</h3>
    <div class="obar">${order.map(k => `<i style="width:${100 * counts[k] / total}%;background:${OUT_COLORS[k]}" title="${k}: ${counts[k]}"></i>`).join('')}</div>
    <div class="olegend">${order.map(k => `<span style="--c:${OUT_COLORS[k]}">${k} <b>${counts[k]}</b> (${Math.round(100 * counts[k] / total)}%)</span>`).join('')}
      <span style="--c:transparent">of ${total} attempts</span></div>`;
}
function tile(label, val, sub = '') { return `<div class="tile"><label>${label}</label><b>${val}</b><small>${sub}</small></div>`; }
const pctv = v => v == null ? '—' : `${Math.round(v)}%`;

function renderBreakdown(b) {
  if (!b || !b.name) { $('#dr-body').innerHTML = '<div class="empty">No data for this yet.</div>'; return; }
  const npc = b.side === 'npc';
  $('#dr-name').innerHTML = `${esc(b.name)} <span class="tag-type ${npc ? 'player' : b.type}" style="${npc ? 'background:#e5675e22;color:#f3a69e' : ''}">${npc ? 'npc' : TYPE_LABEL[b.type]}</span>`;
  $('#dr-sub').textContent = `${b.scope_label} · ${b.fights} fight${b.fights === 1 ? '' : 's'} · ${mmss(b.duration)} of combat`;
  const m = b.melee, df = b.defense;
  const tiles = npc
    ? tile('Damage dealt', num(b.damage), `${dps(b.dps)} dps`) + tile('Damage taken', num(b.taken)) +
      tile('Its hit rate', pctv(m.accuracy), `${m.swings} swings`) + tile('Avoided yours', df.attempts ? pctv(100 - df.hit_pct) : '—', `${df.attempts} swings`) +
      tile('Max hit', num(b.max_hit)) + tile('Crit rate', pctv(b.crit_pct))
    : tile('DPS', dps(b.dps), `${num(b.damage)} dmg`) + tile('Accuracy', pctv(m.accuracy), `${m.swings} swings`) +
      tile('Crit rate', pctv(b.crit_pct), `${b.crits} crit${b.crits === 1 ? '' : 's'}`) + tile('Uptime', pctv(b.active_pct), 'time dealing damage') +
      tile('Max hit', num(b.max_hit)) + tile('Taken', num(b.taken), df.attempts ? `${pctv(df.hit_pct)} of hits landed` : '');
  const tips = `<h3>Suggestions</h3><div class="tips">${b.tips.map(t => `
    <div class="tipc ${t.level}"><span class="lvl">${t.level === 'warn' ? 'fix' : t.level}</span><b>${esc(t.title)}</b><span>${esc(t.detail)}</span></div>`).join('')}</div>`;
  const melee = npc ? outcomeBar(m.counts, m.swings, 'Its attacks on your side') + outcomeBar(df.counts, df.attempts, "Your side's attacks on it")
                    : outcomeBar(m.counts, m.swings, 'Your melee swings') + outcomeBar(df.counts, df.attempts, 'Attacks on you');
  let spells = '';
  if (!npc && b.spells.length) spells = `<h3>Spells</h3><table>
    <tr><th>Spell</th><th>Casts</th><th>Landed</th><th title="DoT ticks">Ticks</th><th>Resisted</th><th>Interrupted</th><th>Fizzled</th><th>Damage</th></tr>
    ${b.spells.map(s => `<tr><td>${esc(s.name)}</td><td>${s.casts || '—'}</td><td>${s.landed}</td><td>${s.ticks || '—'}</td>
      <td class="${s.resist_pct >= 15 ? 'red' : ''}">${s.resists}${s.resist_pct != null && s.resists ? ` (${Math.round(s.resist_pct)}%)` : ''}</td>
      <td>${s.interrupts}${s.interrupt_pct ? ` (${Math.round(s.interrupt_pct)}%)` : ''}</td>
      <td>${s.fizzles}${s.fizzle_pct ? ` (${Math.round(s.fizzle_pct)}%)` : ''}</td><td>${num(s.damage)}</td></tr>`).join('')}</table>`;
  const rb = Object.entries(b.resisted_by || {});
  const resists = rb.length ? `<h3>${npc ? 'Your spells it resisted' : 'Who resisted your spells'}</h3><table><tr><th>${npc ? 'Spell' : 'Mob'}</th><th>Resists</th></tr>
    ${npc ? Object.entries(rb[0][1]).map(([sp, n]) => `<tr><td>${esc(sp)}</td><td>${n}</td></tr>`).join('')
          : rb.map(([mob, d]) => `<tr><td>${esc(mob)}</td><td>${Object.entries(d).map(([sp, n]) => `${esc(sp)} ×${n}`).join(', ')}</td></tr>`).join('')}</table>` : '';
  const yr = Object.entries(b.you_resisted || {});
  const youRes = yr.length ? `<h3>Enemy spells you resisted</h3><table><tr><th>Spell</th><th>Times</th></tr>
    ${yr.map(([sp, n]) => `<tr><td>${esc(sp)}</td><td>${n}</td></tr>`).join('')}</table>` : '';
  const hitMost = npc && b.dealt_to.length ? `<h3>Who it hit</h3><table><tr><th>Target</th><th>Damage</th></tr>
    ${b.dealt_to.map(t => `<tr><td>${esc(t.name)}</td><td>${num(t.dmg)}</td></tr>`).join('')}</table>` : '';
  const note = b.type === 'you' ? '' : `<p class="note">The log only shows spell casts, resists, fizzles and interrupts for your own character, so spell numbers aren't available for ${npc ? 'NPCs' : 'other players'}.</p>`;
  $('#dr-body').innerHTML = `<div class="tiles">${tiles}</div>${tips}${melee}${spells}${resists}${youRes}${hitMost}${note}`;
}

async function loadBreakdown() {
  if (!bd) return;
  const scope = bd.scope === 'recent' ? 'recent' : bd.fightScope;
  const b = await get(`/api/breakdown?scope=${encodeURIComponent(scope)}&name=${encodeURIComponent(bd.name)}&side=${bd.side}&` + q());
  if (bd) renderBreakdown(b);
}
function openBreakdown(fightScope, name, side = 'friend') {
  bd = {scope: 'fight', fightScope: String(fightScope), name, side};
  $$('#dr-scope button').forEach(x => x.classList.toggle('on', x.dataset.scope === 'fight'));
  $('#drawer').hidden = $('#drawer-bg').hidden = false;
  $('#dr-body').innerHTML = '<div class="empty">Loading…</div>';
  loadBreakdown();
  clearInterval(bdTimer);
  bdTimer = setInterval(loadBreakdown, 2000);    // stays live during a fight
}
window.openBreakdown = openBreakdown;
function closeBreakdown() { bd = null; clearInterval(bdTimer); $('#drawer').hidden = $('#drawer-bg').hidden = true; }
$('#dr-close').onclick = closeBreakdown;
$('#drawer-bg').onclick = closeBreakdown;
document.addEventListener('keydown', e => { if (e.key === 'Escape' && bd) closeBreakdown(); });
$$('#dr-scope button').forEach(b => b.onclick = () => {
  if (!bd) return;
  bd.scope = b.dataset.scope;
  $$('#dr-scope button').forEach(x => x.classList.toggle('on', x === b));
  loadBreakdown();
});
$('#my-breakdown').onclick = () => openBreakdown('latest', 'You', 'friend');
// opened from the in-game overlay when running in a browser: #breakdown=scope:side:name
(function fromHash() {
  const m = location.hash.match(/^#breakdown=([^:]+):(friend|npc):(.+)$/);
  if (m) { openBreakdown(decodeURIComponent(m[1]), decodeURIComponent(m[3]), m[2]); history.replaceState(null, '', '/'); }
})();

// ---------- dungeon crawls ----------
let openRun = null;
const hms = s => {
  if (s == null) return '—';
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), ss = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
};
const lvlChip = r => `<span class="lvl-chip l${r.level ?? 0}">${esc(r.tier_label)}${r.mode ? ' · ' + esc(r.mode) : ''}</span>`;
const deltaHtml = d => d == null ? '' : d === 0 ? '<span class="delta ahead">best</span>'
  : `<span class="delta ${d < 0 ? 'ahead' : 'behind'}">${d < 0 ? '−' : '+'}${hms(Math.abs(d))}</span>`;
const partyChip = r => r.party === 'group'
  ? `<span class="party group" title="${esc((r.players || []).join(', ') || 'Group instance')}">Multiplayer${r.players && r.players.length ? ' · ' + (r.players.length + 1) : ''}</span>`
  : '<span class="party solo">Solo</span>';
const motesTxt = mt => Object.entries(mt || {}).map(([k, v]) => `${v} ${k === 'potential' ? 'plain' : k}`).join(', ') || '—';

function crawlNow(d) {
  const c = d.current, j = d.just_done;
  if (c) {
    const vs = c.pb != null ? c.duration - c.pb : null;
    return `<div class="panel-h"><span>${c.away_now ? 'Crawl paused — you are outside the instance' : 'Current run'}</span>
        <span class="btns" style="margin:0"><button class="ghost" id="crawl-stop" title="End this run now and keep its time">Stop timer</button>
        <button class="ghost" id="crawl-reset" title="Back to 0:00: the timer starts again on your next kill">Reset timer</button>
        <button class="ghost" id="crawl-discard" title="This is a normal instance, not a crawl">Not a crawl</button></span></div>
      <div><b>${esc(c.zone)}</b> ${lvlChip(c)} ${partyChip(c)}</div>
      <div class="crawl-live"><span class="big ${c.away_now ? 'away' : ''}">${hms(c.duration)}</span>
        ${c.pb != null ? `<span class="pbline">best <b>${hms(c.pb)}</b> ${deltaHtml(vs)}</span>` : '<span class="pbline">first timed run here</span>'}</div>
      <div class="crawl-stats">
        <div><label>Kills</label><b>${c.kills}</b></div><div><label>Deaths</label><b>${c.deaths}</b></div>
        <div><label>Motes</label><b>${c.motes}</b></div>
        <div><label>In combat</label><b>${c.combat != null ? hms(c.combat) : '—'}</b></div>
        <div><label>Downtime</label><b>${c.combat != null ? hms(Math.max(0, c.inside - c.combat)) : '—'}</b></div>
        <div><label>Outside</label><b>${hms(c.outside)}</b></div></div>
      <p class="hint">${c.waiting_kill ? `<code>${esc(c.raw || c.zone)}</code> became available at ${clock(c.offered)}${c.entered ? '' : ' (not entered yet)'}. The timer starts on your first kill in it` : `Timer started on the first kill at ${clock(c.start)}${c.start_known ? '' : ' (no “is now available” line seen, so this run won\'t count as a best)'}`}. It ends when the first item is looted from the Reward Chest.</p>`;
  }
  if (j) return `<div class="panel-h"><span>Crawl complete${j.new_pb ? ' — <span class="gold">new personal best!</span>' : ''}</span></div>
      <div><b>${esc(j.zone)}</b> ${lvlChip(j)} ${partyChip(j)}</div>
      <div class="crawl-live"><span class="big done">${hms(j.duration)}</span>
        ${j.pb != null ? `<span class="pbline">previous best <b>${hms(j.pb)}</b> ${deltaHtml(j.duration - j.pb)}</span>` : ''}</div>
      <div class="crawl-stats"><div><label>Kills</label><b>${j.kills}</b></div><div><label>Deaths</label><b>${j.deaths}</b></div>
        <div><label>Motes</label><b>${j.motes}</b></div></div>`;
  const w = d.where;
  return `<div class="panel-h"><span>Current run</span>${w && w.inst ? '<span class="btns" style="margin:0"><button class="ghost" id="crawl-reset" title="Start timing this instance: the timer starts on your next kill">Start timing here</button></span>' : ''}</div><div class="muted" style="padding:6px 0 4px">Not in a crawl.
      The timer is set up by “&lt;zone&gt; is now available to you.” and starts on your first kill in that zone${w ? ` (you're in ${esc(w.zone)})` : ''}.</div>`;
}

async function refreshCrawls() {
  const d = await get('/api/crawls?' + q());
  if (!d || !d.char) { $('#crawl-now').innerHTML = '<div class="empty">No character yet — set your Logs folder in Settings.</div>'; return; }
  $('#crawl-now').innerHTML = crawlNow(d);
  $('#crawl-stop')?.addEventListener('click', async () => {
    if (confirm('Stop the timer and save this run with its current time?')) { await post('/api/crawls/stop', {char}); refreshCrawls(); }
  });
  $('#crawl-reset')?.addEventListener('click', async () => {
    const r = await post('/api/crawls/reset', {char});
    if (r && r.ok === false) alert(r.error);
    refreshCrawls();
  });
  $('#crawl-discard')?.addEventListener('click', async () => {
    if (confirm('Stop timing this instance? Use this for normal (non-crawl) instances.')) { await post('/api/crawls/discard', {char}); refreshCrawls(); }
  });
  $('#crawl-bests').innerHTML = d.bests.length ? `<table><tr><th>Zone</th><th>Difficulty</th><th>Party</th><th>Runs</th><th>Best</th><th>Average</th><th>Last</th></tr>
    ${d.bests.map(b => `<tr><td>${esc(b.zone)}</td><td>${lvlChip(b)}</td><td>${partyChip(b)}</td><td>${b.runs}</td><td class="gold"><b>${hms(b.best)}</b></td>
      <td>${hms(b.avg)}</td><td>${hms(b.last)} ${deltaHtml(b.last - b.best || null)}</td></tr>`).join('')}</table>`
    : '<div class="muted">Complete a crawl to set your first time.</div>';
  // history
  const zsel = $('#crawl-zone'), zones = [...new Set(d.runs.map(r => r.zone))].sort();
  const zcur = zsel.value;
  if (zsel.options.length - 1 !== zones.length) {
    zsel.innerHTML = '<option value="">All zones</option>' + zones.map(z => `<option>${esc(z)}</option>`).join('');
    zsel.value = zcur;
  }
  const showAll = $('#crawl-unfinished').checked;
  const runs = d.runs.filter(r => (!zsel.value || r.zone === zsel.value) && (showAll || r.status !== 'left'));
  $('#crawl-runs').innerHTML = runs.length ? `<table>
    <tr><th>When</th><th>Zone</th><th>Difficulty</th><th>Party</th><th>Duration</th><th>vs best</th><th>Kills</th><th>Deaths</th><th>Motes</th><th>Motes/hr</th><th>Refund</th><th title="Did the app see this run being logged live by the game?">Log check</th></tr>
    ${runs.map(r => {
      const status = r.status === 'active' ? '<span class="badge">LIVE</span>' : r.status === 'left' ? '<span class="muted">not completed</span>' : '';
      const refund = r.refund === true ? '✓' : r.refund === false ? '<span class="red" title="Too easy for a recharge">✗</span>' : '—';
      const row = `<tr class="run click ${r.status === 'done' ? '' : 'notdone'}" data-run="${r.id}">
        <td>${dt(r.start)}</td><td>${esc(r.zone)} ${status}</td><td>${lvlChip(r)}</td><td>${partyChip(r)}</td>
        <td><span class="dur">${hms(r.duration)}</span>${r.is_best ? '<span class="pb">★ PB</span>' : ''}${r.start_known ? '' : ' <span class="muted" title="Logging started mid-crawl">(start unknown)</span>'}</td>
        <td>${deltaHtml(r.vs_best)}</td><td>${r.kills}</td><td>${r.deaths || '—'}</td><td>${r.motes || '—'}</td>
        <td>${r.motes_per_hour != null && r.motes ? dps(r.motes_per_hour) : '—'}</td><td>${refund}</td><td>${proofBadge(r.proof)}</td></tr>`;
      if (openRun !== r.id) return row;
      return row + `<tr class="rundetail"><td colspan="12"><div class="rd">
        <div class="wide proof-box ${r.proof.status}"><b>${PROOF_LABEL[r.proof.status] || r.proof.status}</b>
          <ul>${r.proof.reasons.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
          ${r.status !== 'active' ? `<button class="ghost" data-proof="${r.id}">Export proof file</button>` : ''}</div>
        <div><span>Instance:</span> ${esc(r.raw || '—')}</div>
        <div><span>Started:</span> ${dt(r.start)}${r.end ? ` · <span>ended</span> ${dt(r.end)}` : ''}</div>
        <div><span>Inside the instance:</span> ${hms(r.inside)}</div>
        <div><span>Ported out:</span> ${r.exits ? `${r.exits}× for ${hms(r.outside)}` : 'never'}</div>
        <div><span>Time to first kill:</span> ${hms(r.to_first_kill)}</div>
        <div><span>In combat:</span> ${r.combat != null ? `${hms(r.combat)} · downtime ${hms(Math.max(0, r.inside - r.combat))}` : 'not available (older than the loaded fight history)'}</div>
        <div><span>Motes:</span> ${motesTxt(r.motes_tiers)}</div>
        <div><span>Party:</span> ${r.party === 'group' ? `multiplayer${r.players.length ? ' with ' + r.players.map(esc).join(', ') : ''}` : 'solo'}${r.stopped ? ' · <span class="muted">timer stopped by hand</span>' : ''}</div>
        <div><span>Experience:</span> ${r.xp ? r.xp.toFixed(2) + '%' : '—'}${r.reward_xp ? ' (incl. crawl reward)' : ''}</div>
        <div class="wide"><span>Reward chest:</span> ${r.chest.length ? r.chest.map(c => `${esc(c.item)}${c.qty > 1 ? ' ×' + c.qty : ''}`).join(', ') : '—'}</div>
        ${r.notes.length ? `<div class="wide"><span>Messages:</span> ${r.notes.map(esc).join(' · ')}</div>` : ''}
        <div class="wide"><button class="ghost del" data-delrun="${r.id}">Delete this run</button></div></div></td></tr>`;
    }).join('')}</table>` : `<div class="muted" style="padding:8px 0">No ${showAll ? '' : 'completed '}crawls ${zsel.value ? 'in ' + esc(zsel.value) + ' ' : ''}yet.</div>`;
  $$('#crawl-runs tr.run').forEach(tr => tr.onclick = () => { openRun = openRun === +tr.dataset.run ? null : +tr.dataset.run; refreshCrawls(); });
  $$('[data-proof]').forEach(b => b.onclick = async e => {
    e.stopPropagation();
    const r = await post('/api/crawls/proof', {char, id: +b.dataset.proof});
    if (!r || !r.ok) { alert((r && r.error) || 'Could not export'); return; }
    const blob = URL.createObjectURL(new Blob([r.text], {type: 'application/json'}));
    openModal(`<h2>Proof file saved</h2>
      <p>${PROOF_LABEL[r.verdict.status]}: <b>${esc(r.name)}</b></p>
      <p class="muted">Saved in <code>${esc(r.folder)}</code>. Attach it to your leaderboard submission together with your video or screenshots.</p>
      <div class="modal-btns"><a class="btn ghost" href="${blob}" download="${esc(r.name)}">Download a copy</a>
        ${window.pywebview ? `<button class="ghost" id="proof-folder">Open folder</button>` : ''}<button class="primary" onclick="closeModal()">OK</button></div>`);
    const f = $('#proof-folder'); if (f) f.onclick = () => window.pywebview.api.open_folder(r.folder);
  });
  $$('[data-delrun]').forEach(b => b.onclick = async e => {
    e.stopPropagation();
    if (confirm('Delete this run from your history?')) { await post('/api/crawls/delete', {char, id: +b.dataset.delrun}); openRun = null; refreshCrawls(); }
  });
}
$('#crawl-zone').onchange = $('#crawl-unfinished').onchange = () => refreshCrawls();
$('#rescan-crawls').onclick = async () => {
  await post('/api/crawls/rescan', {});
  $('#rescan-status').textContent = 'Scanning…';
  const poll = setInterval(async () => {
    const d = await get('/api/crawls?' + q());
    if (d?.scan_status) $('#rescan-status').textContent = d.scan_status;
    if (d?.scan_status && !d.scan_status.startsWith('Scanning')) clearInterval(poll);
  }, 800);
};

// ---------- modal ----------
function openModal(html) { $('#modal-body').innerHTML = html; $('#modal').hidden = $('#modal-bg').hidden = false; }
function closeModal() { $('#modal').hidden = $('#modal-bg').hidden = true; $('#modal-body').innerHTML = ''; }
$('#modal-bg').onclick = closeModal;
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('#modal').hidden) closeModal(); });
const ago = t => { const s = Date.now() / 1000 - t; return s < 90 ? 'just now' : s < 5400 ? Math.round(s / 60) + ' min ago' : s < 129600 ? Math.round(s / 3600) + ' h ago' : Math.round(s / 86400) + ' days ago'; };
const dur = s => { s = Math.max(0, Math.round(s)); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`; };
const dayTime = t => new Date(t * 1000).toLocaleString([], {weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'});

// ---------- raids ----------
let raidWeek = 0;
async function refreshRaids() {
  const d = await get(`/api/raids?week=${raidWeek}&` + q());
  if (!d || !d.char) { $('#raid-groups').innerHTML = '<div class="empty">No character yet — set your Logs folder in Settings.</div>'; return; }
  const visible = d.groups.filter(g => g.note === '' || true);
  const done = visible.reduce((a, g) => a + g.done, 0), total = visible.reduce((a, g) => a + g.total, 0);
  $('#raid-title').textContent = raidWeek ? `Raid bosses ${raidWeek === 1 ? 'last week' : raidWeek + ' weeks ago'}` : 'Raid bosses this week';
  $('#raid-sub').innerHTML = `${dayTime(d.start)} → ${dayTime(d.end)} (your time) · <b>${done}</b> of ${total} killed` +
    (raidWeek ? '' : ` · next reset in <b>${dur(d.next_reset - d.now)}</b>`);
  $('#raid-eras').innerHTML = d.eras.map(e => `<label class="chk" style="display:inline;margin:0 8px 0 0"><input type="checkbox" data-era="${e}" ${d.shown_eras.includes(e) ? 'checked' : ''}> ${e}</label>`).join('');
  $$('[data-era]').forEach(c => c.onchange = async () => {
    await post('/api/raids/settings', {eras: $$('[data-era]').filter(x => x.checked).map(x => x.dataset.era)}); refreshRaids();
  });
  const now = Date.now() / 1000;
  $('#raid-groups').innerHTML = d.groups.map(g => `<div class="rg ${g.done === g.total ? 'alldone' : ''}">
    <div class="rg-h"><b>${esc(g.group)}</b><span class="era">${esc(g.era)}</span><span class="cnt">${g.done}/${g.total}</span></div>
    ${g.note ? `<div class="rg-note">${esc(g.note)}</div>` : ''}
    ${g.bosses.map(b => {
      const k = b.kills[b.kills.length - 1];
      const lv = b.levels.length ? ' · ' + b.levels.map(l => 'D' + l).join(', ') : '';
      const rep = b.repeat_at == null ? '' : b.repeat_at === 0 ? '<span class="rep ready">repeat ready</span>'
        : `<span class="rep wait" title="18-hour repeat for an extra loot piece">repeat in ${dur(b.repeat_at - now)}</span>`;
      const meta = k ? `${dayTime(k.t)}${k.killer ? ' · by ' + esc(k.killer) : ''}${lv}${b.kills.length > 1 ? ` · ${b.kills.length} kills` : ''}`
        : (b.last_ever ? `last killed ${ago(b.last_ever)}` : '');
      return `<div class="rb ${b.killed ? 'killed' : ''}"><span class="ck">${b.killed ? '✓' : '○'}</span>
        <span class="nm">${esc(b.boss)}${b.mini ? '<span class="mini">mini</span>' : ''}</span>${rep}
        ${meta ? `<span class="meta">${meta}</span>` : ''}</div>`;
    }).join('')}</div>`).join('');
  $('#raid-log').innerHTML = d.log.length ? `<table><tr><th>When</th><th style="text-align:left">Boss</th><th style="text-align:left">Killed by</th><th style="text-align:left">Zone</th><th></th></tr>
    ${d.log.map(k => `<tr><td style="text-align:left">${dayTime(k.t)}</td><td style="text-align:left">${esc(k.boss)}</td><td style="text-align:left">${esc(k.killer || '—')}</td>
      <td style="text-align:left">${esc(k.raw || k.zone || '—')}</td><td><button class="ghost" data-delkill="${k.t}" data-boss="${esc(k.boss)}" title="Remove">✕</button></td></tr>`).join('')}</table>`
    : '<div class="muted">No raid bosses killed in this window.</div>';
  $$('[data-delkill]').forEach(b => b.onclick = async () => {
    if (confirm(`Remove this ${b.dataset.boss} kill?`)) { await post('/api/raids/delete', {char, t: +b.dataset.delkill, boss: b.dataset.boss}); refreshRaids(); }
  });
  if (!raidWeek) { const rb = $('#raid-badge'); rb.hidden = !done; rb.textContent = done; }
  window._raidExtra = d.extra;
}
$$('#raid-week button').forEach(b => b.onclick = () => {
  raidWeek = +b.dataset.week; $$('#raid-week button').forEach(x => x.classList.toggle('on', x === b)); refreshRaids();
});
$('#raid-add').onclick = () => {
  openModal(`<h2>Your raid bosses</h2><p class="muted">Add any named mob you want counted each week, one per line. Use the exact in-game name.</p>
    <textarea id="m-extra" rows="8" style="width:100%;background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:8px;font:inherit">${esc((window._raidExtra || []).join('\n'))}</textarea>
    <div class="modal-btns"><button class="ghost" onclick="closeModal()">Cancel</button><button class="primary" id="m-save">Save</button></div>`);
  $('#m-save').onclick = async () => {
    await post('/api/raids/settings', {extra: $('#m-extra').value.split('\n').map(s => s.trim()).filter(Boolean)});
    closeModal(); refreshRaids();
  };
};
window.closeModal = closeModal;

// ---------- class quests ----------
let qData = null;
const qOpen = new Set(JSON.parse(localStorageGet('eqlc-qopen') || '[]'));
const HOW = {drop: 'drop', forage: 'forage', buy: 'buy', craft: 'combine', collect: 'pick up', quest: 'quest', turnin: 'hand-in'};
function questMatches(qq, term) {
  if (!term) return true;
  term = term.toLowerCase();
  return qq.name.toLowerCase().includes(term) || (qq.reward || '').toLowerCase().includes(term) ||
    (qq.giver || '').toLowerCase().includes(term) ||
    qq.items.some(i => i.n.toLowerCase().includes(term));
}
async function refreshQuests(force) {
  if (!force && document.activeElement && document.activeElement.closest && document.activeElement.closest('#q-list input[type=text]')) return;
  const d = await get('/api/quests?' + q());
  if (!d || !d.char) { $('#q-list').innerHTML = '<div class="empty">No character yet — set your Logs folder in Settings.</div>'; return; }
  qData = d;
  $('#q-classes').innerHTML = d.classes.map(c => `<button class="cc ${d.my_classes.includes(c) ? 'on' : ''}" data-cls="${esc(c)}">${esc(c)}</button>`).join('');
  $$('#q-classes .cc').forEach(b => b.onclick = async () => {
    const mine = new Set(qData.my_classes);
    mine.has(b.dataset.cls) ? mine.delete(b.dataset.cls) : mine.add(b.dataset.cls);
    await post('/api/quests/classes', {char, classes: [...mine]}); refreshQuests(true);
  });
  $('#q-cats').innerHTML = Object.entries(d.categories).map(([c, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(c)}</a>`).join(' · ');
  $('#q-inv').textContent = d.has_inventory ? 'Counts use your latest inventory export.' : 'Type /outputfile inventory in game for exact counts.';
  $('#q-invinfo').innerHTML = d.inventory ? `Using <b>${esc(d.inventory.source)}</b> from ${dt(d.inventory.t)}: ${d.inventory.items.toLocaleString()} items. Loot since then is added on top.` : 'No inventory export yet for this character.';
  renderQuests();
}
function renderQuests() {
  const d = qData; if (!d) return;
  const scope = $$('input[name=q-scope]').find(r => r.checked).value;
  const mine = new Set(d.my_classes);
  const term = $('#q-search').value.trim();
  const hide = $('#q-hide-done').checked;
  const hideK = $('#q-hide-kunark').checked;
  const kind = $('#q-kind').value;
  let list = d.quests.filter(x => (scope === 'all' || !mine.size || x.cls.some(c => mine.has(c) || c === 'Any')) &&
    questMatches(x, term) && !(hide && x.done) && !(hideK && x.banner) && (!kind || x.kind === kind));
  if (scope === 'mine' && !mine.size) list = [];
  if (!list.length) {
    $('#q-list').innerHTML = `<div class="panel"><div class="empty">${scope === 'mine' && !mine.size ? 'Pick your classes on the left (or choose “Show all classes”).' : 'No quests match.'}</div></div>`;
    return;
  }
  $('#q-list').innerHTML = list.map(x => {
    const open = qOpen.has(x.id) || !!term;
    let lastG = null;
    const items = x.items.map(i => {
      const head = i.g && i.g !== lastG ? `<div class="qg">${esc(i.g)}</div>` : '';
      lastG = i.g || lastG;
      const cnt = i.q > 1 || i.held ? `${Math.min(i.held, 999)}/${i.q}` : '';
      return head + `<div class="qi ${i.ok ? 'ok' : ''}">
        <input type="checkbox" data-qt="${esc(x.id)}" data-idx="${i.idx}" ${i.manual ? 'checked' : ''} title="${i.ok && !i.manual ? 'You hold this (from loot / inventory). Tick to mark it done regardless.' : 'Tick when you have it or have used it'}">
        <span class="n">${esc(i.n)}${i.how ? `<span class="how">${esc(HOW[i.how] || i.how)}</span>` : ''}${i.u ? '<span class="warn-u" title="Unverified on the wiki">⚠ unverified</span>' : ''}</span>
        <span class="cnt" title="${i.held ? 'You hold ' + i.held + (i.where && i.where.length ? ' (' + i.where.join(', ') + ')' : '') : (i.where && i.where.length ? 'In ' + i.where.join(', ') : '')}">${i.ok && !i.manual && i.held ? '✓ ' : ''}${cnt}</span>
        ${i.src ? `<span class="src">${esc(i.src)}</span>` : ''}</div>`;
    }).join('');
    return `<div class="qc ${x.done ? 'done' : ''} ${open ? '' : 'collapsed'}" data-q="${esc(x.id)}">
      <div class="qc-h"><span class="nm">${esc(x.name)}${x.reward ? ` <span class="rw">→ ${esc(x.reward)}</span>` : ''}</span>
        ${x.cls.map(c => `<span class="clsb">${esc(c)}</span>`).join('')}<span class="kindb">${esc(x.kind || '')}</span>
        ${x.banner ? `<span class="erab" title="${esc(x.banner)}">${esc(x.banner)}</span>` : ''}
        ${x.done ? '<span class="badge">DONE</span>' : ''}
        <span class="prog"><i style="width:${x.total ? 100 * x.got / x.total : 0}%"></i></span><span class="cnt">${x.got}/${x.total}</span></div>
      <div class="qc-b">
        ${x.banner ? `<div class="era-banner">⚠ ${esc(x.banner)}</div>` : ''}
        <div class="qmeta">${x.giver ? `<b>Start:</b> ${esc(x.giver)}<br>` : ''}${x.level ? `<b>Level:</b> ${esc(x.level)}<br>` : ''}${x.notes ? esc(x.notes) + '<br>' : ''}
          ${x.wiki ? `<a href="${esc(x.wiki)}" target="_blank" rel="noopener">Full walkthrough on eqlwiki.com ↗</a>` : ''}</div>
        ${items || '<div class="muted">No items listed yet.</div>'}
        <div class="qc-f"><label class="chk" style="margin:0"><input type="checkbox" data-qdone="${esc(x.id)}" ${x.done ? 'checked' : ''}> Quest completed</label>
          ${x.done_how === 'reward seen' ? '<span class="muted">(reward found in your items)</span>' : ''}
          ${x.custom ? `<button class="ghost" data-qedit="${esc(x.id)}">Edit</button><button class="ghost" data-qdel="${esc(x.id)}">Delete</button>` : ''}</div>
      </div></div>`;
  }).join('');
  $$('.qc-h').forEach(h => h.onclick = () => {
    const id = h.parentElement.dataset.q;
    qOpen.has(id) ? qOpen.delete(id) : qOpen.add(id);
    localStorageSet('eqlc-qopen', JSON.stringify([...qOpen]));
    h.parentElement.classList.toggle('collapsed');
  });
  $$('[data-qt]').forEach(c => c.onchange = async () => { await post('/api/quests/tick', {char, id: c.dataset.qt, idx: +c.dataset.idx, on: c.checked}); refreshQuests(true); });
  $$('[data-qdone]').forEach(c => c.onchange = async () => { await post('/api/quests/done', {char, id: c.dataset.qdone, on: c.checked}); refreshQuests(true); });
  $$('[data-qedit]').forEach(b => b.onclick = () => questEditor(qData.quests.find(x => x.id === b.dataset.qedit)));
  $$('[data-qdel]').forEach(b => b.onclick = async () => { if (confirm('Delete this quest?')) { await post('/api/quests/delete', {id: b.dataset.qdel}); refreshQuests(true); } });
}
$$('input[name=q-scope]').forEach(r => r.onchange = renderQuests);
$('#q-hide-done').onchange = renderQuests;
$('#q-hide-kunark').onchange = renderQuests;
$('#q-kind').onchange = renderQuests;
$('#q-search').oninput = renderQuests;

function itemRow(i = {}) {
  return `<tr><td><input data-f="n" value="${esc(i.n || '')}" placeholder="Exact item name"></td>
    <td style="width:60px"><input data-f="q" type="number" min="1" value="${i.q || 1}"></td>
    <td><input data-f="src" value="${esc(i.src || '')}" placeholder="Where it comes from"></td>
    <td style="width:120px"><select data-f="how">${Object.entries(HOW).map(([k, v]) => `<option value="${k}" ${i.how === k ? 'selected' : ''}>${v}</option>`).join('')}</select></td>
    <td style="width:120px"><input data-f="g" value="${esc(i.g || '')}" placeholder="Step (optional)"></td>
    <td style="width:30px"><button class="ghost" onclick="this.closest('tr').remove()">✕</button></td></tr>`;
}
function questEditor(x = {}) {
  const classes = qData ? qData.classes : [];
  openModal(`<h2>${x.id ? 'Edit quest' : 'Add a quest'}</h2>
    <div class="row2"><label class="f">Quest name<input id="m-name" value="${esc(x.name || '')}"></label>
      <label class="f">Reward<input id="m-reward" value="${esc(x.reward || '')}" placeholder="e.g. Spell: Tashania"></label></div>
    <label class="f">Classes</label><div class="chips" id="m-cls">${classes.map(c => `<button class="cc ${(x.cls || []).includes(c) ? 'on' : ''}" data-c="${esc(c)}" type="button">${esc(c)}</button>`).join('')}</div>
    <div class="row2"><label class="f">Starts with (NPC, zone)<input id="m-giver" value="${esc(x.giver || '')}"></label>
      <label class="f">Wiki link<input id="m-wiki" value="${esc(x.wiki || '')}" placeholder="https://eqlwiki.com/..."></label></div>
    <label class="f">Notes<input id="m-notes" value="${esc(x.notes || '')}"></label>
    <label class="f">Items to collect</label>
    <table><tbody id="m-items">${(x.items && x.items.length ? x.items : [{}]).map(itemRow).join('')}</tbody></table>
    <button class="ghost" id="m-additem" type="button">+ Item</button>
    <div class="modal-btns"><button class="ghost" onclick="closeModal()">Cancel</button><button class="primary" id="m-save">Save quest</button></div>`);
  $$('#m-cls .cc').forEach(b => b.onclick = () => b.classList.toggle('on'));
  $('#m-additem').onclick = () => $('#m-items').insertAdjacentHTML('beforeend', itemRow());
  $('#m-save').onclick = async () => {
    const items = $$('#m-items tr').map(tr => Object.fromEntries([...tr.querySelectorAll('[data-f]')].map(i => [i.dataset.f, i.value.trim()])))
      .filter(i => i.n).map(i => ({...i, q: +i.q || 1}));
    const quest = {id: x.custom ? x.id : undefined, name: $('#m-name').value, reward: $('#m-reward').value, giver: $('#m-giver').value,
      wiki: $('#m-wiki').value, notes: $('#m-notes').value, cls: $$('#m-cls .cc.on').map(b => b.dataset.c), items};
    if (!quest.name.trim()) { alert('Give the quest a name'); return; }
    const r = await post('/api/quests/save', {quest});
    closeModal();
    if (r.quest) { qOpen.add(r.quest.id); localStorageSet('eqlc-qopen', JSON.stringify([...qOpen])); }
    refreshQuests(true);
  };
}
$('#q-add').onclick = () => questEditor({});
$('#q-import').onclick = () => {
  openModal(`<h2>Import a quest from the EQL wiki</h2>
    <p class="muted">Paste a quest page link or title from eqlwiki.com, e.g. <code>https://eqlwiki.com/Tarton's_Wheel</code> or <code>Coin of Tash (Tashania)</code>.</p>
    <div class="start-row" style="grid-template-columns:1fr auto"><input id="m-page" placeholder="Wiki page link or title"><button class="primary" id="m-fetch">Fetch</button></div>
    <div id="m-result"></div>`);
  $('#m-page').focus();
  const go = async () => {
    const page = $('#m-page').value.trim(); if (!page) return;
    $('#m-result').innerHTML = '<p class="muted">Reading the wiki…</p>';
    const r = await post('/api/quests/import', {page});
    if (!r.ok) { $('#m-result').innerHTML = `<p class="red">${esc(r.error)}</p>`; return; }
    $('#m-result').innerHTML = `<h3>${esc(r.title)}</h3>
      <p class="muted">Found ${r.items.length} item${r.items.length === 1 ? '' : 's'} linked from that page. Untick anything you don't need to collect (the reward is usually in the list too).</p>
      <div>${r.items.map((i, n) => `<label class="chk" style="margin:4px 0"><input type="checkbox" data-imp="${n}" checked> ${esc(i.n)}${i.quest_item ? ' <span class="how">quest item</span>' : ''}</label>`).join('') || '<p class="muted">No item links found on that page. You can still add it by hand.</p>'}</div>
      <div class="modal-btns"><button class="ghost" onclick="closeModal()">Cancel</button><button class="primary" id="m-next">Next: review &amp; save</button></div>`;
    $('#m-next').onclick = () => {
      const items = r.items.filter((_, n) => $(`[data-imp="${n}"]`).checked).map(i => ({n: i.n, q: 1, src: '', how: 'drop'}));
      questEditor({name: r.title, wiki: r.url, cls: r.classes, items});
    };
  };
  $('#m-fetch').onclick = go;
  $('#m-page').onkeydown = e => { if (e.key === 'Enter') go(); };
};

// ---------- factions ----------
let fData = null, fOpen = null;
async function refreshFactions() {
  if (document.activeElement && document.activeElement.closest && document.activeElement.closest('#f-table input')) return;
  const d = await get('/api/factions?' + q());
  if (!d || !d.char) { $('#f-table').innerHTML = '<div class="empty">No character yet — set your Logs folder in Settings.</div>'; return; }
  fData = d; renderFactions();
}
const sgn = n => n > 0 ? `<span class="pos">+${n.toLocaleString()}</span>` : n < 0 ? `<span class="neg">${n.toLocaleString()}</span>` : '0';
const stand = t => t ? `<span class="stand st-${t.split(' ')[0]}">${esc(t)}</span>` : '<span class="muted">—</span>';
function renderFactions() {
  const d = fData; if (!d) return;
  const term = $('#f-search').value.trim().toLowerCase();
  const rows = d.factions.filter(f => !term || f.name.toLowerCase().includes(term));
  $('#f-table').innerHTML = rows.length ? `<table><tr><th>Faction</th><th title="Total change since tracking began">Net change</th><th>Last 24h</th><th>Hits</th>
      <th title="Your entered value plus changes since">Estimated value</th><th>Standing</th><th>Last change</th><th></th></tr>
    ${rows.map(f => {
      const row = `<tr class="click" data-fac="${esc(f.name)}"><td>${esc(f.name)}${f.maxed ? ` <span class="how">${f.maxed === 'better' ? 'maxed' : 'bottomed out'}</span>` : ''}</td>
        <td>${sgn(f.net)}</td><td>${sgn(f.today)}</td><td>${f.hits}</td>
        <td>${f.estimate != null ? f.estimate.toLocaleString() : '<span class="muted">—</span>'}</td><td>${stand(f.tier)}</td>
        <td>${ago(f.last)}</td><td><button class="ghost" data-fbase="${esc(f.name)}">Set</button></td></tr>`;
      if (fOpen !== f.name) return row;
      return row + `<tr class="fdetail"><td colspan="8"><div class="fd">
        <div><b>Recent changes</b>${f.events.map(e => `<div class="ev"><span>${dayTime(e.t)}${e.cause ? ' · ' + esc(e.cause) : ''}</span>
          <span>${e.amt != null ? sgn(e.amt) : `<span class="muted">can't get any ${e.cap}</span>`}</span></div>`).join('')}</div>
        <div><b>What moved it most</b>${f.causes.length ? f.causes.map(c => `<div class="ev"><span>killing ${esc(c.mob)} ×${c.hits}</span><span>${sgn(c.amt)}</span></div>`).join('')
          : '<div class="muted">Mostly quests or hand-ins (no kill right before the change).</div>'}
          <p class="hint">Gained ${sgn(f.ups)} · lost ${sgn(f.downs)} since ${dayTime(f.first)}.${f.base != null ? ` You set ${f.base.toLocaleString()} on ${dayTime(f.base_t)}.` : ''}</p></div></div></td></tr>`;
    }).join('')}</table>`
    : `<div class="empty">${term ? 'No factions match.' : 'No faction changes in your log yet.'}</div>`;
  $$('#f-table tr[data-fac]').forEach(tr => tr.onclick = e => {
    if (e.target.closest('button')) return;
    fOpen = fOpen === tr.dataset.fac ? null : tr.dataset.fac; renderFactions();
  });
  $$('[data-fbase]').forEach(b => b.onclick = async e => {
    e.stopPropagation();
    const f = fData.factions.find(x => x.name === b.dataset.fbase);
    const v = prompt(`Current value for ${f.name}?\n(e.g. from the in-game faction window; leave blank to clear)`, f.estimate ?? '');
    if (v === null) return;
    const r = await post('/api/factions/base', {char, name: f.name, value: v.trim()});
    if (!r.ok) alert(r.error); refreshFactions();
  });
  const ct = $('#c-search').value.trim().toLowerCase();
  const cons = d.cons.filter(c => !ct || c.npc.toLowerCase().includes(ct));
  $('#c-list').innerHTML = cons.length ? cons.map(c => `<div class="con"><span>${esc(c.npc)} <span class="muted">· ${ago(c.t)}</span></span>${stand(c.tier)}</div>`).join('')
    : '<div class="muted">Use /consider on NPCs and they show up here.</div>';
}
$('#f-search').oninput = renderFactions;
$('#c-search').oninput = renderFactions;

// ---------- respawn timers ----------
let rulesDirty = false;
function updateTimerBadge(active) {
  const n = active.filter(t => t.state !== 'up').length, b = $('#timer-badge');
  b.hidden = !n; b.textContent = n;
}
function cd(t) {
  const s = Math.max(0, t), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), ss = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}
function ruleRow(r = {}) {
  return `<tr><td><input data-k="mob" list="mob-names" value="${esc(r.mob || '')}" placeholder="e.g. Gorgalosk"></td>
    <td><input data-k="minutes" type="number" min="0" step="0.5" value="${r.minutes ?? ''}"></td>
    <td><input data-k="variance" type="number" min="0" step="0.5" value="${r.variance || ''}" placeholder="0"></td>
    <td><input data-k="zone" value="${esc(r.zone || '')}" placeholder="any zone"></td>
    <td><button class="ghost del" title="Remove">✕</button></td></tr>`;
}
function bindRules() {
  $$('#rules input').forEach(i => i.oninput = () => { rulesDirty = true; });
  $$('#rules .del').forEach(b => b.onclick = () => { b.closest('tr').remove(); rulesDirty = true; });
}
async function refreshTimers() {
  const d = await get('/api/timers');
  if (!d) return;
  updateTimerBadge(d.active);
  $('#active-timers').innerHTML = d.active.length ? d.active.map(t => {
    const total = Math.max(1, t.spawn_at - t.killed_at), done = Math.min(1, (Date.now() / 1000 - t.killed_at) / total);
    const cls = t.state === 'up' ? 'up' : t.state === 'window' ? 'window' : t.remaining <= 60 ? 'soon' : '';
    const big = t.state === 'up' ? 'UP' : t.state === 'window' ? cd(t.window_left) : cd(t.remaining);
    const meta = t.state === 'window' ? 'in spawn window now' : t.state === 'up' ? 'should be up' :
      `spawns ${clock(t.spawn_at)}${t.window_end > t.spawn_at ? '–' + clock(t.window_end) : ''}`;
    return `<div class="timer ${cls}"><span class="nm">${esc(t.mob)}</span><span class="cd">${big}</span>
      <button class="ghost x" data-id="${t.id}" title="Remove">✕</button>
      <span class="meta">${meta} · killed ${clock(t.killed_at)}${t.zone ? ' · ' + esc(t.zone) : ''}${t.manual ? ' · manual' : ''}</span>
      <span class="prog2"><i style="width:${100 * done}%"></i></span></div>`;
  }).join('') : '<div class="muted" style="padding:10px 0">No timers running.</div>';
  $$('#active-timers .x').forEach(b => b.onclick = async () => { await post('/api/timers/remove', {id: +b.dataset.id}); refreshTimers(); });
  if (!rulesDirty && document.activeElement?.closest('#rules') == null) {
    $('#rules').innerHTML = (d.rules.length ? d.rules : [{}]).map(ruleRow).join('');
    bindRules();
  }
  // suggestions from recent fights
  const f = await get('/api/fights?limit=60&' + q());
  const names = [...new Set((f?.fights || []).map(x => x.name.replace(/ \(\+\d+\)$/, '')))].slice(0, 24);
  $('#mob-names').innerHTML = names.map(n => `<option value="${esc(n)}">`).join('');
  const have = new Set(d.rules.map(r => r.mob.toLowerCase()));
  const chips = names.filter(n => !have.has(n.toLowerCase()));
  $('#recent-kills').innerHTML = chips.length ? chips.map(n => `<button class="chip" data-mob="${esc(n)}">+ ${esc(n)}</button>`).join('')
    : `<span class="muted">${names.length ? 'Everything you killed recently is already in the list.' : 'Kill something and it shows up here to add with one click.'}</span>`;
  $$('#recent-kills .chip').forEach(c => c.onclick = () => {
    const empty = [...$$('#rules tr')].find(tr => !tr.querySelector('[data-k=mob]').value);
    if (empty) empty.querySelector('[data-k=mob]').value = c.dataset.mob;
    else { $('#rules').insertAdjacentHTML('beforeend', ruleRow({mob: c.dataset.mob})); }
    bindRules(); rulesDirty = true;
    const row = [...$$('#rules tr')].find(tr => tr.querySelector('[data-k=mob]').value === c.dataset.mob);
    row?.querySelector('[data-k=minutes]').focus();
  });
}
$('#add-rule').onclick = () => { $('#rules').insertAdjacentHTML('beforeend', ruleRow()); bindRules(); rulesDirty = true; };
$('#save-rules').onclick = async () => {
  const rules = [...$$('#rules tr')].map(tr => Object.fromEntries([...tr.querySelectorAll('[data-k]')].map(i => [i.dataset.k, i.value.trim()])))
    .filter(r => r.mob && +r.minutes > 0);
  const missing = [...$$('#rules tr')].some(tr => tr.querySelector('[data-k=mob]').value.trim() && !(+tr.querySelector('[data-k=minutes]').value > 0));
  await post('/api/timers/rules', {rules});
  rulesDirty = false;
  $('#rules-saved').textContent = missing ? 'Saved — rows without minutes were skipped' : 'Saved ✓';
  setTimeout(() => $('#rules-saved').textContent = '', 3000);
  refreshTimers();
};
$('#t-start').onclick = async () => {
  const mob = $('#t-mob').value.trim(), mins = $('#t-min').value;
  if (!mob) return;
  const r = await post('/api/timers/start', {mob, minutes: mins ? +mins : null});
  if (r.ok) { $('#t-mob').value = ''; $('#t-min').value = ''; refreshTimers(); }
  else alert(r.error || 'Could not start that timer');
};
$('#clear-timers').onclick = async () => { if (confirm('Remove all running timers?')) { await post('/api/timers/remove', {}); refreshTimers(); } };

// ---------- races ----------
let raceData = null;
async function refreshRaces(force) {
  const d = await get('/api/races?' + q());
  if (!d) return;
  const sig = JSON.stringify(d);
  if (!force && sig === refreshRaces.sig) return;
  refreshRaces.sig = sig; raceData = d;
  $('#race-sum').textContent = `· ${d.unlocked}/${d.total} unlocked`;
  $('#race-guide').href = d.guide;
  renderRaces();
}
function renderRaces() {
  const d = raceData; if (!d) return;
  const hide = $('#race-hide').checked;
  const reqHtml = r => {
    const st = r.done ? `<span class="ok">✓ maxed${r.maxed_by.length ? ' by ' + esc(r.maxed_by.join(', ')) : ''}</span>`
      : r.tier ? `<span>${esc(r.tier)}${r.estimate != null ? ` (~${r.estimate})` : ''}</span>`
      : r.seen ? `<span class="muted">${r.net > 0 ? '+' : ''}${r.net ?? 0} from your logs</span>`
      : '<span class="muted">no changes seen yet</span>';
    return `<div class="rq ${r.done ? 'done' : ''}"><span class="f">${esc(r.faction)}</span>${st}</div>`;
  };
  $('#race-cards').innerHTML = d.races.filter(r => !(hide && r.unlocked)).map(r => {
    const [a, b] = r.progress;
    let body = '';
    if (r.groups.length) body = r.groups.map(g => `${g.label ? `<div class="race-grp">${esc(g.label)} <span class="muted">${g.done}/${g.total}</span></div>` : ''}${g.reqs.map(reqHtml).join('')}`).join('');
    if (r.steps) body = `<div class="race-grp"><a href="${esc(r.task.wiki)}" target="_blank" rel="noopener">${esc(r.task.name)} ↗</a> <span class="muted">${a}/${b}</span></div>
      <p class="hint" style="margin:2px 0 6px">${esc(r.task.start)}. ${esc(r.task.note)}</p>` +
      r.steps.map(s => `<label class="rs ${s.done ? 'done' : ''}"><input type="checkbox" data-rstep="${esc(s.name)}" ${s.done ? 'checked' : ''}><span><b>${esc(s.name)}</b> <span class="muted">${esc(s.info)}</span></span></label>`).join('');
    if (r.needs_race) body = `<div class="rq ${r.unlocked ? 'done' : ''}"><span class="f">Unlock ${r.needs_race.map(esc).join(' or ')}</span>${r.unlocked ? '<span class="ok">✓</span>' : ''}</div>`;
    return `<div class="panel race ${r.unlocked ? 'unl' : ''}">
      <div class="race-h"><a class="rn" href="${esc(r.wiki)}" target="_blank" rel="noopener">${esc(r.name)}</a>
        ${r.unlocked ? `<span class="badge">UNLOCKED</span>` : `<span class="prog"><i style="width:${b ? 100 * a / b : 0}%"></i></span><span class="cnt">${a}/${b}</span>`}</div>
      <div class="race-meta"><span class="city">${esc(r.city)}</span></div>
      ${body}
      ${r.tip ? `<p class="hint race-tip">${esc(r.tip)}</p>` : ''}
      <div class="race-f"><label class="chk" style="margin:0"><input type="checkbox" data-runl="${esc(r.name)}" ${r.how === 'manual' ? 'checked' : ''}> Unlocked <span class="muted">(started as it / token)</span></label>
        ${r.unlocked && r.how !== 'manual' ? `<span class="muted">${esc(r.how)}</span>` : ''}</div>
    </div>`;
  }).join('') || '<div class="panel"><div class="empty">Every race is unlocked.</div></div>';
  $$('[data-runl]').forEach(c => c.onchange = async () => { await post('/api/races/unlock', {race: c.dataset.runl, on: c.checked}); refreshRaces(true); });
  $$('[data-rstep]').forEach(c => c.onchange = async () => { await post('/api/races/step', {step: c.dataset.rstep, on: c.checked}); refreshRaces(true); });
}
$('#race-hide').onchange = renderRaces;

// ---------- inventory import ----------
let invChar = null;
$$('[data-inv-import]').forEach(b => b.onclick = () => { invChar = char; $('#inv-file').value = ''; $('#inv-file').click(); });
$('#inv-file').onchange = async e => {
  const f = e.target.files[0];
  if (!f) return;
  const text = await f.text();
  const r = await post('/api/inventory/import', {text, filename: f.name, char: invChar, mtime: f.lastModified});
  if (!r || !r.ok) { alert((r && r.error) || 'Could not read that file'); return; }
  const n = (r.sky_ticked || []).length;
  alert(`Imported ${r.items.toLocaleString()} items for ${charLabel(r.char)}.` + (n ? `\n${n} Plane of Sky test${n === 1 ? '' : 's'} ticked from rewards you own.` : ''));
  if (tab === 'sky') refreshSky(); else refreshQuests(true);
};

// ---------- overlays ----------
const OV_INFO = {
  dps: {name: 'DPS overlay', desc: 'Current fight DPS, last-10 average, a mini chart, the dungeon crawl timer and respawn timers. Double-click it for your fight breakdown.'},
  motes: {name: 'Motes window', desc: 'Motes looted since the app was opened, split by tier, with per-hour rates.'},
  crawl: {name: 'Dungeon crawl timer', desc: 'Live crawl time from “… is now available to you” to the Reward Chest, against your best for that zone and difficulty, with kills, deaths and motes.'},
};
let ovBusy = 0;
async function refreshOverlays(force) {
  if (!force && (ovBusy || document.activeElement?.closest?.('#ov-cards input[type=range]'))) return;
  const d = await get('/api/overlays');
  if (!d) return;
  const sig = JSON.stringify(d);
  if (!force && sig === refreshOverlays.sig) return;
  refreshOverlays.sig = sig;
  $('#ov-cards').innerHTML = d.overlays.map(o => {
    const info = OV_INFO[o.kind] || {name: o.kind, desc: ''};
    const extra = o.kind === 'dps' ? `
        <label class="chk"><input type="checkbox" data-ovopt="crawl_on_overlay" ${d.crawl_on_overlay ? 'checked' : ''}> Also show the crawl timer on this overlay</label>
        <label class="chk"><input type="checkbox" data-ovopt="timers_on_overlay" ${d.timers_on_overlay ? 'checked' : ''}> Show respawn timers</label>` : '';
    return `<div class="panel ov-card ${o.on ? '' : 'off'}" data-kind="${o.kind}">
      <div class="ov-h"><span class="ov-name">${info.name}</span>
        <span class="ov-state ${o.running ? 'run' : ''}">${o.running ? '● showing' : o.on ? 'on — not showing' : 'off'}</span>
        <label class="switch" title="Turn this overlay on or off"><input type="checkbox" data-ovon ${o.on ? 'checked' : ''}><i></i></label></div>
      <p class="muted">${info.desc}</p>
      <div class="ov-row"><span>Size</span><input type="range" min="60" max="250" step="5" value="${Math.round(o.scale * 100)}" data-ovset="scale"><b>${Math.round(o.scale * 100)}%</b></div>
      <div class="ov-row"><span>Opacity</span><input type="range" min="20" max="100" step="5" value="${Math.round(o.alpha * 100)}" data-ovset="alpha"><b>${Math.round(o.alpha * 100)}%</b></div>
      <label class="chk"><input type="checkbox" data-ovlock ${o.locked ? 'checked' : ''}> Lock position and size</label>${extra}
      <div class="btns">${o.on && !o.running ? '<button class="primary" data-ovshow>Show it now</button>' : ''}<button class="ghost" data-ovreset>Reset size and position</button></div>
    </div>`;
  }).join('');
  const kindOf = el => el.closest('.ov-card').dataset.kind;
  const set = async (el, body) => { ovBusy++; try { await post('/api/overlays/set', Object.assign({kind: kindOf(el)}, body)); } finally { ovBusy--; } };
  $$('[data-ovon]').forEach(c => c.onchange = async () => { await set(c, {on: c.checked}); setTimeout(() => refreshOverlays(true), 800); });
  $$('[data-ovset]').forEach(r => {
    r.oninput = () => { r.nextElementSibling.textContent = r.value + '%'; };
    r.onchange = async () => { await set(r, {[r.dataset.ovset]: r.value / 100}); refreshOverlays(true); };
  });
  $$('[data-ovlock]').forEach(c => c.onchange = async () => { await set(c, {locked: c.checked}); });
  $$('[data-ovopt]').forEach(c => c.onchange = async () => { await set(c, {[c.dataset.ovopt]: c.checked}); });
  $$('[data-ovshow]').forEach(b => b.onclick = async () => { await set(b, {on: true}); setTimeout(() => refreshOverlays(true), 800); });
  $$('[data-ovreset]').forEach(b => b.onclick = async () => { await set(b, {reset: true}); refreshOverlays(true); });
}
$$('[data-goto]').forEach(b => b.onclick = () => document.querySelector(`nav button[data-tab="${b.dataset.goto}"]`).click());

// ---------- settings ----------
const FIELDS = ['log_dir', 'character', 'fight_timeout', 'min_fight_secs', 'avg_fights', 'backfill_mb', 'include_pets', 'pet_names'];
let settingsLoaded = false;
async function refreshSettings(force) {
  const d = await get('/api/settings');
  if (!d) return;
  $('#status-dot').classList.toggle('ok', d.status === 'ok');
  $('#status-dot').title = d.status;
  fillChars(d.characters, d.active);
  if (tab !== 'settings' || (settingsLoaded && !force)) return;
  settingsLoaded = true;
  $('#set-status').textContent = d.status === 'ok' ? `Reading logs. Active character: ${charLabel(d.active)}` : d.status;
  $('#s-character').innerHTML = '<option value="">Follow active log</option>' + d.characters.map(c => `<option value="${esc(c)}">${esc(charLabel(c))}</option>`).join('');
  for (const k of FIELDS) {
    const el = $('#s-' + k), v = d.cfg[k];
    if (el.type === 'checkbox') el.checked = !!v;
    else el.value = Array.isArray(v) ? v.join(', ') : v;
  }
  $('#data-dir').innerHTML = `EQL Assistant ${esc(d.version || '')} · Saved data: <code>${esc(d.data_dir)}</code>`;
}
$('#save').onclick = async () => {
  const body = {};
  for (const k of FIELDS) {
    const el = $('#s-' + k);
    body[k] = el.type === 'checkbox' ? el.checked : el.type === 'number' ? +el.value
      : k === 'pet_names' ? el.value.split(',').map(s => s.trim()).filter(Boolean) : el.value.trim();
  }
  await post('/api/settings', body);
  $('#saved').textContent = 'Saved ✓'; setTimeout(() => $('#saved').textContent = '', 2000);
  settingsLoaded = false; refreshSettings(true);
};

// ---------- native app window extras ----------
function onNative() {
  document.body.classList.add('native');
  $('#browse').hidden = false;
}
if (window.pywebview && window.pywebview.api) onNative();
window.addEventListener('pywebviewready', onNative);
$('#browse').onclick = async () => {
  const p = await window.pywebview.api.pick_folder($('#s-log_dir').value);
  if (p) { $('#s-log_dir').value = p; $('#save').click(); }
};
$('#quit').onclick = async () => {
  if (!confirm('Quit EQL Assistant? The overlay will close too.')) return;
  try { await post('/api/quit', {}); } catch (e) {}
  document.body.innerHTML = '<div class="empty" style="padding-top:20vh">EQL Assistant has been closed. You can close this window.</div>';
};

// ---------- loop ----------
let n = 0;
async function refresh() {
  try {
    if (tab === 'parser') await refreshParser();
    if (tab === 'timers') await refreshTimers();
    if (tab === 'overlays') await refreshOverlays();
    if (tab === 'crawls') await refreshCrawls();
    if (tab === 'raids' && (n % 2 === 0 || !$('#raid-groups').innerHTML)) await refreshRaids();
    if (tab === 'quests' && (n % 5 === 0 || !$('#q-list').innerHTML)) await refreshQuests();
    if (tab === 'factions' && (n % 3 === 0 || !$('#f-table').innerHTML)) await refreshFactions();
    if (tab === 'races' && (n % 3 === 0 || !$('#race-cards').innerHTML)) await refreshRaces();
    if (tab === 'sky' && (n % 4 === 0 || !$('#classes').innerHTML)) await refreshSky();
    if (n % 4 === 0 || tab === 'settings') await refreshSettings();
  } catch (e) { $('#status-dot').classList.remove('ok'); $('#status-dot').title = 'app not reachable'; }
}
refresh();
setInterval(() => { n++; refresh(); }, 1000);
