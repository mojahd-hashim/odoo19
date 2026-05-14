/* ═══════════════════════════════════════════════════════════
   Waqf Executive Dashboard — JS v2
   New: Phase Gantt · Mosque heatmap detail · Global search
        Cert/CO detail modals · Extra KPI badges
   ═══════════════════════════════════════════════════════════ */
'use strict';

document.addEventListener('DOMContentLoaded', function () {

  // ── State ──────────────────────────────────────────────────
  const dataEl = document.getElementById('waqf-data');
  window.WAQF_DASH_CONFIG = JSON.parse(dataEl.dataset.config   || '{}');
  window.WAQF_PACKAGES    = JSON.parse(dataEl.dataset.packages || '[]');
  const state = {
    activeMosqueId: null,
    packages:       window.WAQF_PACKAGES || [],
    mosques:        [],
    chatHistory:    [],
    mosqueContext:  null,
    refreshTimer:   null,
    config:         window.WAQF_DASH_CONFIG || {},
    allMosques:     [], // flat list for search
  };

  const $ = id => document.getElementById(id);
  const fmt  = n  => new Intl.NumberFormat('ar-SA').format(Math.round(n));
  const pct  = n  => Math.round(n) + '%';
  const fmtDate = s => s ? s.substring(0, 7).replace('-', '/') : '—';

  // ── API helpers ────────────────────────────────────────────
  async function apiGet(url) {
    const r = await fetch(url, { credentials: 'same-origin' });
    return r.json();
  }
  async function apiPost(url, data) {
    const csrfToken = document.cookie.match(/csrf_token=([^;]+)/)?.[1] || '';
    const r = await fetch(url, {
      method:  'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
      body:    JSON.stringify({ jsonrpc: '2.0', method: 'call', params: data }),
    });
    const json = await r.json();
    return json.result;
  }

  // ══════════════════════════════════════════════════════════
  // INIT
  // ══════════════════════════════════════════════════════════
  async function init() {
    // Packages already injected by server — build sidebar + gantt immediately
    if (state.packages.length) {
      buildSidebar(state.packages);
      buildPhaseGantt(state.packages);
      // flatten mosques for search
      state.packages.forEach(pkg =>
        pkg.mosques.forEach(m => state.allMosques.push({ ...m, package: pkg.name })));
    }

    // Load mosques for heatmap
    const mosques = await apiGet('/dashboard/api/mosques');
    state.mosques = mosques;
    // update allMosques with full data
    state.allMosques = mosques.map(m => ({
      ...m, package: m.package || '',
    }));
    buildHeatmap();
    loadOnSite();
    checkLiveStream();
    initSearch();
    initQuickFilters();
    startRefresh();
  }

  // ══════════════════════════════════════════════════════════
  // SIDEBAR
  // ══════════════════════════════════════════════════════════
  function buildSidebar(pkgs) {
    const container = $('sb-packages');
    if (!container) return;
    container.innerHTML = '';
    pkgs.forEach(pkg => {
      const div = document.createElement('div');
      div.className = 'sb-pkg';
      const phaseClass = pkg.is_current ? 'current' : pkg.is_past ? 'past' : 'future';
      div.innerHTML = `
        <div class="sb-pkg-hdr ${phaseClass}" data-pkg="${pkg.id}">
          <span>${pkg.name}</span>
          <span class="sb-pkg-badge">${pkg.mosque_count}</span>
          ${pkg.is_current ? '<span class="sb-pkg-live">نشط</span>' : ''}
          <span class="sb-pkg-arrow">›</span>
        </div>
        <div class="sb-pkg-mosques" style="display:none">
          ${pkg.mosques.map(m => `
            <div class="sb-mosque ${colorClass(m.overall_kpi)}" data-id="${m.id}">
              <div class="sb-mosque-dot" style="background:${dotColor(m.overall_kpi)}"></div>
              <span>${truncate(m.name, 16)}</span>
              <span class="sb-mosque-code">${m.code}</span>
            </div>`).join('')}
        </div>`;
      container.appendChild(div);

      div.querySelector('.sb-pkg-hdr').addEventListener('click', function () {
        const mosques = div.querySelector('.sb-pkg-mosques');
        const open = mosques.style.display !== 'none';
        mosques.style.display = open ? 'none' : '';
        this.classList.toggle('open', !open);
      });
      div.querySelectorAll('.sb-mosque').forEach(el => {
        el.addEventListener('click', function () {
          document.querySelectorAll('.sb-mosque').forEach(m => m.classList.remove('active'));
          this.classList.add('active');
          loadMosqueDetail(parseInt(this.dataset.id));
        });
      });
    });
    // Open current phase by default
    const currentHdr = container.querySelector('.sb-pkg-hdr.current');
    if (currentHdr) currentHdr.click();
    else {
      const firstHdr = container.querySelector('.sb-pkg-hdr');
      if (firstHdr) firstHdr.click();
    }
  }

  // ══════════════════════════════════════════════════════════
  // PHASE GANTT — المخطط الزمني بالمراحل + تفاصيل المساجد
  // ══════════════════════════════════════════════════════════
  function buildPhaseGantt(pkgs) {
    const el       = $('gantt-rows');
    const monthsEl = $('gantt-months');
    if (!el) return;

    // Project date range
    const projectStart = new Date('2026-04-01');
    const projectEnd   = new Date('2027-04-30');
    const totalMs      = projectEnd - projectStart;
    const today        = new Date();
    const todayPct     = Math.min(100, Math.max(0, (today - projectStart) / totalMs * 100));

    // Months header
    if (monthsEl) {
      monthsEl.innerHTML = '';
      const months = ['أبر٢٦','مايو','يون','يول','أغس','سبت','أكت','نوف','ديس','يناير٢٧','فبر','مارس','أبر٢٧'];
      months.forEach(m => {
        const d = document.createElement('div');
        d.className = 'gantt-month';
        d.textContent = m;
        monthsEl.appendChild(d);
      });
    }

    el.innerHTML = '';

    // Color per phase
    const phaseColors = {
      current: '#237292',
      past:    '#2ECC8A',
      future:  '#8FA3B3',
    };

    pkgs.forEach(pkg => {
      if (!pkg.planned_start || !pkg.planned_end) return;
      const start = new Date(pkg.planned_start);
      const end   = new Date(pkg.planned_end);
      const leftPct  = Math.max(0, (start - projectStart) / totalMs * 100);
      const widthPct = Math.min(100 - leftPct, (end - start) / totalMs * 100);
      const phase    = pkg.is_current ? 'current' : pkg.is_past ? 'past' : 'future';
      const color    = phaseColors[phase];

      // progress fill inside bar
      let progressPct = 0;
      if (phase === 'past') progressPct = 100;
      else if (phase === 'current') {
        const elapsed = Math.max(0, today - start);
        const total   = end - start;
        progressPct = Math.min(100, elapsed / total * 100);
      }

      const row = document.createElement('div');
      row.className = 'gantt-row';
      row.innerHTML = `
        <div class="gantt-label" title="${pkg.name}">
          <span class="gantt-phase-dot" style="background:${color}"></span>
          ${pkg.code}
          ${pkg.is_current ? '<span class="gantt-live-badge">الآن</span>' : ''}
        </div>
        <div class="gantt-track" data-pkg="${pkg.id}">
          <!-- background bar -->
          <div class="gantt-bar-bg" style="right:${leftPct}%;width:${widthPct}%;background:${color}22;border:1px solid ${color}44;border-radius:6px">
            <!-- progress fill -->
            <div class="gantt-bar-progress" style="width:${progressPct}%;background:${color};border-radius:5px;height:100%;transition:width 1s ease"></div>
            <!-- label -->
            <span class="gantt-bar-label" style="color:${color}">
              ${pkg.avg_kpi}% · ${pkg.mosque_count}م
            </span>
          </div>
          <!-- today line -->
          <div class="gantt-today" style="right:${todayPct}%">
            <div class="gantt-today-label">اليوم</div>
          </div>
          <!-- popup -->
          <div class="gantt-popup" id="gantt-popup-${pkg.id}">
            <div class="gantt-popup-title">${pkg.name}</div>
            <div class="gantt-popup-meta">
              ${pkg.planned_start} — ${pkg.planned_end}
            </div>
            <div class="gantt-popup-row">
              <span class="gantt-popup-label">KPI الحالي</span>
              <span class="gantt-popup-val" style="color:${color}">${pkg.avg_kpi}%</span>
            </div>
            <div class="gantt-popup-row">
              <span class="gantt-popup-label">المرحلة</span>
              <span class="gantt-popup-val">${phase === 'current' ? '🟢 نشطة الآن' : phase === 'past' ? '✅ منتهية' : '⏳ قادمة'}</span>
            </div>
            <!-- Mosques list in popup -->
            <div style="margin-top:10px;border-top:1px solid var(--border);padding-top:8px">
              <div style="font-size:10px;font-weight:600;color:var(--text3);margin-bottom:6px">المساجد (${pkg.mosque_count})</div>
              <div class="gantt-mosques-list">
                ${pkg.mosques.slice(0, 6).map(m => `
                  <div class="gantt-mosque-row" onclick="loadMosqueDetailGlobal(${m.id})">
                    <div class="gantt-m-dot" style="background:${dotColor(m.overall_kpi)}"></div>
                    <span class="gantt-m-code">${m.code}</span>
                    <span class="gantt-m-name">${truncate(m.name, 14)}</span>
                    <span class="gantt-m-kpi" style="color:${dotColor(m.overall_kpi)}">${m.overall_kpi}%</span>
                    ${m.days_delay > 0 ? `<span class="gantt-m-delay">-${m.days_delay}د</span>` : ''}
                  </div>`).join('')}
                ${pkg.mosques.length > 6 ? `
                  <div style="font-size:10px;color:var(--text3);text-align:center;padding-top:4px">
                    +${pkg.mosques.length - 6} مسجد آخر
                  </div>` : ''}
              </div>
            </div>
          </div>
        </div>`;
      el.appendChild(row);

      // Toggle popup on track click
      const track = row.querySelector('.gantt-track');
      const popup  = row.querySelector('.gantt-popup');
      track.addEventListener('click', e => {
        e.stopPropagation();
        document.querySelectorAll('.gantt-popup').forEach(p => p !== popup && p.classList.remove('show'));
        popup.classList.toggle('show');
      });
    });

    document.addEventListener('click', () =>
      document.querySelectorAll('.gantt-popup').forEach(p => p.classList.remove('show')));
  }

  // global helper so inline onclick can call it
  window.loadMosqueDetailGlobal = function(id) {
    document.querySelectorAll('.gantt-popup').forEach(p => p.classList.remove('show'));
    loadMosqueDetail(id);
  };

  // ══════════════════════════════════════════════════════════
  // HEATMAP — مع تفاصيل المسجد عند النقر
  // ══════════════════════════════════════════════════════════
  function buildHeatmap() {
    const el = $('heatmap-grid');
    if (!el) return;
    el.innerHTML = '';

    state.mosques.forEach(m => {
      const cell = document.createElement('div');
      cell.className = `hm-cell ${m.kpi_color}`;
      cell.dataset.id = m.id;
      // رمز المسجد المختصر
      const shortCode = (m.code || '').replace(/^(RUH|JED|TIF|RFH|AFJ|YRA|GIZ)-0?/, '');
      cell.textContent = shortCode;

      // Tooltip
      const tip = document.createElement('div');
      tip.className = 'hm-tooltip';
      tip.innerHTML = `
        <strong>${m.code}</strong><br/>
        ${truncate(m.name, 18)}<br/>
        KPI: ${m.overall_kpi}%
        ${m.days_delay > 0 ? `<br/><span style="color:#F87171">تأخير ${m.days_delay} يوم</span>` : ''}`;
      cell.appendChild(tip);

      cell.addEventListener('click', function () {
        document.querySelectorAll('.hm-cell').forEach(c => c.classList.remove('active'));
        this.classList.add('active');
        // Sync sidebar
        document.querySelectorAll('.sb-mosque').forEach(s =>
          s.classList.toggle('active', parseInt(s.dataset.id) === m.id));
        loadMosqueDetail(parseInt(this.dataset.id));
      });
      el.appendChild(cell);
    });
  }

  // ══════════════════════════════════════════════════════════
  // GLOBAL SEARCH
  // ══════════════════════════════════════════════════════════
  function initSearch() {
    const input    = $('global-search');
    const dropdown = $('search-dropdown');
    if (!input || !dropdown) return;

    input.addEventListener('input', function () {
      const q = this.value.trim().toLowerCase();
      if (q.length < 2) { dropdown.classList.remove('show'); return; }

      // Search mosques, packages
      const results = [];

      // Mosques
      state.allMosques.filter(m =>
        m.name?.toLowerCase().includes(q) ||
        m.code?.toLowerCase().includes(q) ||
        m.package?.toLowerCase().includes(q)
      ).slice(0, 6).forEach(m => results.push({
        type:  'mosque',
        label: m.name,
        meta:  `${m.code} · ${m.package} · KPI ${m.overall_kpi}%`,
        color: dotColor(m.overall_kpi),
        id:    m.id,
      }));

      // Packages
      state.packages.filter(pkg =>
        pkg.name?.toLowerCase().includes(q) ||
        pkg.code?.toLowerCase().includes(q)
      ).slice(0, 3).forEach(pkg => results.push({
        type:  'package',
        label: pkg.name,
        meta:  `${pkg.mosque_count} مساجد · KPI ${pkg.avg_kpi}%`,
        color: '#237292',
        id:    pkg.id,
      }));

      if (!results.length) {
        dropdown.innerHTML = '<div class="search-empty">لا توجد نتائج</div>';
      } else {
        dropdown.innerHTML = results.map(r => `
          <div class="search-item" data-type="${r.type}" data-id="${r.id}">
            <div class="search-item-dot" style="background:${r.color}"></div>
            <div class="search-item-body">
              <div class="search-item-label">${r.label}</div>
              <div class="search-item-meta">${r.meta}</div>
            </div>
            <div class="search-item-type">${r.type === 'mosque' ? '🕌' : '📦'}</div>
          </div>`).join('');

        dropdown.querySelectorAll('.search-item').forEach(item => {
          item.addEventListener('click', function () {
            const type = this.dataset.type;
            const id   = parseInt(this.dataset.id);
            dropdown.classList.remove('show');
            input.value = '';
            if (type === 'mosque') loadMosqueDetail(id);
            else {
              // scroll sidebar to package
              const hdr = document.querySelector(`[data-pkg="${id}"]`);
              if (hdr && !hdr.classList.contains('open')) hdr.click();
              hdr?.scrollIntoView({ behavior: 'smooth' });
            }
          });
        });
      }
      dropdown.classList.add('show');
    });

    input.addEventListener('keydown', e => {
      if (e.key === 'Escape') { dropdown.classList.remove('show'); input.value = ''; }
    });

    document.addEventListener('click', e => {
      if (!input.contains(e.target) && !dropdown.contains(e.target))
        dropdown.classList.remove('show');
    });
  }

  // ══════════════════════════════════════════════════════════
  // QUICK FILTERS
  // ══════════════════════════════════════════════════════════
  function initQuickFilters() {
    document.querySelectorAll('.qf-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.qf-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        const filter = this.dataset.filter;
        filterHeatmap(filter);
      });
    });
  }

  function filterHeatmap(filter) {
    document.querySelectorAll('.hm-cell').forEach(cell => {
      const mosqueId = parseInt(cell.dataset.id);
      const mosque   = state.mosques.find(m => m.id === mosqueId);
      if (!mosque) return;
      let visible = true;
      if (filter === 'delayed')  visible = mosque.days_delay > 0;
      if (filter === 'ok')       visible = mosque.overall_kpi >= 70;
      if (filter === 'warn')     visible = mosque.overall_kpi >= 50 && mosque.overall_kpi < 70;
      if (filter === 'critical') visible = mosque.overall_kpi < 50 && mosque.overall_kpi > 0;
      cell.style.opacity = visible ? '1' : '0.2';
      cell.style.transform = visible ? '' : 'scale(0.85)';
    });
  }

  // ══════════════════════════════════════════════════════════
  // MOSQUE DETAIL
  // ══════════════════════════════════════════════════════════
  async function loadMosqueDetail(mosqueId) {
    state.activeMosqueId = mosqueId;

    const mosque = state.mosques.find(m => m.id === mosqueId);
    if (mosque) {
      $('topbar-title').textContent = mosque.name;
      $('topbar-sub').textContent   =
        `${mosque.code} · ${mosque.package} · ${stateLabel(mosque.state)}` +
        (mosque.days_delay > 0 ? ` · ⚠ تأخير ${mosque.days_delay} يوم` : '');
    }

    $('mosque-detail-content').innerHTML = `
      <div style="padding:40px;text-align:center">
        <div class="loading-spinner" style="width:32px;height:32px;margin:0 auto"></div>
        <div style="margin-top:12px;color:var(--text3);font-size:12px">جاري تحميل بيانات المسجد...</div>
      </div>`;

    const data = await apiGet(`/dashboard/api/mosque/${mosqueId}`);
    if (!data.mosque) return;

    const m = data.mosque;
    state.mosqueContext = {
      name:         m.name,
      overall_kpi:  m.overall_kpi,
      financial_pct:m.financial_kpi,
      time_pct:     m.time_kpi,
      days_delay:   m.days_delay,
      pending_certs: data.certs.filter(c =>
        ['submitted','consultant_approved'].includes(c.state)).length,
    };

    $('mosque-detail-content').innerHTML = buildMosqueDetailHTML(data);
    initMosqueDetailEvents(data);
    drawKpiRings(m);
    drawBoqChart(data.boq_categories);

    // Scroll into view
    $('section-mosque')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function buildMosqueDetailHTML(data) {
    const m = data.mosque;
    const pendingCerts  = data.certs.filter(c =>
      ['submitted','consultant_approved'].includes(c.state)).length;
    const pendingCOs    = data.change_orders.filter(co => co.state === 'review').length;
    const totalCertVal  = data.certs.reduce((s, c) => s + (c.total_value || 0), 0);

    return `
<!-- ── Mosque hero header ── -->
<div class="mosque-hero" style="
  background:linear-gradient(135deg,var(--navy) 0%,var(--navy-deep) 100%);
  border-radius:var(--radius-lg);padding:20px 24px;
  margin-bottom:14px;display:flex;align-items:center;gap:18px;
  box-shadow:var(--shadow-md)">
  <div style="flex:1">
    <div style="font-size:18px;font-weight:700;color:#fff;margin-bottom:4px">${m.name}</div>
    <div style="font-size:12px;color:rgba(255,255,255,.55)">
      ${m.code} · ${m.city} ${m.district ? '· ' + m.district : ''}
    </div>
    <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
      <span style="background:rgba(255,255,255,.1);color:rgba(255,255,255,.8);
            font-size:10px;font-weight:600;padding:3px 10px;border-radius:999px">
        ${stateLabel(m.state)}
      </span>
      ${m.days_delay > 0 ? `
        <span style="background:rgba(232,85,85,.2);color:#FCA5A5;
              font-size:10px;font-weight:700;padding:3px 10px;border-radius:999px">
          ⚠ تأخير ${m.days_delay} يوم
        </span>` : `
        <span style="background:rgba(46,204,138,.2);color:#6EE7B7;
              font-size:10px;font-weight:600;padding:3px 10px;border-radius:999px">
          ✓ في الموعد
        </span>`}
      ${m.contractor ? `
        <span style="background:rgba(200,164,84,.15);color:var(--gold-light);
              font-size:10px;padding:3px 10px;border-radius:999px">${m.contractor}</span>` : ''}
    </div>
  </div>
  <!-- Quick stats -->
  <div style="display:flex;gap:20px;flex-shrink:0">
    <div style="text-align:center">
      <div style="font-size:22px;font-weight:800;color:var(--gold)">${pct(m.overall_kpi)}</div>
      <div style="font-size:10px;color:rgba(255,255,255,.4)">KPI الكلي</div>
    </div>
    <div style="text-align:center">
      <div style="font-size:22px;font-weight:800;color:${pendingCerts > 0 ? '#FCA5A5' : '#6EE7B7'}">${pendingCerts}</div>
      <div style="font-size:10px;color:rgba(255,255,255,.4)">مستخلصات معلقة</div>
    </div>
    <div style="text-align:center">
      <div style="font-size:22px;font-weight:800;color:${pendingCOs > 0 ? '#FCD34D' : '#6EE7B7'}">${pendingCOs}</div>
      <div style="font-size:10px;color:rgba(255,255,255,.4)">CO معلق</div>
    </div>
  </div>
</div>

<!-- ── KPI Rings ── -->
<div class="card" style="margin-bottom:14px">
  <div class="card-hdr">
    <div class="card-title">مؤشرات الأداء الرئيسية</div>
    <div style="display:flex;gap:8px">
      <span style="font-size:11px;background:rgba(200,164,84,.1);color:var(--gold);
            padding:2px 10px;border-radius:999px;font-weight:600">
        قيمة العقد: ${fmt(m.contract_value)} ر
      </span>
    </div>
  </div>
  <div class="card-body">
    <div class="kpi-rings">
      <div class="kpi-ring-wrap">
        <canvas id="ring-financial" width="72" height="72"></canvas>
        <div class="kpi-ring-label">مالي (40%)</div>
        <div class="kpi-ring-val" style="color:var(--gold)">${pct(m.financial_kpi)}</div>
      </div>
      <div class="kpi-ring-wrap">
        <canvas id="ring-overall" width="88" height="88"></canvas>
        <div class="kpi-ring-label" style="font-weight:700">KPI الكلي</div>
        <div class="kpi-ring-val" style="font-size:16px;color:var(--teal)">${pct(m.overall_kpi)}</div>
      </div>
      <div class="kpi-ring-wrap">
        <canvas id="ring-time" width="72" height="72"></canvas>
        <div class="kpi-ring-label">زمني (35%)</div>
        <div class="kpi-ring-val" style="color:var(--green)">${pct(m.time_kpi)}</div>
      </div>
      <div class="kpi-ring-wrap">
        <canvas id="ring-visit" width="72" height="72"></canvas>
        <div class="kpi-ring-label">إشرافي (25%)</div>
        <div class="kpi-ring-val" style="color:var(--teal-light)">${pct(m.visit_compliance)}</div>
      </div>
    </div>
  </div>
</div>

<!-- ── Tabs ── -->
<div class="tab-row">
  <button class="tab-btn active" data-tab="tasks">المهام</button>
  <button class="tab-btn" data-tab="financial">
    المالي
    ${pendingCerts > 0 ? `<span class="tab-badge red">${pendingCerts}</span>` : ''}
    ${pendingCOs   > 0 ? `<span class="tab-badge orange">${pendingCOs}</span>` : ''}
  </button>
  <button class="tab-btn" data-tab="boq">جداول الكميات</button>
  <button class="tab-btn" data-tab="visits">الزيارات والحضور</button>
</div>

<!-- ── Tasks ── -->
<div class="tab-panel active" data-tab-panel="tasks">
  <div class="task-list">${buildTasksHTML(data.tasks)}</div>
</div>

<!-- ── Financial ── -->
<div class="tab-panel" data-tab-panel="financial">
  <!-- Summary bar -->
  <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap">
    <div class="fin-kpi-card">
      <div class="fin-kpi-val">${fmt(totalCertVal)} ر</div>
      <div class="fin-kpi-label">إجمالي المستخلصات</div>
    </div>
    <div class="fin-kpi-card">
      <div class="fin-kpi-val" style="color:${pendingCerts > 0 ? 'var(--red)' : 'var(--green)'}">${pendingCerts}</div>
      <div class="fin-kpi-label">بانتظار الاعتماد</div>
    </div>
    <div class="fin-kpi-card">
      <div class="fin-kpi-val" style="color:var(--gold)">${data.change_orders.reduce((s,c) => s + (c.amount||0), 0).toLocaleString('ar-SA')}</div>
      <div class="fin-kpi-label">قيمة أوامر التغيير</div>
    </div>
  </div>

  <div class="section-row">
    <div class="section-title">المستخلصات</div>
    <div class="section-line"></div>
    <div class="section-badge">${data.certs.length}</div>
  </div>
  <div class="cert-list">${buildCertsHTML(data.certs)}</div>

  <div class="section-row" style="margin-top:16px">
    <div class="section-title">أوامر التغيير</div>
    <div class="section-line"></div>
    <div class="section-badge">${data.change_orders.length}</div>
  </div>
  <div class="cert-list">${buildCOHTML(data.change_orders)}</div>
</div>

<!-- ── BOQ ── -->
<div class="tab-panel" data-tab-panel="boq">
  <div style="position:relative;width:100%;height:220px;margin-bottom:16px">
    <canvas id="boq-chart"></canvas>
  </div>
  <table class="boq-table">
    <tr><th>الفئة</th><th>تعاقدي (ر)</th><th>منفذ (ر)</th><th>نسبة</th></tr>
    ${(data.boq_categories || []).map(cat => {
      const pv = cat.contracted > 0 ? Math.round(cat.executed / cat.contracted * 100) : 0;
      return `<tr>
        <td style="font-weight:600">${cat.name}</td>
        <td>${fmt(cat.contracted)}</td>
        <td style="color:var(--teal);font-weight:600">${fmt(cat.executed)}</td>
        <td>
          <div class="boq-bar-wrap"><div class="boq-bar-fill"
            style="width:${pv}%;background:${pv > 90 ? 'var(--orange)' : 'var(--teal)'}"></div></div>
          <span style="font-size:10px;color:var(--text3)">${pv}%</span>
        </td>
      </tr>`;
    }).join('')}
  </table>
</div>

<!-- ── Visits ── -->
<div class="tab-panel" data-tab-panel="visits">
  <div class="section-row">
    <div class="section-title">تقارير الزيارة الميدانية</div>
    <div class="section-line"></div>
    <div class="section-badge">${data.visits.length}</div>
  </div>
  <div class="visit-tl">
    ${data.visits.map((v, i) => `
      <div class="visit-item" style="cursor:pointer"
           onclick="window.showVisitDetail(${JSON.stringify(v).replace(/"/g,'&quot;')})">
        <div class="visit-dot-col">
          <div class="visit-dot" style="background:${v.state === 'approved' ? 'var(--green)' : 'var(--teal)'}"></div>
          ${i < data.visits.length - 1 ? '<div class="visit-line"></div>' : ''}
        </div>
        <div class="visit-body">
          <div class="visit-eng">${v.engineer}</div>
          <div class="visit-meta">${v.date} · ${v.workers} عمال · NCR: ${v.ncr}</div>
          ${v.issues ? `<div style="font-size:10px;color:var(--orange);margin-top:2px">⚠ ${v.issues.substring(0,60)}</div>` : ''}
        </div>
        <div class="visit-dur">${v.photo_count} 📷</div>
      </div>`).join('')}
  </div>

  <div class="section-row" style="margin-top:16px">
    <div class="section-title">سجل الحضور والانصراف</div>
    <div class="section-line"></div>
  </div>
  <div style="overflow-x:auto">
    <table class="boq-table">
      <tr><th>المهندس</th><th>الدخول</th><th>الخروج</th><th>المدة</th><th>حالة</th></tr>
      ${data.attendance.map(a => `
        <tr>
          <td style="font-weight:600">${a.engineer}</td>
          <td style="font-family:monospace">${a.check_in}</td>
          <td style="font-family:monospace;color:var(--text3)">${a.check_out || '—'}</td>
          <td>${a.duration ? Math.round(a.duration * 60) + 'د' : '—'}</td>
          <td><span class="pill ${a.validated ? 'approved' : 'pending'}">${a.validated ? 'موثق' : 'GPS'}</span></td>
        </tr>`).join('')}
    </table>
  </div>
</div>`;
  }

  // ── Tasks HTML ─────────────────────────────────────────────
  function buildTasksHTML(tasks) {
    if (!tasks || !tasks.length)
      return '<div style="text-align:center;padding:24px;color:var(--text3)">لا توجد مهام</div>';
    return tasks.map(t => {
      const dot   = kanbanColor(t.kanban_color);
      const stage = stageStyle(t.kanban_color);
      return `
        <div class="task-row">
          <div class="task-hdr" onclick="toggleTask(this)">
            <div class="task-dot" style="background:${dot}"></div>
            <div class="task-name">${t.name}</div>
            <div class="task-count">${t.approved_count}/${t.subtask_count}</div>
            <span class="task-stage" style="${stage}">${t.stage}</span>
            ${t.blocking_co ? `<span style="font-size:9px;background:rgba(240,165,0,.1);color:#A67800;padding:2px 6px;border-radius:999px">🔒 ${t.blocking_co}</span>` : ''}
            <div class="task-chevron">▾</div>
          </div>
          <div class="subtask-panel">
            ${t.subtasks.map(s => `
              <div class="subtask-item"
                   onclick="window.showSubtaskDetail(${JSON.stringify(s).replace(/"/g,'&quot;')})">
                <div class="sub-dot" style="background:${kanbanColor(s.kanban_color)}"></div>
                <div class="sub-name">${s.name}</div>
                <div class="sub-status" style="color:${kanbanColor(s.kanban_color)}">${reviewStateLabel(s.review_state)}</div>
                ${s.photos?.length ? `<div class="sub-photos">📷${s.photos.length}</div>` : ''}
                ${s.docs?.length   ? `<div class="sub-photos">📄${s.docs.length}</div>` : ''}
              </div>`).join('')}
          </div>
        </div>`;
    }).join('');
  }

  // ── Certs HTML ─────────────────────────────────────────────
  function buildCertsHTML(certs) {
    return certs.map(c => `
      <div class="cert-row" onclick="window.showCertDetailModal(${JSON.stringify(c).replace(/"/g,'&quot;')})">
        <div class="cert-num">مستخلص #${c.number}</div>
        <div class="cert-amount">${fmt(c.total_value)} ر</div>
        <div class="cert-date">${c.period_from} — ${c.period_to}</div>
        <div class="cert-status"><span class="pill ${certPillClass(c.state)}">${certStateLabel(c.state)}</span></div>
        <div class="cert-btns">
          ${c.state === 'consultant_approved' ? `
            <button class="act-btn approve" onclick="event.stopPropagation();approveCert(${c.id},this)">✓ اعتماد</button>
            <button class="act-btn reject"  onclick="event.stopPropagation();rejectCertDlg(${c.id},this)">✗ رفض</button>` : ''}
        </div>
      </div>`).join('');
  }

  // ── CO HTML ────────────────────────────────────────────────
  function buildCOHTML(cos) {
    return cos.map(co => `
      <div class="cert-row" onclick="window.showCODetailModal(${JSON.stringify(co).replace(/"/g,'&quot;')})">
        <div class="cert-num">${co.name}</div>
        <div class="cert-amount">${fmt(co.amount)} ر</div>
        <div class="cert-date">+${co.days_extension} يوم</div>
        <div class="cert-status"><span class="pill ${certPillClass(co.state)}">${certStateLabel(co.state)}</span></div>
        <div class="cert-btns">
          ${co.state === 'review' ? `
            <button class="act-btn approve" onclick="event.stopPropagation();approveCO(${co.id},this)">✓ اعتماد</button>
            <button class="act-btn reject"  onclick="event.stopPropagation();rejectCO(${co.id},this)">✗ رفض</button>` : ''}
        </div>
      </div>`).join('');
  }

  // ══════════════════════════════════════════════════════════
  // CERT DETAIL MODAL
  // ══════════════════════════════════════════════════════════
  window.showCertDetailModal = function(cert) {
    $('modal-cert-title').textContent = `مستخلص #${cert.number}`;
    $('modal-cert-body').innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
        ${[
          ['القيمة الإجمالية',  `${fmt(cert.total_value)} ر`,   'var(--teal)'],
          ['القيمة الصافية',   `${fmt(cert.net_value || cert.total_value)} ر`, 'var(--navy)'],
          ['الفترة من',        cert.period_from,  ''],
          ['الفترة إلى',       cert.period_to,    ''],
        ].map(([label, val, color]) => `
          <div style="background:var(--surface2);border-radius:8px;padding:12px">
            <div style="font-size:10px;color:var(--text3)">${label}</div>
            <div style="font-size:14px;font-weight:700;${color ? 'color:' + color : ''}">${val}</div>
          </div>`).join('')}
      </div>
      <div style="margin-bottom:12px">
        <span class="pill ${certPillClass(cert.state)}" style="font-size:12px;padding:4px 14px">
          ${certStateLabel(cert.state)}
        </span>
      </div>
      ${cert.lines && cert.lines.length ? `
        <div class="section-row"><div class="section-title">بنود المستخلص</div><div class="section-line"></div></div>
        <table class="boq-table">
          <tr><th>الكود</th><th>الوصف</th><th>الكمية</th><th>القيمة</th></tr>
          ${cert.lines.map(l => `
            <tr>
              <td style="font-family:monospace;color:var(--teal);font-weight:600">${l.boq_code}</td>
              <td>${l.desc}</td>
              <td>${l.qty}</td>
              <td>${fmt(l.value)} ر</td>
            </tr>`).join('')}
        </table>` : ''}
      ${cert.state === 'consultant_approved' ? `
        <div style="display:flex;gap:10px;margin-top:16px">
          <button class="act-btn approve" style="flex:1;padding:12px;font-size:13px"
                  onclick="approveCert(${cert.id},this);closeModal('modal-cert')">✓ اعتماد المستخلص</button>
          <button class="act-btn reject"  style="flex:1;padding:12px;font-size:13px"
                  onclick="rejectCertDlg(${cert.id},this);closeModal('modal-cert')">✗ رفض</button>
        </div>` : ''}`;
    openModal('modal-cert');
  };

  // ══════════════════════════════════════════════════════════
  // CO DETAIL MODAL
  // ══════════════════════════════════════════════════════════
  window.showCODetailModal = function(co) {
    $('modal-co-title').textContent = co.name;
    $('modal-co-body').innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
        ${[
          ['قيمة التغيير',   `${fmt(co.amount)} ر`,   'var(--gold)'],
          ['تمديد زمني',     `${co.days_extension} يوم`, 'var(--teal)'],
          ['النوع',          co.type || '—',  ''],
          ['الحالة',         certStateLabel(co.state), ''],
        ].map(([label, val, color]) => `
          <div style="background:var(--surface2);border-radius:8px;padding:12px">
            <div style="font-size:10px;color:var(--text3)">${label}</div>
            <div style="font-size:14px;font-weight:700;${color ? 'color:' + color : ''}">${val}</div>
          </div>`).join('')}
      </div>
      ${co.reason ? `
        <div class="section-row"><div class="section-title">سبب التغيير</div><div class="section-line"></div></div>
        <div style="background:var(--surface2);border-radius:8px;padding:12px;
                    font-size:13px;line-height:1.7;color:var(--text1)">${co.reason}</div>` : ''}
      ${co.state === 'review' ? `
        <div style="display:flex;gap:10px;margin-top:16px">
          <button class="act-btn approve" style="flex:1;padding:12px;font-size:13px"
                  onclick="approveCO(${co.id},this);closeModal('modal-co')">✓ اعتماد</button>
          <button class="act-btn reject"  style="flex:1;padding:12px;font-size:13px"
                  onclick="rejectCO(${co.id},this);closeModal('modal-co')">✗ رفض</button>
        </div>` : ''}`;
    openModal('modal-co');
  };

  // ══════════════════════════════════════════════════════════
  // KPI RINGS
  // ══════════════════════════════════════════════════════════
  function drawRing(id, pctVal, color, size) {
    const c = $(id);
    if (!c) return;
    const ctx = c.getContext('2d');
    const cx = size / 2, r = size * 0.4, lw = size * 0.12;
    ctx.clearRect(0, 0, size, size);
    ctx.lineWidth = lw; ctx.lineCap = 'round';
    ctx.strokeStyle = '#E8EDF2';
    ctx.beginPath(); ctx.arc(cx, cx, r, -Math.PI / 2, Math.PI * 1.5); ctx.stroke();
    ctx.strokeStyle = color;
    ctx.beginPath(); ctx.arc(cx, cx, r, -Math.PI / 2, (pctVal / 100) * Math.PI * 2 - Math.PI / 2); ctx.stroke();
    ctx.fillStyle = '#1B3A52';
    ctx.font = `600 ${Math.round(size * .19)}px IBM Plex Sans Arabic,sans-serif`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(Math.round(pctVal) + '%', cx, cx);
  }
  function drawKpiRings(m) {
    drawRing('ring-financial', m.financial_kpi,    '#C8A454', 72);
    drawRing('ring-overall',   m.overall_kpi,      '#237292', 88);
    drawRing('ring-time',      m.time_kpi,         '#2ECC8A', 72);
    drawRing('ring-visit',     m.visit_compliance, '#2E8FB5', 72);
  }

  // ══════════════════════════════════════════════════════════
  // BOQ CHART
  // ══════════════════════════════════════════════════════════
  function drawBoqChart(cats) {
    const canvas = $('boq-chart');
    if (!canvas || !window.Chart || !cats?.length) return;
    if (window._boqChart) window._boqChart.destroy();
    window._boqChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: cats.map(c => c.name),
        datasets: [
          { label: 'تعاقدي', data: cats.map(c => Math.round(c.contracted)), backgroundColor: 'rgba(27,58,82,.15)', borderRadius: 4 },
          { label: 'منفذ',   data: cats.map(c => Math.round(c.executed)),   backgroundColor: '#237292',            borderRadius: 4 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'top', labels: { font: { size: 11 } } } },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 11 } } },
          y: { grid: { color: 'rgba(0,0,0,.04)' }, ticks: { font: { size: 11 } } },
        },
      },
    });
  }

  // ══════════════════════════════════════════════════════════
  // EVENTS
  // ══════════════════════════════════════════════════════════
  function initMosqueDetailEvents(data) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        const tabId = this.dataset.tab;
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        document.querySelectorAll('.tab-panel').forEach(p =>
          p.classList.toggle('active', p.dataset.tabPanel === tabId));
        if (tabId === 'boq') setTimeout(() => drawBoqChart(data.boq_categories), 50);
      });
    });
  }

  window.toggleTask = function(hdr) {
    const panel   = hdr.nextElementSibling;
    const chevron = hdr.querySelector('.task-chevron');
    const open    = panel.classList.contains('show');
    panel.classList.toggle('show', !open);
    chevron.classList.toggle('open', !open);
  };

  // ══════════════════════════════════════════════════════════
  // SUBTASK + VISIT + LIGHTBOX MODALS
  // ══════════════════════════════════════════════════════════
  window.showSubtaskDetail = function(s) {
    $('modal-subtask-title').textContent = s.name;
    let html = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">
        <div style="width:12px;height:12px;border-radius:50%;background:${kanbanColor(s.kanban_color)}"></div>
        <span style="font-size:12px;font-weight:600">${reviewStateLabel(s.review_state)}</span>
        <span style="font-size:11px;color:var(--text3)">${s.stage}</span>
      </div>`;
    if (s.rejection_note)
      html += `<div style="background:rgba(232,85,85,.08);border:1px solid rgba(232,85,85,.2);
               border-radius:8px;padding:10px 12px;margin-bottom:14px;font-size:12px;color:var(--red)">
               سبب الرفض: ${s.rejection_note}</div>`;
    if (s.photos?.length) {
      html += `<div class="section-row"><div class="section-title">صور الشاهد</div><div class="section-line"></div><div class="section-badge">${s.photos.length}</div></div>`;
      html += `<div class="photo-gallery">` + s.photos.map(ph =>
        `<div class="photo-thumb" onclick="openLightbox('${ph.url}','${ph.name}')">
           <img src="${ph.url}" alt="${ph.name}" loading="lazy"/></div>`).join('') + `</div>`;
    }
    if (s.docs?.length) {
      html += `<div class="section-row" style="margin-top:14px"><div class="section-title">الوثائق</div><div class="section-line"></div></div>`;
      html += `<div class="doc-list">` + s.docs.map(doc =>
        `<a class="doc-item" href="${doc.url}" target="_blank" download>
           <span class="doc-icon">${docIcon(doc.mimetype)}</span>
           <span class="doc-name">${doc.name}</span>
           <span class="doc-type">${(doc.mimetype.split('/')[1] || 'FILE').toUpperCase()}</span>
         </a>`).join('') + `</div>`;
    }
    $('modal-subtask-body').innerHTML = html;
    openModal('modal-subtask');
  };

  window.openLightbox = function(url, name) {
    $('lightbox-img').src = url;
    $('lightbox-caption').textContent = name;
    openModal('modal-lightbox');
  };
  window.open360Viewer = function(url, name) {
  // نستخدم Pannellum CDN
  if (!document.getElementById('pannellum-css')) {
    const css = document.createElement('link');
    css.id   = 'pannellum-css';
    css.rel  = 'stylesheet';
    css.href = 'https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.css';
    document.head.appendChild(css);
  }
  if (!window.pannellum) {
    const s = document.createElement('script');
    s.src   = 'https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.js';
    s.onload = () => _show360(url, name);
    document.head.appendChild(s);
    return;
  }
  _show360(url, name);
};

  function _show360(url, name) {
  // Modal 360
  let modal = document.getElementById('modal-360');
  if (!modal) {
    modal = document.createElement('div');
    modal.id        = 'modal-360';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal" style="max-width:900px;padding:0;overflow:hidden">
        <div class="modal-hdr" style="position:absolute;top:0;right:0;left:0;z-index:10;
             background:rgba(0,0,0,.5);border:none">
          <div class="modal-title" id="360-title" style="color:#fff"></div>
          <button class="modal-close" style="color:#fff"
                  onclick="document.getElementById('modal-360').classList.remove('show');
                           document.getElementById('viewer-360').innerHTML=''">✕</button>
        </div>
        <div id="viewer-360" style="width:100%;height:500px"></div>
      </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', function(e) {
      if (e.target === this) {
        this.classList.remove('show');
        document.getElementById('viewer-360').innerHTML = '';
      }
    });
  }

  document.getElementById('360-title').textContent = name || 'عرض 360°';
  document.getElementById('viewer-360').innerHTML   = '';
  modal.classList.add('show');

  pannellum.viewer('viewer-360', {
    type:        'equirectangular',
    panorama:    url,
    autoLoad:    true,
    autoRotate:  -2,
    compass:     false,
    showControls: true,
    hfov:        100,
  });
}
  window.showVisitDetail = function(v) {
  $('modal-visit-title').textContent = `تقرير زيارة — ${v.date}`;

  // Photos HTML
  const photos = v.photos || [];
  const photosHTML = photos.length ? `
    <div style="font-size:11px;font-weight:600;color:var(--text2);margin:12px 0 8px">
      الصور (${photos.length})
    </div>
    <div class="photo-gallery">
      ${photos.map(ph => ph.is_360 ? `
        <div style="position:relative;border-radius:10px;overflow:hidden;cursor:pointer;grid-column:span 3"
             onclick="open360Viewer('${ph.url}','${ph.name}')">
          <img src="${ph.url}" style="width:100%;height:160px;object-fit:cover;filter:blur(1px)"/>
          <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
                      background:rgba(0,0,0,.35)">
            <div style="background:rgba(255,255,255,.9);border-radius:999px;padding:8px 16px;
                        font-size:12px;font-weight:700;color:#1B3A52">
              🔮 صورة 360° — اضغط للعرض
            </div>
          </div>
        </div>` : `
        <div class="photo-thumb" onclick="openLightbox('${ph.url}','${ph.name}')">
          <img src="${ph.url}" alt="${ph.name}" loading="lazy"
               style="width:100%;height:100%;object-fit:cover"/>
        </div>`
      ).join('')}
    </div>` : '';

  $('modal-visit-body').innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px">
      ${[['المهندس', v.engineer, ''], ['العمال', v.workers, ''],
         ['تقارير NCR', v.ncr, v.ncr > 0 ? 'var(--red)' : 'var(--green)'],
         ['الصور', `${v.photo_count} 📷`, '']].map(([l, val, c]) => `
        <div style="background:var(--surface2);border-radius:8px;padding:10px 12px">
          <div style="font-size:10px;color:var(--text3)">${l}</div>
          <div style="font-size:13px;font-weight:700;${c ? 'color:' + c : ''}">${val}</div>
        </div>`).join('')}
    </div>
    ${v.activities ? `
      <div style="font-size:11px;font-weight:600;color:var(--text2);margin-bottom:5px">الأعمال المنجزة</div>
      <div style="font-size:12px;line-height:1.7;background:var(--surface2);border-radius:8px;
                  padding:10px 12px;margin-bottom:10px">${v.activities}</div>` : ''}
    ${v.issues ? `
      <div style="font-size:11px;font-weight:600;color:var(--orange);margin-bottom:5px">المشكلات</div>
      <div style="font-size:12px;line-height:1.7;background:rgba(240,165,0,.05);
                  border:1px solid rgba(240,165,0,.2);border-radius:8px;
                  padding:10px 12px">${v.issues}</div>` : ''}
    ${photosHTML}`;

  openModal('modal-visit');
};

  // ══════════════════════════════════════════════════════════
  // CERT & CO ACTIONS
  // ══════════════════════════════════════════════════════════
  window.approveCert = async function(id, btn) {
    btn.disabled = true; btn.textContent = '...';
    const res = await apiPost(`/dashboard/api/cert/${id}/approve`, {});
    if (res?.ok) btn.closest('.cert-row')?.querySelector('.cert-status')
      ?.replaceChildren(Object.assign(document.createElement('span'), { className: 'pill approved', textContent: '✓ معتمد' }));
    btn.closest('.cert-btns').innerHTML = '';
  };
  window.rejectCertDlg = function(id, btn) {
    const reason = prompt('سبب الرفض:');
    if (!reason) return;
    apiPost(`/dashboard/api/cert/${id}/reject`, { reason }).then(res => {
      if (res?.ok) btn.closest('.cert-row')?.querySelector('.cert-status')
        ?.replaceChildren(Object.assign(document.createElement('span'), { className: 'pill rejected', textContent: '✗ مرفوض' }));
      btn.closest('.cert-btns').innerHTML = '';
    });
  };
  window.approveCO = async function(id, btn) {
    btn.disabled = true; btn.textContent = '...';
    const res = await apiPost(`/dashboard/api/co/${id}/approve`, {});
    if (res?.ok) btn.closest('.cert-row')?.querySelector('.cert-status')
      ?.replaceChildren(Object.assign(document.createElement('span'), { className: 'pill approved', textContent: '✓ معتمد' }));
    btn.closest('.cert-btns').innerHTML = '';
  };
  window.rejectCO = async function(id, btn) {
    btn.disabled = true; btn.textContent = '...';
    await apiPost(`/dashboard/api/co/${id}/reject`, {});
    btn.closest('.cert-btns').innerHTML = '';
  };

  // ══════════════════════════════════════════════════════════
  // ON-SITE
  // ══════════════════════════════════════════════════════════
  async function loadOnSite() {
    const data = await apiGet('/dashboard/api/onsite');
    const pill = $('onsite-pill');
    if (pill) pill.querySelector('span:last-child').textContent = `${data.length} في الموقع`;
    const list = $('onsite-list');
    if (!list) return;
    list.innerHTML = data.length
      ? data.map(p => `
          <div class="onsite-item">
            <div class="onsite-avatar">${(p.name || 'م')[0]}</div>
            <div>
              <div class="onsite-name">${p.name}</div>
              <div class="onsite-mosque">${p.mosque} · ${p.code}</div>
            </div>
            <div class="onsite-time">منذ ${p.checkin}</div>
          </div>`).join('')
      : `<div style="text-align:center;padding:20px;color:var(--text3);font-size:12px">لا يوجد مستشارون في المواقع حالياً</div>`;
  }

  // ══════════════════════════════════════════════════════════
  // LIVE STREAM
  // ══════════════════════════════════════════════════════════
  async function checkLiveStream() {
    const data = await apiGet('/dashboard/api/stream');
    const pill = $('live-pill');
    if (!pill) return;
    if (data?.id) {
      pill.style.display = 'flex';
      pill.onclick = () => openLiveStream(data);
    } else { pill.style.display = 'none'; }
  }
  function openLiveStream(data) {
    $('stream-modal-title').textContent = data.name || 'بث مباشر';
    $('stream-embed').innerHTML =
      `<iframe src="${data.url}" allowfullscreen allow="camera;microphone"></iframe>`;
    openModal('modal-stream');
  }

  // ══════════════════════════════════════════════════════════
  // CHATBOT
  // ══════════════════════════════════════════════════════════
  const chatFab   = $('chatbot-fab');
  const chatPanel = $('chatbot-panel');
  const chatMsgs  = $('chat-msgs');
  const chatInput = $('chat-input');
  chatFab?.addEventListener('click', () => {
    chatPanel.classList.toggle('open');
    if (chatPanel.classList.contains('open')) chatInput?.focus();
  });
  $('chat-close')?.addEventListener('click', () => chatPanel.classList.remove('open'));

  async function sendChat(msg) {
    if (!msg.trim()) return;
    chatInput.value = '';
    appendMsg('user', msg);
    state.chatHistory.push({ role: 'user', content: msg });
    const thinking = appendMsg('bot', '...');
    const res = await apiPost('/dashboard/api/chat', {
      message: msg, mosque_context: state.mosqueContext,
      history: state.chatHistory.slice(-8),
    });
    thinking.textContent = res?.reply || 'تعذر الحصول على رد.';
    state.chatHistory.push({ role: 'assistant', content: res?.reply || '' });
    chatMsgs.scrollTop = chatMsgs.scrollHeight;
  }
  function appendMsg(role, text) {
    const d = document.createElement('div');
    d.className = `chat-msg ${role}`;
    d.textContent = text;
    chatMsgs.appendChild(d);
    chatMsgs.scrollTop = chatMsgs.scrollHeight;
    return d;
  }
  $('chat-send')?.addEventListener('click', () => sendChat(chatInput.value));
  chatInput?.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(chatInput.value); }
  });
  document.querySelectorAll('.chat-sug').forEach(btn =>
    btn.addEventListener('click', function () {
      sendChat(this.textContent);
      chatPanel.classList.add('open');
    }));

  // ══════════════════════════════════════════════════════════
  // MODALS
  // ══════════════════════════════════════════════════════════
  function openModal(id) {
    document.getElementById(id)?.classList.add('show');
  }
  window.closeModal = function(id) {
    document.getElementById(id)?.classList.remove('show');
    if (id === 'modal-stream') $('stream-embed').innerHTML = '';
    if (id === 'modal-lightbox') $('lightbox-img').src = '';
  };
  document.querySelectorAll('.modal-overlay').forEach(o =>
    o.addEventListener('click', function(e) {
      if (e.target === this) {
        const id = this.id;
        window.closeModal(id);
      }
    }));

  // ══════════════════════════════════════════════════════════
  // AUTO REFRESH
  // ══════════════════════════════════════════════════════════
  function startRefresh() {
    const interval = (state.config.refresh_interval || 60) * 1000;
    state.refreshTimer = setInterval(() => {
      loadOnSite();
      checkLiveStream();
      if (state.activeMosqueId) loadMosqueDetail(state.activeMosqueId);
    }, interval);
  }

  // ══════════════════════════════════════════════════════════
  // HELPERS
  // ══════════════════════════════════════════════════════════
  function kanbanColor(c) {
    return { green:'#2ECC8A', red:'#E85555', yellow:'#F0A500', orange:'#F0A500', grey:'#8FA3B3' }[c] || '#8FA3B3';
  }
  function dotColor(kpi) {
    return kpi >= 70 ? '#2ECC8A' : kpi >= 50 ? '#F0A500' : kpi > 0 ? '#E85555' : '#C8D4DC';
  }
  function colorClass(kpi) {
    return kpi >= 70 ? 'ok' : kpi >= 50 ? 'warn' : kpi > 0 ? 'err' : '';
  }
  function stageStyle(color) {
    const m = { green:'background:rgba(46,204,138,.12);color:#1A7A55', red:'background:rgba(232,85,85,.1);color:#A33', yellow:'background:rgba(240,165,0,.1);color:#A67800', grey:'background:var(--surface2);color:var(--text3)' };
    return m[color] || m.grey;
  }
  function reviewStateLabel(s) {
    return { pending:'لم يبدأ', submitted:'بانتظار الاستشاري', approved:'✓ معتمد', rejected:'✗ مرفوض', blocked:'🔒 مجمّد' }[s] || s;
  }
  function certPillClass(s) {
    return { draft:'pending', submitted:'pending', consultant_review:'pending', consultant_approved:'review', approved:'approved', rejected:'rejected', review:'pending', paid:'approved' }[s] || 'pending';
  }
  function certStateLabel(s) {
    return { draft:'مسودة', submitted:'بانتظار الاستشاري', consultant_review:'مراجعة الاستشاري', consultant_approved:'بانتظار الوقف', approved:'معتمد', rejected:'مرفوض', review:'قيد المراجعة', paid:'مدفوع' }[s] || s;
  }
  function stateLabel(s) {
    return { draft:'لم يبدأ', mobilizing:'التجهيز', active:'قيد التنفيذ', initial_hov:'استلام ابتدائي', final_hov:'استلام نهائي', warranty:'ضمان', closed:'مغلق' }[s] || s;
  }
  function docIcon(mime) {
    if (mime?.includes('pdf'))   return '📄';
    if (mime?.includes('word') || mime?.includes('docx')) return '📝';
    if (mime?.includes('sheet') || mime?.includes('xlsx')) return '📊';
    if (mime?.includes('zip'))   return '🗜';
    return '📁';
  }
  function truncate(str, n) {
    return str && str.length > n ? str.substring(0, n) + '…' : str;
  }

  // ── Load Chart.js then init ────────────────────────────────
  function loadChartJS(cb) {
    if (window.Chart) { cb(); return; }
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js';
    s.onload = cb;
    document.head.appendChild(s);
  }
  loadChartJS(init);
});
