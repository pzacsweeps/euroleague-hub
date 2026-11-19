(() => {
  const $ = s => document.querySelector(s);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const POS = { G: 'Guard', F: 'Forward', C: 'Center' };
  const STATS4 = [['pts', 'PTS'], ['reb', 'REB'], ['ast', 'AST'], ['fg3m', '3PM']];

  let D, T, L, F;   // data, teams, log rows (objects), log field index
  let INJ = null, INJP = {};   // injury report, injury entry by player id
  const state = { round: null, team: '', mHome: '', mAway: '', sort: { k: 'round', dir: -1 } };

  // ---------- helpers ----------
  const crest = (code, cls = 'crest') => T[code]?.crest ? `<img class="${cls}" src="${esc(T[code].crest)}" alt="" loading="lazy">` : '';
  const short = c => T[c]?.short || c;
  const rec = c => T[c] ? `${T[c].w}-${T[c].l}` : '';
  const fmtDay = d => d.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' });
  const fmtTime = d => d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  const rankCls = r => !r ? '' : r <= 6 ? 'soft' : r >= 15 ? 'tough' : '';
  const n1 = v => v == null ? '–' : (+v).toFixed(1);

  function nextRound() {
    const up = D.games.filter(g => !g.played).sort((a, b) => (a.utc || '').localeCompare(b.utc || ''))[0];
    return up ? up.round : D.lastRound;
  }

  // ---------- tabs ----------
  function showTab(name) {
    document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === name));
    document.querySelectorAll('.panel').forEach(p => p.classList.toggle('on', p.id === 'tab-' + name));
    try { history.replaceState(null, '', '#' + name); } catch (e) {}
    window.scrollTo({ top: 0 });
  }
  document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => showTab(b.dataset.tab));

  // ---------- SCHEDULE ----------
  function initSchedule() {
    const sel = $('#roundSel');
    sel.innerHTML = D.rounds.map(r => `<option value="${r}">Round ${r}${r === D.lastRound ? ' · latest' : ''}</option>`).join('');
    state.round = nextRound();
    sel.value = state.round;
    sel.onchange = () => { state.round = +sel.value; state.team = ''; renderSchedule(); };
    $('#rPrev').onclick = () => step(-1);
    $('#rNext').onclick = () => step(1);
    const chips = $('#teamChips');
    const codes = Object.keys(T).sort((a, b) => short(a).localeCompare(short(b)));
    chips.innerHTML = `<button class="chip all on" data-t="">All teams</button>` +
      codes.map(c => `<button class="chip" data-t="${c}">${crest(c)}${esc(short(c))}</button>`).join('');
    chips.onclick = e => {
      const b = e.target.closest('.chip'); if (!b) return;
      state.team = b.dataset.t;
      chips.querySelectorAll('.chip').forEach(x => x.classList.toggle('on', x === b));
      renderSchedule();
    };
    renderSchedule();
  }
  function step(d) {
    const i = D.rounds.indexOf(state.round) + d;
    if (i < 0 || i >= D.rounds.length) return;
    state.round = D.rounds[i]; $('#roundSel').value = state.round; renderSchedule();
  }

  function gameCard(g, forTeam) {
    const d = g.utc ? new Date(g.utc) : null;
    const hw = g.played && g.hs > g.as, aw = g.played && g.as > g.hs;
    let tag = g.played ? '<span class="tag final">Final</span>' : '';
    if (forTeam && g.played) {
      const won = (forTeam === g.home && hw) || (forTeam === g.away && aw);
      tag = `<span class="tag ${won ? 'w' : 'l'}">${won ? 'W' : 'L'}</span>`;
    }
    const c = el('div', 'game');
    c.innerHTML = `
      <div class="tm ${g.played && !hw ? 'lose' : ''}">${crest(g.home)}<span class="nm">${esc(short(g.home))}</span><span class="rec">${rec(g.home)}</span></div>
      <div class="sc ${hw ? 'win' : ''}">${g.played ? g.hs : ''}</div>
      <div class="tm ${g.played && !aw ? 'lose' : ''}">${crest(g.away)}<span class="nm">${esc(short(g.away))}</span><span class="rec">${rec(g.away)}</span></div>
      <div class="sc ${aw ? 'win' : ''}">${g.played ? g.as : ''}</div>
      <div class="gmeta"><span class="when">${forTeam ? 'R' + g.round + ' · ' : ''}${d ? (forTeam ? d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) + ' · ' : '') + fmtTime(d) : 'TBC'}</span><span>${tag || esc(g.venue || '')}</span></div>`;
    c.onclick = () => { setMatchup(g.home, g.away, g.code); showTab('matchup'); };
    return c;
  }

  function renderSchedule() {
    const list = $('#schedList'); list.innerHTML = '';
    const nav = document.querySelector('.round-nav');
    if (state.team) {
      nav.style.visibility = 'hidden';
      const gs = D.games.filter(g => g.home === state.team || g.away === state.team);
      const t = T[state.team];
      $('#schedHint').textContent = `${t.name} · ${t.w}-${t.l} · full season`;
      let lastR = null;
      gs.forEach(g => {
        if (!g.played && lastR !== 'up') { list.append(el('div', 'day', 'Upcoming')); lastR = 'up'; }
        else if (g.played && lastR === null) { list.append(el('div', 'day', 'Played')); lastR = 'played'; }
        list.append(gameCard(g, state.team));
      });
      return;
    }
    nav.style.visibility = '';
    const gs = D.games.filter(g => g.round === state.round).sort((a, b) => (a.utc || '').localeCompare(b.utc || ''));
    const played = gs.filter(g => g.played).length;
    $('#schedHint').textContent = `${gs.length} games · ${played === gs.length ? 'all played' : played ? played + ' played' : 'upcoming'}`;
    let day = '';
    gs.forEach(g => {
      const d = g.utc ? fmtDay(new Date(g.utc)) : 'Date TBC';
      if (d !== day) { list.append(el('div', 'day', d)); day = d; }
      list.append(gameCard(g));
    });
    if (!gs.length) list.append(el('div', 'empty', 'No games in this round.'));
  }

  // ---------- MATCHUP ----------
  function initMatchup() {
    const codes = Object.keys(T).sort((a, b) => short(a).localeCompare(short(b)));
    const opts = codes.map(c => `<option value="${c}">${esc(short(c))}</option>`).join('');
    $('#mHome').innerHTML = opts; $('#mAway').innerHTML = opts;
    const nr = nextRound();
    const pick = D.games.filter(g => g.round === nr || g.round === nr + 1 || g.round === D.lastRound);
    const byR = {};
    pick.forEach(g => (byR[g.round] ||= []).push(g));
    $('#mGame').innerHTML = Object.keys(byR).sort((a, b) => b - a).map(r =>
      `<optgroup label="Round ${r}">` + byR[r].sort((a, b) => (a.utc || '').localeCompare(b.utc || '')).map(g =>
        `<option value="${g.code}">${esc(short(g.home))} vs ${esc(short(g.away))}${g.played ? ` (${g.hs}-${g.as})` : ''}</option>`).join('') + '</optgroup>').join('') +
      '<option value="">Custom matchup</option>';
    $('#mGame').onchange = e => { const g = D.games.find(x => x.code == e.target.value); if (g) setMatchup(g.home, g.away, g.code); };
    $('#mHome').onchange = () => setMatchup($('#mHome').value, $('#mAway').value);
    $('#mAway').onchange = () => setMatchup($('#mHome').value, $('#mAway').value);
    $('#gpSpread').oninput = renderGameProps;
    $('#gpTotal').oninput = renderGameProps;
    $('#gpTotal').onchange = () => { const v = parseFloat($('#gpTotal').value); if (!isNaN(v)) $('#gpTotal').value = toHalf(v); renderGameProps(); };
    $('#gpLast').onchange = renderGameProps;
    $('#gpProj').onclick = () => { setProjection(); renderGameProps(); };
    const first = D.games.filter(g => g.round === nr && !g.played).sort((a, b) => (a.utc || '').localeCompare(b.utc || ''))[0]
      || D.games.find(g => g.round === nr);
    if (first) setMatchup(first.home, first.away, first.code);
  }

  function setMatchup(h, a, code) {
    state.mHome = h; state.mAway = a;
    $('#mHome').value = h; $('#mAway').value = a;
    const g = code ? D.games.find(x => x.code === code) : D.games.find(x => x.home === h && x.away === a && !x.played) || null;
    $('#mGame').value = g && [...$('#mGame').options].some(o => o.value == g.code) ? g.code : '';
    renderMatchup(g);
  }

  function renderMatchup(g) {
    const h = state.mHome, a = state.mAway, th = T[h], ta = T[a];
    const form = t => `<div class="form">${(t.form || []).map(r => `<span class="${r}">${r}</span>`).join('')}</div>`;
    const d = g?.utc ? new Date(g.utc) : null;
    $('#mHead').innerHTML = `
      <div class="mside">${crest(h, '')}<div class="nm">${esc(th.short)}</div><div class="rec">${th.w}-${th.l} · Home</div>${form(th)}</div>
      <div class="vs">VS<small>${g ? (g.played ? `Final ${g.hs}-${g.as}` : d ? `${fmtDay(d)}, ${fmtTime(d)}` : '') : 'Custom'}</small>${g ? `<small>Round ${g.round}</small>` : ''}</div>
      <div class="mside">${crest(a, '')}<div class="nm">${esc(ta.short)}</div><div class="rec">${ta.w}-${ta.l} · Away</div>${form(ta)}</div>`;

    setProjection();
    renderGameProps();

    // comparison rows: [key, label, higherIsBetter, suffix]
    const rows = [['ppg', 'Points', 1], ['oppg', 'Points allowed', 0], ['diff', 'Point diff', 1], ['pace', 'Pace', 1],
      ['ortg', 'Off. rating', 1], ['drtg', 'Def. rating', 0], ['fgp', 'FG%', 1, '%'], ['tpp', '3PT%', 1, '%'],
      ['tpm', '3PT made', 1], ['opp_tpp', 'Opp 3PT%', 0, '%'], ['rpg', 'Rebounds', 1], ['orpg', 'Off. rebounds', 1],
      ['opp_rpg', 'Opp rebounds', 0], ['apg', 'Assists', 1], ['tpg', 'Turnovers', 0], ['spg', 'Steals', 1], ['ftp', 'FT%', 1, '%']];
    $('#mCompare').innerHTML = rows.map(([k, lab, hib, suf = '']) => {
      const vh = th[k], va = ta[k];
      if (vh == null || va == null) return '';
      const better = vh === va ? 0 : (hib ? vh > va : vh < va) ? -1 : 1;
      const max = Math.max(Math.abs(vh), Math.abs(va)) || 1;
      const side = (v, r, cls, b) => `<div class="v ${cls} ${b ? 'better' : ''}"><span class="num">${n1(v)}${suf}<small>(${r ?? '–'})</small></span><span class="trk"><span class="fill" style="width:${Math.max(4, Math.abs(v) / max * 100)}%"></span></span></div>`;
      return `<div class="cmp">${side(vh, th.rank?.[k], 'l', better === -1)}<div class="lab">${lab}</div>${side(va, ta.rank?.[k], 'r', better === 1)}</div>`;
    }).join('');

    // DvP tables: what each defence allows
    const dvpTable = (team, vsName) => {
      const dv = D.dvp[team]; if (!dv) return '';
      return `<div class="dvp"><h3><b>${esc(short(team))}</b> defence · what ${esc(vsName)} can expect</h3>
        <table class="mini"><thead><tr><th>Pos</th>${STATS4.map(s => `<th>${s[1]}</th>`).join('')}</tr></thead><tbody>` +
        ['G', 'F', 'C'].map(p => `<tr><td><span class="pos ${p}">${p}</span> ${POS[p]}s</td>` + STATS4.map(([k]) => {
          const r = dv[p].rank?.[k];
          return `<td><span class="cell ${rankCls(r)}"><b>${n1(dv[p][k])}</b><i>#${r ?? '–'} · lg ${n1(D.dvpLeague[p][k])}</i></span></td>`;
        }).join('') + '</tr>').join('') + '</tbody></table></div>';
    };
    $('#mDvp').innerHTML = dvpTable(a, short(h)) + dvpTable(h, short(a));

    $('#mPlayersHome').innerHTML = playersVs(h, a);
    $('#mPlayersAway').innerHTML = playersVs(a, h);
    document.querySelectorAll('.pm .pn').forEach(n => n.onclick = () => openLogFor(n.dataset.id));
  }

  function playersVs(team, opp) {
    const ps = D.players.filter(p => p.team === team && p.gp > 0).sort((x, y) => y.min - x.min);
    const dv = D.dvp[opp];
    const injList = (INJ?.teams?.[team] || []).filter(e => e.status !== 'Ready');
    const strip = injList.length ? `<div class="mi">${injList.map(e => `<span><span class="st-pill st-${esc(e.status)}">${esc(e.status)}</span> <b>${esc(e.name)}</b>${e.reason ? ' · ' + esc(e.reason) : ''}</span>`).join('')}</div>` : '';
    const body = ps.map(p => { const ij = INJP[p.id]; const pill = ij && ij.status !== 'Ready' ? ` <span class="st-pill st-${esc(ij.status)}" title="${esc(ij.reason || '')}">${esc(ij.status)}</span>` : '';
      return `<tr class="${ij && ij.status === 'Out' ? 'inj-out' : ''}">
      <td class="t"><span class="nm"><span class="pos ${p.pos}">${p.pos}</span><span><span class="pn" data-id="${esc(p.id)}">${esc(p.name)}</span>${pill}<span class="sub2">${p.gp} GP · ${n1(p.min)} min</span></span></span></td>` +
      STATS4.map(([k]) => {
        const r = dv?.[p.pos]?.rank?.[k];
        return `<td><div class="st"><b>${n1(p[k])}</b><span class="${rankCls(r)}" title="${esc(short(opp))} allows ${n1(dv?.[p.pos]?.[k])} ${k.toUpperCase()} per game to ${POS[p.pos]}s">#${r ?? '–'}</span></div></td>`;
      }).join('') + '</tr>'; }).join('');
    return `<h2 class="h2">${crest(team)}${esc(short(team))} players <small>vs ${esc(short(opp))} defence by position · tap a name for his game log</small></h2>
      ${strip}<div class="tablewrap" style="border:0;background:none"><table class="pm"><thead><tr><th class="t">Player</th>${STATS4.map(s => `<th>${s[1]}</th>`).join('')}</tr></thead>
      <tbody>${body || `<tr><td colspan="5" class="empty">No games played yet.</td></tr>`}</tbody></table></div>`;
  }

  // ---------- GAME PROP CHECK ----------
  const half = x => Math.round(x * 2) / 2;
  const toHalf = x => Math.floor(x) + 0.5;   // totals always end in .5, so no pushes
  const sgn = x => (x > 0 ? '+' : '') + x;
  function teamGames(t) {
    return D.games.filter(g => g.played && (g.home === t || g.away === t))
      .sort((a, b) => (a.utc || '').localeCompare(b.utc || ''))
      .map(g => {
        const home = g.home === t, own = home ? g.hs : g.as, opp = home ? g.as : g.hs;
        return { g, home, own, opp, margin: own - opp, total: g.hs + g.as, oppCode: home ? g.away : g.home };
      });
  }
  function setProjection() {
    const h = T[state.mHome], a = T[state.mAway];
    if (!h?.gp || !a?.gp) { $('#gpProjTxt').textContent = ''; return; }
    // simple projection: average of each side's scoring and the other side's points allowed, +2 home edge
    const hp = (h.ppg + a.oppg) / 2 + 1, ap = (a.ppg + h.oppg) / 2 - 1;
    const spread = half(-(hp - ap));
    $('#gpSpread').value = spread === 0 ? -0.5 : spread;
    $('#gpTotal').value = toHalf(hp + ap);
    $('#gpProjTxt').textContent = `Hub projection: ${short(state.mHome)} ${hp.toFixed(1)} · ${short(state.mAway)} ${ap.toFixed(1)} (season scoring vs points allowed, 2 pt home edge). Overwrite with your bookie's lines.`;
  }
  function renderGameProps() {
    const h = state.mHome, a = state.mAway;
    $('#gpHomeLab').textContent = short(h);
    const sp = parseFloat($('#gpSpread').value), totRaw = parseFloat($('#gpTotal').value), last = +$('#gpLast').value;
    const tot = isNaN(totRaw) ? NaN : toHalf(totRaw);
    const block = (t, line, venueHome) => {
      let gs = teamGames(t);
      if (last) gs = gs.slice(-last);
      if (!gs.length) return `<div class="gpt"><div class="gpt-h">${crest(t, '')}${esc(short(t))}</div><p class="hint">No games played yet.</p></div>`;
      const res = gs.map(x => ({ ...x,
        cov: isNaN(line) ? null : (x.margin + line > 0 ? 'y' : x.margin + line < 0 ? 'n' : 'p'),
        ov: isNaN(tot) ? null : (x.total > tot ? 'y' : x.total < tot ? 'n' : 'p') }));
      const count = (arr, k) => { const dec = arr.filter(r => r[k] && r[k] !== 'p'); const y = dec.filter(r => r[k] === 'y').length; return { y, n: dec.length, pct: dec.length ? Math.round(y / dec.length * 100) : null }; };
      const all = count(res, 'cov'), ven = count(res.filter(r => r.home === venueHome), 'cov');
      const oAll = count(res, 'ov'), oVen = count(res.filter(r => r.home === venueHome), 'ov');
      const avg = k => (res.reduce((s, r) => s + r[k], 0) / res.length);
      const vlab = venueHome ? 'home' : 'away';
      const cls = p => p == null ? '' : p >= 60 ? 'good' : p <= 40 ? 'bad' : '';
      const fmt = c => c.n ? `${c.y}/${c.n}` : '–';
      const lineTxt = isNaN(line) ? 'no line' : `${sgn(line)}`;
      const rows = res.slice().reverse().map(r => `<tr class="${r.home === venueHome ? 'venue' : ''}">
        <td>R${r.g.round}</td><td class="t">${r.home ? 'vs' : '@'} ${crest(r.oppCode)}${esc(short(r.oppCode))}</td>
        <td><span class="tag ${r.margin > 0 ? 'w' : 'l'}">${r.margin > 0 ? 'W' : 'L'}</span> ${r.own}-${r.opp}</td>
        <td class="mg">${sgn(r.margin)}</td>
        <td class="${r.cov || ''}">${r.cov ? { y: '✓', n: '✗', p: 'P' }[r.cov] : '–'}</td>
        <td>${r.total}</td>
        <td class="${r.ov || ''}">${r.ov ? { y: 'O', n: 'U', p: 'P' }[r.ov] : '–'}</td></tr>`).join('');
      return `<div class="gpt">
        <div class="gpt-h">${crest(t, '')}${esc(short(t))}<span class="ln">${esc(short(t))} ${lineTxt}</span></div>
        <div class="gpk">
          <div><span>Covered ${lineTxt}</span><b class="${cls(all.pct)}">${all.pct ?? '–'}${all.pct != null ? '%' : ''}</b><i>${fmt(all)} · <em>${vlab} ${fmt(ven)}</em></i></div>
          <div><span>Over ${isNaN(tot) ? '–' : tot}</span><b class="${cls(oAll.pct)}">${oAll.pct ?? '–'}${oAll.pct != null ? '%' : ''}</b><i>${fmt(oAll)} · <em>${vlab} ${fmt(oVen)}</em></i></div>
          <div><span>Avg margin</span><b>${sgn(avg('margin').toFixed(1))}</b><i>${res.filter(r => r.margin > 0).length}-${res.filter(r => r.margin < 0).length} in these games</i></div>
          <div><span>Avg total</span><b>${avg('total').toFixed(1)}</b><i>scores ${avg('own').toFixed(1)} · allows ${avg('opp').toFixed(1)}</i></div>
        </div>
        <div class="tablewrap" style="border:0;background:none"><table class="gpl"><thead><tr><th>Rd</th><th class="t">Opponent</th><th>Score</th><th class="mg">Margin</th><th>Cover</th><th>Total</th><th>O/U</th></tr></thead><tbody>${rows}</tbody></table></div>
      </div>`;
    };
    $('#gpOut').innerHTML = block(h, sp, true) + block(a, isNaN(sp) ? NaN : -sp, false);
  }

  // ---------- INJURIES ----------
  const ST = ['Out', 'Doubtful', 'Uncertain', 'Game-time', 'Ready'];
  const iState = { status: '' };
  function initInjuries() {
    if (!INJ) { $('#injList').innerHTML = '<div class="empty">No injury report loaded yet.</div>'; return; }
    const pub = INJ.published || INJ.fetched;
    $('#injStamp').textContent = `Updated ${new Date(pub).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}` +
      (INJ.fetched ? ` · pulled ${new Date(INJ.fetched).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}` : '');
    if (INJ.source) $('#injCredit').href = INJ.source;
    const codes = Object.keys(T).sort((a, b) => short(a).localeCompare(short(b)));
    $('#iTeam').innerHTML = '<option value="">All</option>' + codes.map(c => `<option value="${c}">${esc(short(c))}</option>`).join('');
    const counts = s => Object.values(INJ.teams).flat().filter(e => !s || e.status === s).length;
    $('#iStatus').innerHTML = `<button class="chip all on" data-s="">All ${counts('')}</button>` +
      ST.map(s => `<button class="chip" data-s="${s}"><span class="st-pill st-${s}">${s}</span> ${counts(s)}</button>`).join('');
    $('#iStatus').onclick = e => { const b = e.target.closest('.chip'); if (!b) return; iState.status = b.dataset.s;
      $('#iStatus').querySelectorAll('.chip').forEach(x => x.classList.toggle('on', x === b)); renderInjuries(); };
    $('#iTeam').onchange = renderInjuries;
    renderInjuries();
  }
  function nextGameOf(t) {
    return D.games.filter(g => !g.played && (g.home === t || g.away === t)).sort((a, b) => (a.utc || '').localeCompare(b.utc || ''))[0];
  }
  function renderInjuries() {
    const team = $('#iTeam').value;
    const codes = team ? [team] : Object.keys(T);
    const cards = codes.map(c => ({ c, g: nextGameOf(c), list: (INJ.teams[c] || []).filter(e => !iState.status || e.status === iState.status) }))
      .sort((a, b) => ((a.g?.utc || 'z').localeCompare(b.g?.utc || 'z')) || short(a.c).localeCompare(short(b.c)));
    const html = cards.map(({ c, g, list }) => {
      if (iState.status && !list.length) return '';
      const nx = g ? `<span class="nx">R${g.round} ${g.home === c ? 'vs' : '@'} <b>${esc(short(g.home === c ? g.away : g.home))}</b><br>${new Date(g.utc).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })} ${fmtTime(new Date(g.utc))}</span>` : '';
      const rows = list.map(e => `<div class="injr">
          <span class="pos ${e.pos.includes('C') ? 'C' : /F/.test(e.pos) ? 'F' : 'G'}">${esc(e.pos)}</span>
          <span class="who">${e.pid ? `<span class="pn" data-id="${esc(e.pid)}">${esc(e.name)}</span>` : `<span class="nm0">${esc(e.name)}</span>`}
            <span class="st-pill st-${esc(e.status)}">${esc(e.status)}</span>
            <span class="meta">${e.reason ? `<em>${esc(e.reason)}</em>` : 'No reason given'}${e.pid ? ` · ${n1(e.pts)} pts, ${n1(e.min)} min in ${e.gp} GP` : ' · no EuroLeague minutes'}</span></span>
          <span class="rt"><b>${esc(e.round)}</b>${e.back ? 'Back: ' + esc(e.back) : ''}</span>
        </div>`).join('');
      return `<div class="injt"><div class="injt-h">${crest(c, '')}${esc(short(c))}${nx}</div>${rows || '<p class="hint" style="padding:8px 0 2px">No players listed.</p>'}</div>`;
    }).join('');
    $('#injList').innerHTML = html || '<div class="empty">No players match these filters.</div>';
    $('#injList').querySelectorAll('.pn').forEach(n => n.onclick = () => openLogFor(n.dataset.id));
  }

  // ---------- GAME LOG ----------
  function initLog() {
    const codes = Object.keys(T).sort((a, b) => short(a).localeCompare(short(b)));
    $('#lTeam').innerHTML = '<option value="">All teams</option>' + codes.map(c => `<option value="${c}">${esc(short(c))}</option>`).join('');
    fillPlayerList();
    $('#lTeam').onchange = () => { $('#lPlayer').value = ''; fillPlayerList(); renderLog(); };
    $('#lPos').onchange = renderLog;
    $('#lLast').onchange = renderLog;
    $('#lPlayer').oninput = renderLog;
    $('#lReset').onclick = () => { $('#lTeam').value = ''; $('#lPos').value = ''; $('#lPlayer').value = ''; $('#lLast').value = '0'; fillPlayerList(); renderLog(); };
    $('#pStat').onchange = renderLog; $('#pLine').oninput = renderLog;
    renderLog();
  }
  function fillPlayerList() {
    const t = $('#lTeam').value;
    $('#lPlayers').innerHTML = D.players.filter(p => !t || p.team === t).sort((a, b) => a.name.localeCompare(b.name))
      .map(p => `<option value="${esc(p.name)}">${esc(short(p.team))} · ${POS[p.pos]}</option>`).join('');
  }
  function openLogFor(id) {
    const p = D.players.find(x => x.id === id); if (!p) return;
    $('#lTeam').value = ''; $('#lPos').value = ''; fillPlayerList(); $('#lPlayer').value = p.name;
    showTab('log'); renderLog();
  }

  const COLS = [['round', 'Rd'], ['utc', 'Date', 't'], ['name', 'Player', 't'], ['pos', 'Pos'], ['team', 'Team', 't'], ['opp', 'Opp', 't'], ['res', 'Res'],
    ['min', 'MIN'], ['pts', 'PTS'], ['reb', 'REB'], ['ast', 'AST'], ['fgm', 'FGM'], ['fga', 'FGA'], ['fg3m', '3PM'], ['fg3a', '3PA'], ['ftm', 'FTM'], ['fta', 'FTA'], ['stl', 'STL'], ['blk', 'BLK'], ['tov', 'TOV'], ['pir', 'PIR']];

  function renderLog() {
    const t = $('#lTeam').value, pos = $('#lPos').value, q = $('#lPlayer').value.trim().toLowerCase(), last = +$('#lLast').value;
    let rows = L.filter(r => (!t || r.team === t) && (!pos || r.pos === pos) && (!q || r.name.toLowerCase().includes(q)));
    const exact = q && D.players.find(p => p.name.toLowerCase() === q);
    if (exact) rows = rows.filter(r => r.id === exact.id);
    if (last) {
      // last N games per player
      const by = {}; rows.slice().sort((a, b) => b.round - a.round).forEach(r => { (by[r.id] ||= []); if (by[r.id].length < last) by[r.id].push(r); });
      rows = Object.values(by).flat();
    }
    const { k, dir } = state.sort;
    rows.sort((a, b) => { const x = a[k], y = b[k]; return (typeof x === 'string' ? x.localeCompare(y) : x - y) * dir || b.round - a.round || b.pts - a.pts; });

    // single player: summary + prop check
    const ids = new Set(rows.map(r => r.id));
    const single = ids.size === 1 && rows.length;
    $('#propBox').hidden = !single;
    let hitKey = null, line = null;
    if (single) {
      const r0 = rows[0], n = rows.length, avg = f => (rows.reduce((s, r) => s + r[f], 0) / n).toFixed(1);
      const pct = (m, a) => { const A = rows.reduce((s, r) => s + (r[a] || 0), 0); return A ? (100 * rows.reduce((s, r) => s + (r[m] || 0), 0) / A).toFixed(1) + '%' : '–'; };
      $('#logSummary').innerHTML = `<div class="stat who"><span>${esc(short(r0.team))} · ${POS[r0.pos]}</span><b>${esc(r0.name)}</b></div>` +
        [['GP', n], ['MIN', avg('min')], ['PTS', avg('pts')], ['REB', avg('reb')], ['AST', avg('ast')], ['3PM', avg('fg3m')],
         ['FG%', pct('fgm', 'fga')], ['FT%', pct('ftm', 'fta')]]
          .map(([l, v]) => `<div class="stat"><b>${v}</b><span>${l}</span></div>`).join('');
      hitKey = $('#pStat').value; line = parseFloat($('#pLine').value);
      const val = r => hitKey === 'pra' ? r.pts + r.reb + r.ast : r[hitKey];
      if (!isNaN(line)) {
        const hits = rows.filter(r => val(r) > line).length;
        $('#pOut').innerHTML = `Over in <b>${hits}/${n}</b> games (${Math.round(hits / n * 100)}%)`;
      } else $('#pOut').textContent = '';
    } else $('#logSummary').innerHTML = '';

    const shown = rows.slice(0, 600);
    const head = `<thead><tr>${COLS.map(([c, lab, cls]) => `<th class="${cls || ''} ${c === k ? 'sorted' : ''}" data-k="${c}">${lab}${c === k ? (dir < 0 ? ' ↓' : ' ↑') : ''}</th>`).join('')}</tr></thead>`;
    const statCls = (r, c) => {
      if (!hitKey || isNaN(line)) return '';
      if (hitKey === 'pra' ? !['pts', 'reb', 'ast'].includes(c) : c !== hitKey) return '';
      const v = hitKey === 'pra' ? r.pts + r.reb + r.ast : r[c];
      return v > line ? 'hit' : 'miss';
    };
    const body = shown.map(r => `<tr>` + COLS.map(([c, , cls]) => {
      let v = r[c];
      if (c === 'utc') v = r.utc ? new Date(r.utc).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) : '';
      else if (c === 'name') v = `<span class="pn" data-id="${esc(r.id)}">${esc(r.name)}</span>`;
      else if (c === 'pos') v = `<span class="pos ${r.pos}">${r.pos}</span>`;
      else if (c === 'team') v = crest(r.team) + esc(short(r.team));
      else if (c === 'opp') v = (r.ha === 'A' ? '@ ' : 'vs ') + esc(short(r.opp));
      else if (c === 'res') v = `<span class="tag ${r.res.toLowerCase()}">${r.res}</span>`;
      else if (c === 'min') v = (+v).toFixed(1);
      return `<td class="${cls || ''} ${statCls(r, c)}">${v}</td>`;
    }).join('') + '</tr>').join('');
    $('#logTable').innerHTML = head + `<tbody>${body || `<tr><td colspan="${COLS.length}" class="empty">No games match these filters.</td></tr>`}</tbody>`;
    $('#logTable').querySelectorAll('th').forEach(th => th.onclick = () => {
      const kk = th.dataset.k;
      state.sort = { k: kk, dir: state.sort.k === kk ? -state.sort.dir : (['name', 'team', 'opp', 'pos'].includes(kk) ? 1 : -1) };
      renderLog();
    });
    $('#logTable').querySelectorAll('.pn').forEach(n => n.onclick = () => openLogFor(n.dataset.id));
    $('#logCount').textContent = rows.length > shown.length ? `Showing ${shown.length} of ${rows.length} rows. Filter by team or player to narrow it down.` : `${rows.length} rows`;
  }

  // ---------- boot ----------
  fetch('data/hub.json', { cache: 'no-cache' }).then(r => r.json()).then(data => {
    D = data; T = D.teams;
    F = D.logFields;
    L = D.log.map(row => Object.fromEntries(F.map((f, i) => [f, row[i]])));
    const yr = (D.season || '').replace(/^E/, '');
    $('#seasonLine').textContent = `${yr}-${String((+yr + 1) % 100).padStart(2, '0')} season · through Round ${D.lastRound}`;
    $('#updated').textContent = D.updated ? 'Updated ' + new Date(D.updated).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
    return fetch('data/injuries.json', { cache: 'no-cache' }).then(r => r.ok ? r.json() : null).catch(() => null).then(inj => {
      INJ = inj;
      if (INJ) Object.values(INJ.teams).flat().forEach(e => { if (e.pid) INJP[e.pid] = e; });
      initSchedule(); initMatchup(); initLog(); initInjuries();
    const h = location.hash.replace('#', '');
    if (['schedule', 'matchup', 'log', 'injuries'].includes(h)) showTab(h);
    });
  }).catch(err => {
    $('#schedList').innerHTML = `<div class="empty">Couldn't load the data (${esc(err.message)}).</div>`;
  });
})();
