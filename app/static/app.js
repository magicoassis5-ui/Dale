(() => {
  const $ = (id) => document.getElementById(id);
  function fmtUsd(v) {
    const sign = v > 0 ? "+" : (v < 0 ? "-" : "");
    return `${sign}$${Math.abs(v).toFixed(2)}`;
  }
  function fmtPct(v) { return `${v > 0 ? "+" : ""}${Number(v).toFixed(0)}%`; }
  function fmtTime(d) { return d.toTimeString().slice(0, 8); }
  async function fetchJson(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`${path} ${r.status}`);
    return r.json();
  }
  function renderSummary(s) {
    const mtmEl = $("mtmValue");
    mtmEl.textContent = fmtUsd(s.mtm);
    mtmEl.style.color = s.mtm >= 0 ? "var(--pos)" : "var(--neg)";
    $("mtmSub").textContent = `${s.mtm_pct >= 0 ? "+" : ""}${s.mtm_pct.toFixed(1)}% sobre $${s.bankroll} — ${s.winning} ganhando • ${s.losing} perdendo`;
    const rEl = $("realizedValue");
    rEl.textContent = fmtUsd(s.realized);
    rEl.style.color = s.realized >= 0 ? "var(--pos)" : "var(--neg)";
    $("realizedSub").textContent = `${s.closed_count} trades fechados • ${s.win_rate}% win rate`;
    $("mActiveCities").textContent = s.active_cities;
    if (s.cities_list && s.cities_list.length) {
      $("mCitiesList").textContent = s.cities_list.join(", ");
    }
    $("mMinEdge").textContent = `${(s.min_edge * 100).toFixed(0)}%`;
    $("mFees").textContent = `$${s.fees.toFixed(2)}`;
    $("mNextResolve").textContent = s.next_resolve_h != null ? `${s.next_resolve_h.toFixed(1)}h` : "—";
    const today = $("rPnlToday");
    today.textContent = fmtUsd(s.realized_today);
    today.className = "value sm " + (s.realized_today >= 0 ? "pos" : "neg");
    $("rLossLimit").textContent = `$${s.daily_loss_limit}`;
    $("rTradeSize").textContent = `$${s.trade_size}`;
    $("rMinEdge").textContent = `${(s.min_edge * 100).toFixed(0)}%`;
    $("btBankroll").textContent = s.bankroll;
    $("updatedAt").textContent = fmtTime(new Date());
    $("openCount").textContent = s.open_count;
    $("mode").textContent = s.mode;
  }
  function renderConfig(c) {
    $("proxy").textContent = c.proxy_configured ? "ON" : "off";
    $("owm").textContent = c.owm_configured ? "ON" : "off";
    $("wallet").textContent = c.wallet_configured ? "ON" : "off";
  }
  function renderBacktest(bt) {
    $("btRange").textContent = `${bt.from} → ${bt.to}`;
    $("btRoi").textContent = `+${bt.roi_pct.toFixed(1)}%`;
    $("btPnl").textContent = `$${bt.pnl.toLocaleString()}`;
    $("btTrades").textContent = bt.trades.toLocaleString();
    $("btProjected").textContent = `~$${bt.projected_24h_usd.toFixed(2)}`;
    $("btHorizon").textContent = "24h";
  }
  function unitFmt(t, u) {
    if (t == null) return "";
    if (u === "F") return `${Math.round(t * 9/5 + 32)}°F`;
    return `${Math.round(t)}°C`;
  }
  function renderPositions(rows) {
    const grid = $("grid");
    if (!rows.length) {
      grid.innerHTML = `<div class="muted small" style="padding:20px">Aguardando posições…</div>`;
      return;
    }
    grid.innerHTML = rows.map((p) => {
      const win = p.pnl_usd >= 0;
      const tempStr = unitFmt(p.threshold_c, p.threshold_unit || "C");
      const cityLine = `${p.city || p.market_id}${tempStr ? " · " + tempStr : ""}`;
      const fee = (p.fee || 0).toFixed(2);
      const resolve = p.resolves_in_h != null ? `${p.resolves_in_h.toFixed(1)}h` : "—";
      return `
        <div class="pcard ${win ? 'win' : 'loss'}">
          <div class="head"><div class="city">${cityLine}</div><div class="badge">${p.side}</div></div>
          <div class="entry">entry $${p.entry.toFixed(3)} <span class="arrow">→</span> $${p.last.toFixed(3)}</div>
          <div class="pnl">
            <span class="usd">${fmtUsd(p.pnl_usd)}</span>
            <span class="pct">(${fmtPct(p.pnl_pct)})</span>
          </div>
          <div class="meta">
            <span>resolve em ${resolve}</span>
            <span>edge ${p.edge_at_entry.toFixed(1)}%</span>
            <span>fee $${fee}</span>
          </div>
        </div>`;
    }).join("");
  }
  let inflight = false;
  async function refresh() {
    if (inflight) return;
    inflight = true;
    try {
      const [s, pos, bt, cfg] = await Promise.all([
        fetchJson("/api/summary"), fetchJson("/api/positions/open"),
        fetchJson("/api/backtest/last"), fetchJson("/api/config"),
      ]);
      renderSummary(s); renderBacktest(bt); renderConfig(cfg); renderPositions(pos);
    } catch(e) { console.error(e); } finally { inflight = false; }
  }
  function connectWs() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => { $("liveLabel").textContent = "LIVE"; };
    ws.onclose = () => { $("liveLabel").textContent = "OFFLINE"; setTimeout(connectWs, 2000); };
    ws.onmessage = (ev) => {
      try {
        const m = JSON.parse(ev.data);
        if (["tick","orderbook_tick","position_opened","position_closed"].includes(m.type)) refresh();
      } catch {}
    };
  }
  refresh(); setInterval(refresh, 5000); connectWs();
})();
