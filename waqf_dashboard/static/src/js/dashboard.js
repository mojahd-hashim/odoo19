/* ═══════════════════════════════════════════════════════════
   Waqf Executive Dashboard — Main JS
   ═══════════════════════════════════════════════════════════ */
'use strict';

document.addEventListener('DOMContentLoaded', function () {

  // ── State ──────────────────────────────────────────────────
  const state = {
    activeMosqueId:   null,
    packages:         [],
    mosques:          [],
    chatHistory:      [],
    mosqueContext:    null,
    refreshTimer:     null,
    config:           window.WAQF_DASH_CONFIG || {},
  };

  // ── Utility ────────────────────────────────────────────────
  const $ = id => document.getElementById(id);
  const fmt = n => new Intl.NumberFormat('ar-SA').format(Math.round(n));
  const pct = n => Math.round(n) + '%';

  async function apiGet(url) {
    const r = await fetch(url, { credentials: 'same-origin' });
    return r.json();
  }

  async function apiPost(url, data) {
    const r = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken':  document.cookie.match(/csrf_token=([^;]+)/)?.[1] || '',
      },
      body: JSON.stringify({ jsonrpc:'2.0', method:'call', params: data }),
    });
    const json = await r.json();
    return json.result;
  }

  // ══════════════════════════════════════════════════════════
  // INIT
  // ══════════════════════════════════════════════════════════
  async function init() {
    await Promise.all([loadSummary(), loadPackages(), loadMosques()]);
    buildHeatmap();
    buildGantt();
    loadOnSite();
    checkLiveStream();
    startRefresh();
  }

  // ══════════════════════════════════════════════════════════
  // SUMMARY KPIs
  // ══════════════════════════════════════════════════════════
  async function loadSummary() {
    const d = await apiGet('/dashboard/api/summary');
    $('kpi-total-value').textContent   = fmt(d.total_contract_value);
    $('kpi-avg-kpi').textContent       = pct(d.avg_kpi);
    $('kpi-delayed').textContent       = d.delayed_mosques;
    $('kpi-pending-cert').textContent  = d.pending_certs;
    $('kpi-financial-pct').textContent = pct(d.financial_pct);
  }

  // ══════════════════════════════════════════════════════════
  // PACKAGES + GANTT
  // ══════════════════════════════════════════════════════════
  async function loadPackages() {
    const pkgs = await apiGet('/dashboard/api/packages');
    state.packages = pkgs;
    buildSidebar(pkgs);
    buildGantt();
  }

  function buildSidebar(pkgs) {
    const container = $('sb-packages');
    if (!container) return;
    container.innerHTML = '';

    pkgs.forEach(pkg => {
      const div = document.createElement('div');
      div.className = 'sb-pkg';
      div.innerHTML = `
        <div class="sb-pkg-hdr" data-pkg="${pkg.id}">
          <span>${pkg.name}</span>
          <span class="sb-pkg-badge">${pkg.mosque_count}</span>
          <span class="sb-pkg-arrow">›</span>
        </div>
        <div class="sb-pkg-mosques" id="pkg-mosques-${pkg.id}" style="display:none">
          ${pkg.mosques.map(m => `
            <div class="sb-mosque ${colorClass(m.overall_kpi)}" data-id="${m.id}">
              <div class="sb-mosque-dot" style="background:${dotColor(m.overall_kpi)}"></div>
              <span>${truncate(m.name, 16)}</span>
              <span class="sb-mosque-code">${m.code}</span>
            </div>
          `).join('')}
        </div>
      `;
      container.appendChild(div);

      // Package toggle
      div.querySelector('.sb-pkg-hdr').addEventListener('click', function () {
        const mosques = div.querySelector('.sb-pkg-mosques');
        const open = mosques.style.display !== 'none';
        mosques.style.display = open ? 'none' : '';
        this.classList.toggle('open', !open);
      });

      // Mosque click
      div.querySelectorAll('.sb-mosque').forEach(el => {
        el.addEventListener('click', function () {
          document.querySelectorAll('.sb-mosque').forEach(m => m.classList.remove('active'));
          this.classList.add('active');
          loadMosqueDetail(parseInt(this.dataset.id));
        });
      });
    });

    // Open first package by default
    if (pkgs.length) {
      const firstHdr = container.querySelector('.sb-pkg-hdr');
      if (firstHdr) firstHdr.click();
    }
  }

  // ══════════════════════════════════════════════════════════
  // MOSQUES
  // ══════════════════════════════════════════════════════════
  async function loadMosques() {
    const mosques = await apiGet('/dashboard/api/mosques');
    state.mosques = mosques;
    buildHeatmap();
  }

  // ══════════════════════════════════════════════════════════
  // HEATMAP
  // ══════════════════════════════════════════════════════════
  function buildHeatmap() {
    const el = $('heatmap-grid');
    if (!el || !state.mosques.length) return;
    el.innerHTML = '';

    state.mosques.forEach(m => {
      const cell = document.createElement('div');
      cell.className = `hm-cell ${m.kpi_color}`;
      cell.dataset.id = m.id;

      // Short label
      const code = m.code || '';
      const label = code.replace(/^(RUH|JED|TIF|RFH|AFJ|YRA|GIZ)-/, '');
      cell.textContent = label;

      // Tooltip
      const tip = document.createElement('div');
      tip.className = 'hm-tooltip';
      tip.textContent = `${m.code} · ${m.overall_kpi}%`;
      cell.appendChild(tip);

      cell.addEventListener('click', function () {
        document.querySelectorAll('.hm-cell').forEach(c => c.classList.remove('active'));
        this.classList.add('active');
        loadMosqueDetail(parseInt(this.dataset.id));

        // Sync sidebar
        document.querySelectorAll('.sb-mosque').forEach(s => {
          s.classList.toggle('active', parseInt(s.dataset.id) === m.id);
        });
      });

      el.appendChild(cell);
    });
  }

  // ══════════════════════════════════════════════════════════
  // GANTT CHART
  // ══════════════════════════════════════════════════════════
  function buildGantt() {
    const el = $('gantt-rows');
    const monthsEl = $('gantt-months');
    if (!el || !state.packages.length) return;

    // Date range
    const projectStart = new Date('2026-04-01');
    const projectEnd   = new Date('2027-04-01');
    const totalMs = projectEnd - projectStart;
    const today = new Date();

    // Months header
    if (monthsEl) {
      monthsEl.innerHTML = '';
      const months = ['أبر','مايو','يون','يول','أغس','سبت','أكت','نوف','ديس','يناير','فبر','مارس'];
      months.forEach(m => {
        const d = document.createElement('div');
        d.className = 'gantt-month';
        d.textContent = m;
        monthsEl.appendChild(d);
      });
    }

    el.innerHTML = '';

    const colors = ['#237292','#2ECC8A','#C8A454','#F0A500'];

    state.packages.forEach((pkg, i) => {
      if (!pkg.planned_start || !pkg.planned_end) return;
      const start = new Date(pkg.planned_start);
      const end   = new Date(pkg.planned_end);

      const leftPct  = Math.max(0, (start - projectStart) / totalMs * 100);
      const widthPct = Math.min(100 - leftPct, (end - start) / totalMs * 100);
      const todayPct = Math.min(100, (today - projectStart) / totalMs * 100);

      const row = document.createElement('div');
      row.className = 'gantt-row';
      row.innerHTML = `
        <div class="gantt-label" title="${pkg.name}">${pkg.code} — ${pkg.mosque_count}م</div>
        <div class="gantt-track" style="position:relative">
          <div class="gantt-bar" style="right:${leftPct}%;width:${widthPct}%;background:${colors[i % 4]}">
            <span class="gantt-bar-label">KPI ${pkg.avg_kpi}%</span>
          </div>
          <div class="gantt-today" style="right:${todayPct}%">
            <div class="gantt-today-label">اليوم</div>
          </div>
          <div class="gantt-popup" id="gantt-popup-${pkg.id}">
            <div class="gantt-popup-title">${pkg.name}</div>
            <div class="gantt-popup-row">
              <span class="gantt-popup-label">KPI الحالي</span>
              <span class="gantt-popup-val">${pkg.avg_kpi}%</span>
            </div>
            <div class="gantt-popup-row">
              <span class="gantt-popup-label">الإنجاز الزمني</span>
              <span class="gantt-popup-val">${pkg.avg_time}%</span>
            </div>
            <div class="gantt-popup-row">
              <span class="gantt-popup-label">المتوقع الآن</span>
              <span class="gantt-popup-val">${pkg.expected_pct}%</span>
            </div>
            <div class="gantt-popup-row">
              <span class="gantt-popup-label">الانحراف</span>
              <span class="gantt-popup-dev ${pkg.deviation >= 0 ? 'ahead' : 'behind'}">
                ${pkg.deviation >= 0 ? '+' : ''}${pkg.deviation}%
              </span>
            </div>
            <div class="gantt-popup-row">
              <span class="gantt-popup-label">مساجد متأخرة</span>
              <span class="gantt-popup-val" style="color:${pkg.delayed_count > 0 ? 'var(--red)' : 'var(--green)'}">
                ${pkg.delayed_count}
              </span>
            </div>
          </div>
        </div>
      `;
      el.appendChild(row);

      // Gantt click → popup
      const track = row.querySelector('.gantt-track');
      const popup  = row.querySelector('.gantt-popup');
      track.addEventListener('click', function (e) {
        e.stopPropagation();
        document.querySelectorAll('.gantt-popup').forEach(p => p !== popup && p.classList.remove('show'));
        popup.classList.toggle('show');
      });
    });

    document.addEventListener('click', () => {
      document.querySelectorAll('.gantt-popup').forEach(p => p.classList.remove('show'));
    });
  }

  // ══════════════════════════════════════════════════════════
  // MOSQUE DETAIL
  // ══════════════════════════════════════════════════════════
  async function loadMosqueDetail(mosqueId) {
    state.activeMosqueId = mosqueId;
    showSection('section-mosque');

    // Topbar update
    const mosque = state.mosques.find(m => m.id === mosqueId);
    if (mosque) {
      $('topbar-title').textContent = mosque.name;
      $('topbar-sub').textContent   = `${mosque.code} · ${mosque.package} · ${stateLabel(mosque.state)}`;
      if (mosque.days_delay > 0) {
        $('topbar-sub').textContent += ` · تأخير ${mosque.days_delay} يوم`;
      }
    }

    // Loading state
    $('mosque-detail-content').innerHTML = `
      <div style="padding:40px;text-align:center">
        <div class="loading-spinner" style="width:32px;height:32px;margin:0 auto"></div>
        <div style="margin-top:12px;color:var(--text3);font-size:12px">جاري تحميل بيانات المسجد...</div>
      </div>
    `;

    const data = await apiGet(`/dashboard/api/mosque/${mosqueId}`);
    if (!data.mosque) return;

    const m = data.mosque;
    state.mosqueContext = {
      name:         m.name,
      overall_kpi:  m.overall_kpi,
      financial_pct:m.financial_kpi,
      time_pct:     m.time_kpi,
      days_delay:   m.days_delay,
      pending_certs: data.certs.filter(c => ['submitted','consultant_approved'].includes(c.state)).length,
    };

    $('mosque-detail-content').innerHTML = buildMosqueDetailHTML(data);
    initMosqueDetailEvents(data);
    drawKpiRings(m);
    drawBoqChart(data.boq_categories);
  }

  function buildMosqueDetailHTML(data) {
    const m = data.mosque;
    return `
      <!-- KPI Rings -->
      <div class="card" style="margin-bottom:14px">
        <div class="card-hdr">
          <div class="card-title">مؤشرات الأداء الرئيسية</div>
          <span style="font-size:11px;color:var(--text3)">${m.days_delay > 0 ? `<span style="color:var(--red)">تأخير ${m.days_delay} يوم</span>` : '<span style="color:var(--green)">في الموعد</span>'}</span>
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

      <!-- Tabs -->
      <div class="tab-row">
        <button class="tab-btn active" data-tab="tasks">المهام</button>
        <button class="tab-btn" data-tab="financial">المالي</button>
        <button class="tab-btn" data-tab="boq">جداول الكميات</button>
        <button class="tab-btn" data-tab="visits">الزيارات والحضور</button>
      </div>

      <!-- Tab: Tasks -->
      <div class="tab-panel active" data-tab-panel="tasks">
        <div class="task-list" id="task-list">
          ${buildTasksHTML(data.tasks)}
        </div>
      </div>

      <!-- Tab: Financial -->
      <div class="tab-panel" data-tab-panel="financial">
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

      <!-- Tab: BOQ -->
      <div class="tab-panel" data-tab-panel="boq">
        <div style="position:relative;width:100%;height:220px;margin-bottom:16px">
          <canvas id="boq-chart" role="img" aria-label="BOQ consumption chart"></canvas>
        </div>
        <table class="boq-table">
          <tr>
            <th>الفئة</th><th>تعاقدي (ر)</th><th>منفذ (ر)</th><th>نسبة</th>
          </tr>
          ${(data.boq_categories || []).map(cat => {
            const pctVal = cat.contracted > 0 ? Math.round(cat.executed / cat.contracted * 100) : 0;
            return `<tr>
              <td style="font-weight:600">${cat.name}</td>
              <td>${fmt(cat.contracted)}</td>
              <td style="color:var(--teal);font-weight:600">${fmt(cat.executed)}</td>
              <td>
                <div class="boq-bar-wrap">
                  <div class="boq-bar-fill" style="width:${pctVal}%;background:${pctVal > 90 ? 'var(--orange)' : 'var(--teal)'}"></div>
                </div>
                <span style="font-size:10px;color:var(--text3)">${pctVal}%</span>
              </td>
            </tr>`;
          }).join('')}
        </table>
      </div>

      <!-- Tab: Visits -->
      <div class="tab-panel" data-tab-panel="visits">
        <div class="section-row">
          <div class="section-title">تقارير الزيارة الميدانية</div>
          <div class="section-line"></div>
          <div class="section-badge">${data.visits.length}</div>
        </div>
        <div class="visit-tl">
          ${data.visits.map((v, i) => `
            <div class="visit-item" style="cursor:pointer" data-visit="${v.id}" onclick="window.showVisitDetail(${JSON.stringify(v).replace(/"/g,'&quot;')})">
              <div class="visit-dot-col">
                <div class="visit-dot" style="background:${v.state==='approved'?'var(--green)':'var(--teal)'}"></div>
                ${i < data.visits.length-1 ? '<div class="visit-line"></div>' : ''}
              </div>
              <div class="visit-body">
                <div class="visit-eng">${v.engineer}</div>
                <div class="visit-meta">${v.date} · ${v.workers} عمال · NCR: ${v.ncr}</div>
                ${v.issues ? `<div style="font-size:10px;color:var(--orange);margin-top:2px">⚠ ${v.issues.substring(0,60)}</div>` : ''}
              </div>
              <div class="visit-dur">${v.photo_count} 📷</div>
            </div>
          `).join('')}
        </div>

        <div class="section-row" style="margin-top:16px">
          <div class="section-title">سجل الحضور والانصراف (30 يوم)</div>
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
                <td>${a.duration ? Math.round(a.duration*60)+'د' : '—'}</td>
                <td><span class="pill ${a.validated ? 'approved' : 'pending'}">${a.validated ? 'موثق' : 'GPS'}</span></td>
              </tr>
            `).join('')}
          </table>
        </div>
      </div>
    `;
  }

  function buildTasksHTML(tasks) {
    return tasks.map(t => {
      const dotColor = kanbanColor(t.kanban_color);
      const stageClass = stageStyle(t.kanban_color);
      return `
        <div class="task-row">
          <div class="task-hdr" onclick="toggleTask(this)">
            <div class="task-dot" style="background:${dotColor}"></div>
            <div class="task-name">${t.name}</div>
            <div class="task-count">${t.approved_count}/${t.subtask_count}</div>
            <span class="task-stage" style="${stageClass}">${t.stage}</span>
            ${t.blocking_co ? `<span style="font-size:9px;background:rgba(240,165,0,.1);color:#A67800;padding:2px 6px;border-radius:999px">🔒 ${t.blocking_co}</span>` : ''}
            <div class="task-chevron">▾</div>
          </div>
          <div class="subtask-panel" id="sub-${t.id}">
            ${t.subtasks.map(s => `
              <div class="subtask-item" onclick="window.showSubtaskDetail(${JSON.stringify(s).replace(/"/g,'&quot;')})">
                <div class="sub-dot" style="background:${kanbanColor(s.kanban_color)}"></div>
                <div class="sub-name">${s.name}</div>
                <div class="sub-status" style="color:${kanbanColor(s.kanban_color)}">${reviewStateLabel(s.review_state)}</div>
                ${s.photos.length ? `<div class="sub-photos">📷${s.photos.length}</div>` : ''}
                ${s.docs.length   ? `<div class="sub-photos" style="margin-right:4px">📄${s.docs.length}</div>` : ''}
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }).join('');
  }

  function buildCertsHTML(certs) {
    return certs.map(c => `
      <div class="cert-row" onclick="showCertDetail(${c.id})">
        <div class="cert-num">مستخلص #${c.number}</div>
        <div class="cert-amount">${fmt(c.total_value)} ر</div>
        <div class="cert-date">${c.period_from} — ${c.period_to}</div>
        <div class="cert-status"><span class="pill ${certPillClass(c.state)}">${certStateLabel(c.state)}</span></div>
        <div class="cert-btns">
          ${c.state === 'consultant_approved' ? `
            <button class="act-btn approve" onclick="event.stopPropagation();approveCert(${c.id},this)">✓ اعتماد</button>
            <button class="act-btn reject"  onclick="event.stopPropagation();rejectCertDlg(${c.id},this)">✗ رفض</button>
          ` : ''}
        </div>
      </div>
    `).join('');
  }

  function buildCOHTML(cos) {
    return cos.map(co => `
      <div class="cert-row" onclick="showCODetail(${co.id})">
        <div class="cert-num">${co.name}</div>
        <div class="cert-amount">${fmt(co.amount)} ر</div>
        <div class="cert-date">+${co.days_extension} يوم</div>
        <div class="cert-status"><span class="pill ${certPillClass(co.state)}">${certStateLabel(co.state)}</span></div>
        <div class="cert-btns">
          ${co.state === 'review' ? `
            <button class="act-btn approve" onclick="event.stopPropagation();approveCO(${co.id},this)">✓ اعتماد</button>
            <button class="act-btn reject"  onclick="event.stopPropagation();rejectCO(${co.id},this)">✗ رفض</button>
          ` : ''}
        </div>
      </div>
    `).join('');
  }

  // ══════════════════════════════════════════════════════════
  // KPI RINGS
  // ══════════════════════════════════════════════════════════
  function drawRing(id, pctVal, color, size) {
    const c = $(id);
    if (!c) return;
    const ctx = c.getContext('2d');
    const cx = size/2, r = size*0.4, lw = size*0.12;
    ctx.clearRect(0,0,size,size);
    ctx.lineWidth = lw; ctx.lineCap = 'round';
    ctx.strokeStyle = '#E8EDF2';
    ctx.beginPath(); ctx.arc(cx,cx,r,-Math.PI/2,Math.PI*2-Math.PI/2); ctx.stroke();
    ctx.strokeStyle = color;
    ctx.beginPath(); ctx.arc(cx,cx,r,-Math.PI/2,(pctVal/100)*Math.PI*2-Math.PI/2); ctx.stroke();
    ctx.fillStyle = '#1B3A52';
    ctx.font = `600 ${Math.round(size*.19)}px IBM Plex Sans Arabic,sans-serif`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(Math.round(pctVal)+'%', cx, cx);
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
    if (!canvas || !window.Chart || !cats || !cats.length) return;

    if (window._boqChart) window._boqChart.destroy();

    const labels  = cats.map(c => c.name);
    const contracted = cats.map(c => Math.round(c.contracted));
    const executed   = cats.map(c => Math.round(c.executed));

    window._boqChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'تعاقدي', data: contracted, backgroundColor: 'rgba(27,58,82,.15)', borderRadius: 4 },
          { label: 'منفذ',   data: executed,   backgroundColor: '#237292',            borderRadius: 4 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: true, position: 'top', labels: { font: { size: 11 } } } },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 11 } } },
          y: { grid: { color: 'rgba(0,0,0,.04)' }, ticks: { font: { size: 11 } } },
        },
      },
    });
  }

  // ══════════════════════════════════════════════════════════
  // TASK EVENTS
  // ══════════════════════════════════════════════════════════
  function initMosqueDetailEvents(data) {
    // Tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        const tabId = this.dataset.tab;
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        document.querySelectorAll('.tab-panel').forEach(p => {
          p.classList.toggle('active', p.dataset.tabPanel === tabId);
        });
        if (tabId === 'boq') drawBoqChart(data.boq_categories);
      });
    });
  }

  // Global task toggle
  window.toggleTask = function(hdr) {
    const panel   = hdr.nextElementSibling;
    const chevron = hdr.querySelector('.task-chevron');
    const open    = panel.classList.contains('show');
    panel.classList.toggle('show', !open);
    chevron.classList.toggle('open', !open);
  };

  // ══════════════════════════════════════════════════════════
  // SUBTASK DETAIL MODAL
  // ══════════════════════════════════════════════════════════
  window.showSubtaskDetail = function(subtask) {
    const modal = $('modal-subtask');
    $('modal-subtask-title').textContent = subtask.name;

    let html = '';

    // Status
    html += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">
      <div style="width:12px;height:12px;border-radius:50%;background:${kanbanColor(subtask.kanban_color)}"></div>
      <span style="font-size:12px;font-weight:600">${reviewStateLabel(subtask.review_state)}</span>
      <span style="font-size:11px;color:var(--text3)">${subtask.stage}</span>
    </div>`;

    if (subtask.rejection_note) {
      html += `<div style="background:rgba(232,85,85,.08);border:1px solid rgba(232,85,85,.2);border-radius:8px;padding:10px 12px;margin-bottom:14px;font-size:12px;color:var(--red)">
        سبب الرفض: ${subtask.rejection_note}
      </div>`;
    }

    // Photos gallery
    if (subtask.photos && subtask.photos.length) {
      html += `<div class="section-row"><div class="section-title">صور الشاهد</div><div class="section-line"></div><div class="section-badge">${subtask.photos.length}</div></div>`;
      html += `<div class="photo-gallery">`;
      subtask.photos.forEach((ph, idx) => {
        html += `<div class="photo-thumb" onclick="openLightbox('${ph.url}','${ph.name}')">
          <img src="${ph.url}" alt="${ph.name}" loading="lazy"/>
        </div>`;
      });
      html += `</div>`;
    }

    // Documents
    if (subtask.docs && subtask.docs.length) {
      html += `<div class="section-row" style="margin-top:14px"><div class="section-title">الوثائق</div><div class="section-line"></div></div>`;
      html += `<div class="doc-list">`;
      subtask.docs.forEach(doc => {
        const icon = docIcon(doc.mimetype);
        html += `<a class="doc-item" href="${doc.url}" target="_blank" download>
          <span class="doc-icon">${icon}</span>
          <span class="doc-name">${doc.name}</span>
          <span class="doc-type">${doc.mimetype.split('/')[1]?.toUpperCase() || 'FILE'}</span>
        </a>`;
      });
      html += `</div>`;
    }

    $('modal-subtask-body').innerHTML = html;
    openModal('modal-subtask');
  };

  // ══════════════════════════════════════════════════════════
  // LIGHTBOX
  // ══════════════════════════════════════════════════════════
  window.openLightbox = function(url, name) {
    $('lightbox-img').src = url;
    $('lightbox-caption').textContent = name;
    openModal('modal-lightbox');
  };

  // ══════════════════════════════════════════════════════════
  // VISIT DETAIL
  // ══════════════════════════════════════════════════════════
  window.showVisitDetail = function(visit) {
    $('modal-visit-title').textContent = `تقرير زيارة — ${visit.date}`;
    $('modal-visit-body').innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px">
        <div style="background:var(--surface2);border-radius:8px;padding:10px 12px">
          <div style="font-size:10px;color:var(--text3)">المهندس</div>
          <div style="font-size:13px;font-weight:700">${visit.engineer}</div>
        </div>
        <div style="background:var(--surface2);border-radius:8px;padding:10px 12px">
          <div style="font-size:10px;color:var(--text3)">العمال</div>
          <div style="font-size:13px;font-weight:700">${visit.workers}</div>
        </div>
        <div style="background:var(--surface2);border-radius:8px;padding:10px 12px">
          <div style="font-size:10px;color:var(--text3)">تقارير NCR</div>
          <div style="font-size:13px;font-weight:700;color:${visit.ncr > 0 ? 'var(--red)' : 'var(--green)'}">${visit.ncr}</div>
        </div>
        <div style="background:var(--surface2);border-radius:8px;padding:10px 12px">
          <div style="font-size:10px;color:var(--text3)">الصور</div>
          <div style="font-size:13px;font-weight:700">${visit.photo_count} 📷</div>
        </div>
      </div>
      ${visit.activities ? `
        <div style="font-size:11px;font-weight:600;color:var(--text2);margin-bottom:5px">الأعمال المنجزة</div>
        <div style="font-size:12px;line-height:1.7;color:var(--text1);background:var(--surface2);border-radius:8px;padding:10px 12px;margin-bottom:10px">${visit.activities}</div>
      ` : ''}
      ${visit.issues ? `
        <div style="font-size:11px;font-weight:600;color:var(--orange);margin-bottom:5px">المشكلات والعوائق</div>
        <div style="font-size:12px;line-height:1.7;color:var(--text1);background:rgba(240,165,0,.05);border:1px solid rgba(240,165,0,.2);border-radius:8px;padding:10px 12px">${visit.issues}</div>
      ` : ''}
    `;
    openModal('modal-visit');
  };

  // ══════════════════════════════════════════════════════════
  // CERT & CO ACTIONS
  // ══════════════════════════════════════════════════════════
  window.approveCert = async function(id, btn) {
    btn.disabled = true; btn.textContent = '...';
    const res = await apiPost(`/dashboard/api/cert/${id}/approve`, {});
    if (res?.ok) btn.closest('.cert-row').querySelector('.cert-status').innerHTML =
      '<span class="pill approved">✓ معتمد</span>';
    btn.closest('.cert-btns').innerHTML = '';
  };

  window.rejectCertDlg = function(id, btn) {
    const reason = prompt('سبب الرفض:');
    if (!reason) return;
    apiPost(`/dashboard/api/cert/${id}/reject`, { reason }).then(res => {
      if (res?.ok) btn.closest('.cert-row').querySelector('.cert-status').innerHTML =
        '<span class="pill rejected">✗ مرفوض</span>';
      btn.closest('.cert-btns').innerHTML = '';
    });
  };

  window.approveCO = async function(id, btn) {
    btn.disabled = true; btn.textContent = '...';
    const res = await apiPost(`/dashboard/api/co/${id}/approve`, {});
    if (res?.ok) btn.closest('.cert-row').querySelector('.cert-status').innerHTML =
      '<span class="pill approved">✓ معتمد</span>';
    btn.closest('.cert-btns').innerHTML = '';
  };

  window.rejectCO = async function(id, btn) {
    btn.disabled = true; btn.textContent = '...';
    const res = await apiPost(`/dashboard/api/co/${id}/reject`, {});
    if (res?.ok) btn.closest('.cert-row').querySelector('.cert-status').innerHTML =
      '<span class="pill rejected">✗ مرفوض</span>';
    btn.closest('.cert-btns').innerHTML = '';
  };

  // ══════════════════════════════════════════════════════════
  // ON-SITE CONSULTANTS
  // ══════════════════════════════════════════════════════════
  async function loadOnSite() {
    const data = await apiGet('/dashboard/api/onsite');
    const pill = $('onsite-pill');
    if (pill) pill.querySelector('span:last-child').textContent = `${data.length} في الموقع`;

    const list = $('onsite-list');
    if (!list) return;
    list.innerHTML = data.length ? data.map(p => `
      <div class="onsite-item">
        <div class="onsite-avatar">${(p.name||'م')[0]}</div>
        <div>
          <div class="onsite-name">${p.name}</div>
          <div class="onsite-mosque">${p.mosque} · ${p.code}</div>
        </div>
        <div class="onsite-time">منذ ${p.checkin}</div>
      </div>
    `).join('') : `<div style="text-align:center;padding:20px;color:var(--text3);font-size:12px">لا يوجد مستشارون في المواقع حالياً</div>`;
  }

  // ══════════════════════════════════════════════════════════
  // LIVE STREAM
  // ══════════════════════════════════════════════════════════
  async function checkLiveStream() {
    const data = await apiGet('/dashboard/api/stream');
    const pill = $('live-pill');
    if (!pill) return;
    if (data && data.id) {
      pill.style.display = 'flex';
      pill.title = data.name;
      pill.onclick = () => openLiveStream(data);
    } else {
      pill.style.display = 'none';
    }
  }

  function openLiveStream(data) {
    $('stream-modal-title').textContent = data.name || 'بث مباشر';
    const embed = $('stream-embed');
    embed.innerHTML = `<iframe src="${data.url}" allowfullscreen allow="camera;microphone"></iframe>`;
    openModal('modal-stream');
  }

  // ══════════════════════════════════════════════════════════
  // CHATBOT
  // ══════════════════════════════════════════════════════════
  const chatFab   = $('chatbot-fab');
  const chatPanel = $('chatbot-panel');
  const chatMsgs  = $('chat-msgs');
  const chatInput = $('chat-input');

  if (chatFab) chatFab.addEventListener('click', () => {
    chatPanel.classList.toggle('open');
    if (chatPanel.classList.contains('open')) chatInput.focus();
  });

  document.getElementById('chat-close')?.addEventListener('click', () =>
    chatPanel.classList.remove('open'));

  async function sendChatMessage(msg) {
    if (!msg.trim()) return;
    chatInput.value = '';

    appendChatMsg('user', msg);
    state.chatHistory.push({ role: 'user', content: msg });

    const thinking = appendChatMsg('bot', '...');

    const res = await apiPost('/dashboard/api/chat', {
      message:         msg,
      mosque_context:  state.mosqueContext,
      history:         state.chatHistory.slice(-8),
    });

    thinking.textContent = res?.reply || 'تعذر الحصول على رد.';
    state.chatHistory.push({ role: 'assistant', content: res?.reply || '' });
    chatMsgs.scrollTop = chatMsgs.scrollHeight;
  }

  function appendChatMsg(role, text) {
    const d = document.createElement('div');
    d.className = `chat-msg ${role}`;
    d.textContent = text;
    chatMsgs.appendChild(d);
    chatMsgs.scrollTop = chatMsgs.scrollHeight;
    return d;
  }

  document.getElementById('chat-send')?.addEventListener('click', () =>
    sendChatMessage(chatInput.value));

  chatInput?.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChatMessage(chatInput.value); }
  });

  document.querySelectorAll('.chat-sug').forEach(btn => {
    btn.addEventListener('click', function () {
      sendChatMessage(this.textContent);
      chatPanel.classList.add('open');
    });
  });

  // ══════════════════════════════════════════════════════════
  // MODAL HELPERS
  // ══════════════════════════════════════════════════════════
  function openModal(id) {
    $('modal-' + id.replace('modal-',''))?.classList.add('show');
    document.getElementById(id)?.classList.add('show');
  }

  function closeModal(id) {
    document.getElementById(id)?.classList.remove('show');
  }

  window.closeModal = closeModal;

  // Close on overlay click
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', function (e) {
      if (e.target === this) this.classList.remove('show');
    });
  });

  // ══════════════════════════════════════════════════════════
  // SECTION SWITCHER
  // ══════════════════════════════════════════════════════════
  function showSection(id) {
    document.querySelectorAll('.wd-section').forEach(s => s.style.display = 'none');
    const el = $(id);
    if (el) el.style.display = '';
  }

  // ══════════════════════════════════════════════════════════
  // AUTO REFRESH
  // ══════════════════════════════════════════════════════════
  function startRefresh() {
    const interval = (state.config.refresh_interval || 60) * 1000;
    state.refreshTimer = setInterval(() => {
      loadSummary();
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
    const m = {
      green:  'background:rgba(46,204,138,.12);color:#1A7A55',
      red:    'background:rgba(232,85,85,.1);color:#A33',
      yellow: 'background:rgba(240,165,0,.1);color:#A67800',
      grey:   'background:var(--surface2);color:var(--text3)',
    };
    return m[color] || m.grey;
  }
  function reviewStateLabel(s) {
    return { pending:'لم يبدأ', submitted:'بانتظار الاستشاري', approved:'✓ معتمد', rejected:'✗ مرفوض', blocked:'🔒 مجمّد' }[s] || s;
  }
  function certPillClass(s) {
    return { draft:'pending', submitted:'pending', consultant_review:'pending',
             consultant_approved:'review', approved:'approved', rejected:'rejected',
             review:'pending', paid:'approved' }[s] || 'pending';
  }
  function certStateLabel(s) {
    return { draft:'مسودة', submitted:'بانتظار الاستشاري', consultant_review:'مراجعة الاستشاري',
             consultant_approved:'بانتظار الوقف', approved:'معتمد', rejected:'مرفوض',
             review:'قيد المراجعة', paid:'مدفوع' }[s] || s;
  }
  function stateLabel(s) {
    return { draft:'لم يبدأ', mobilizing:'التجهيز', active:'قيد التنفيذ',
             initial_hov:'استلام ابتدائي', final_hov:'استلام نهائي',
             warranty:'ضمان', closed:'مغلق' }[s] || s;
  }
  function docIcon(mime) {
    if (mime.includes('pdf'))   return '📄';
    if (mime.includes('word') || mime.includes('docx')) return '📝';
    if (mime.includes('sheet') || mime.includes('xlsx')) return '📊';
    if (mime.includes('zip'))   return '🗜';
    return '📁';
  }
  function truncate(str, n) {
    return str && str.length > n ? str.substring(0, n) + '…' : str;
  }

  // Load Chart.js dynamically
  function loadChartJS(cb) {
    if (window.Chart) { cb(); return; }
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js';
    s.onload = cb;
    document.head.appendChild(s);
  }

  loadChartJS(init);
});