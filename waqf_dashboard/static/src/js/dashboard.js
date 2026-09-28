/* ═══════════════════════════════════════════════════════════════
   Waqf Executive Command Center — JS v2
   Full rebuild: Executive Strip · Alerts · Gantt · Heatmap
   Risk Matrix · Forecast · Quality · AI Insights · Contractors
   Mosque Detail (preserved) · Chatbot · Search
   ═══════════════════════════════════════════════════════════════ */
'use strict';

document.addEventListener('DOMContentLoaded', function () {

    /* ── Read server-injected data ─────────────────────────── */
    const dataEl = document.getElementById('waqf-data');
    const CONFIG = JSON.parse(dataEl?.dataset.config || '{}');
    const PKGS = JSON.parse(dataEl?.dataset.packages || '[]');
    const ONSITE = JSON.parse(dataEl?.dataset.onsite || '[]');
    const HAS_AI = dataEl?.dataset.hasAi === '1';

    /* ── State ─────────────────────────────────────────────── */
    const S = {
        mosques: [],          // كل المساجد (من /api/mosques)
        packages: PKGS,
        scopePkgId: (PKGS.find(p => p.is_current) || {}).id || null,
        summary: {},
        onsite: ONSITE,
        allAlerts: [],
        alertFilter: 'all',
        hmFilter: 'all',
        mapFilter: 'all',
        activeMosqueId: null,
        mosqueContext: null,
        chatHistory: [],
        refreshTimer: null,
        map: null,
        cluster: null,
        mapMarkers: {},
        liveStreams: {},      // mosque_id → url (مباشر الآن)
        streams: [],          // المباشر + التسجيلات
        streamByMosque: {},   // mosque_id → أحدث بث (المباشر أولاً)
    };

    /* ── Helpers ────────────────────────────────────────────── */
    const $ = id => document.getElementById(id);
    const fmt = n => new Intl.NumberFormat('en-US').format(Math.round(n || 0));
    const pct = n => Math.round(n || 0) + '%';
    const esc = s => String(s ?? '').replace(/[&<>"']/g,
        c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
    const STATUS = {
        ok:          {label: 'في الموعد',  color: '#25A874'},
        warning:     {label: 'تأخر بسيط', color: '#E0A12A'},
        critical:    {label: 'حرج',        color: '#DE5B4C'},
        done:        {label: 'مكتمل',      color: '#2E8FB5'},
        not_started: {label: 'لم يبدأ',    color: '#B9AE96'},
    };
    const statusColor = s => (STATUS[s] || STATUS.not_started).color;
    const dotColor = kpi =>
        kpi >= 70 ? '#25A874' : kpi >= 50 ? '#E0A12A' : kpi > 0 ? '#DE5B4C' : '#B9AE96';
    const truncate = (s, n) =>
        s && s.length > n ? s.substring(0, n) + '…' : (s || '');
    const kanbanColor = c =>
        ({
            green: '#1F9D6B', red: '#D9493B', yellow: '#D98A0B',
            orange: '#D98A0B', grey: '#8FA3B3'
        }[c] || '#8FA3B3');
    const stateLabel = s =>
        ({
            draft: 'لم يبدأ', mobilizing: 'التجهيز', active: 'قيد التنفيذ',
            initial_hov: 'استلام ابتدائي', final_hov: 'استلام نهائي',
            warranty: 'ضمان', closed: 'مغلق'
        }[s] || s);
    const certPillClass = s =>
        ({
            draft: 'pending', submitted: 'pending', consultant_review: 'pending',
            consultant_approved: 'review', approved: 'approved',
            rejected: 'rejected', review: 'pending', paid: 'approved'
        }[s] || 'pending');
    const certStateLabel = s =>
        ({
            draft: 'مسودة', submitted: 'بانتظار الاستشاري',
            consultant_review: 'مراجعة الاستشاري',
            consultant_approved: 'بانتظار الوقف',
            approved: 'معتمد', rejected: 'مرفوض',
            review: 'قيد المراجعة', paid: 'مدفوع'
        }[s] || s);
    const reviewStateLabel = s =>
        ({
            pending: 'لم يبدأ', submitted: 'بانتظار الاستشاري',
            approved: '✓ معتمد', rejected: '✗ مرفوض', blocked: '🔒 مجمّد'
        }[s] || s);
    const docIcon = mime => {
        if (!mime) return '📁';
        if (mime.includes('pdf')) return '📄';
        if (mime.includes('word') || mime.includes('docx')) return '📝';
        if (mime.includes('sheet') || mime.includes('xlsx')) return '📊';
        if (mime.includes('zip')) return '🗜';
        return '📁';
    };
    // مبلغ مالي يُخفى عند تفعيل «إخفاء المالية»
    const mny = v => `<span class="fin">${fmt(v)} ر</span>`;
    // قيمة مالية مختصرة: مليون / ألف
    const money = v => v >= 1e6
        ? {val: (v / 1e6).toLocaleString('en-US', {maximumFractionDigits: 1}), unit: 'م ر'}
        : {val: Math.round(v / 1000).toLocaleString('en-US'), unit: 'ألف ر'};
    const elapsedLabel = min => {
        const h = Math.floor(min / 60), m = min % 60;
        return h ? `${h}س ${m}د` : `${m}د`;
    };
    const scopedMosques = () => S.scopePkgId
        ? S.mosques.filter(m => m.package_id === S.scopePkgId) : S.mosques;

    /* ── API ────────────────────────────────────────────────── */
    async function apiGet(url) {
        try {
            const r = await fetch(url, {credentials: 'same-origin'});
            return await r.json();
        } catch (e) {
            console.warn('dashboard api', url, e);
            return null;
        }
    }

    async function apiPost(url, data) {
        const csrf = document.cookie.match(/csrf_token=([^;]+)/)?.[1] || '';
        const r = await fetch(url, {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: data}),
        });
        const j = await r.json();
        return j.result;
    }

    /* ══════════════════════════════════════════════════════════
       INIT
       ══════════════════════════════════════════════════════════ */
    async function init() {
        initFinToggle();
        startClock();
        buildSidebar(S.packages);
        renderOnsite(S.onsite);
        initQuickFilters();
        initAlertFilters();
        initMapFilters();
        initSideTabs();

        loadChartJS(async () => {
            const [mosques, summary, alerts, insights, risk, forecast, quality, contractors, streams] =
                await Promise.all([
                    apiGet('/dashboard/api/mosques'),
                    apiGet('/dashboard/api/summary'),
                    apiGet('/dashboard/api/alerts'),
                    apiGet('/dashboard/api/ai_insights'),
                    apiGet('/dashboard/api/risk_matrix'),
                    apiGet('/dashboard/api/forecast'),
                    apiGet('/dashboard/api/quality'),
                    apiGet('/dashboard/api/contractors'),
                    apiGet('/dashboard/api/streams'),
                ]);

            setMosques(mosques || []);
            setStreams(streams || []);
            S.summary = summary || {};
            if (!S.scopePkgId && S.summary.current_package_id) S.scopePkgId = S.summary.current_package_id;
            renderAlerts(alerts || {});
            applyScope();
            initMap();
            if (insights) renderAIInsights(insights);
            renderRiskMatrix(risk?.points || []);
            renderForecast(forecast?.rows || []);
            if (quality) renderQuality(quality);
            renderContractors(contractors?.contractors || []);
            renderCriticalProjects(S.mosques);
            loadOnSite();
            checkLiveStream();
            initSearch();
            startRefresh();
        });
    }

    function setMosques(list) {
        S.mosques = list;
        S.liveStreams = {};
        list.forEach(m => { if (m.stream_url) S.liveStreams[m.id] = m.stream_url; });
        Object.values(S.streamByMosque).forEach(st => { if (st.is_live && st.mosque_id) S.liveStreams[st.mosque_id] = st.url; });
    }

    function setStreams(list) {
        S.streams = Array.isArray(list) ? list : [];
        S.streamByMosque = {};
        S.streams.forEach(st => {           // مرتبة: المباشر أولاً ثم الأحدث
            if (st.mosque_id && !S.streamByMosque[st.mosque_id]) S.streamByMosque[st.mosque_id] = st;
            if (st.is_live && st.mosque_id) S.liveStreams[st.mosque_id] = st.url;
        });
        renderStreams();
    }

    function initSideTabs() {
        document.querySelectorAll('.mapx-tab').forEach(t =>
            t.addEventListener('click', () => {
                document.querySelectorAll('.mapx-tab').forEach(x => x.classList.toggle('active', x === t));
                document.querySelectorAll('.mapx-pane').forEach(p =>
                    p.classList.toggle('active', p.dataset.pane === t.dataset.pane));
            }));
    }

    function renderStreams() {
        const box = $('stream-list');
        const live = S.streams.filter(st => st.is_live).length;
        const cnt = $('stream-count');
        if (cnt) cnt.textContent = live ? `${live} مباشر` : S.streams.length;
        if (!box) return;
        if (!S.streams.length) {
            box.innerHTML = `<div class="mapx-empty">لا توجد بثوث مسجّلة بعد</div>`;
            return;
        }
        box.innerHTML = S.streams.map((st, i) => `
          <div class="stream-card${st.is_live ? ' live' : ''}" data-i="${i}">
            <div class="stream-thumb">${st.is_live ? '<span class="dot"></span>' : '▶'}</div>
            <div class="onsite-info">
              <div class="onsite-nm">${esc(st.mosque || st.name)}</div>
              <div class="onsite-ms">${esc(st.name)}${st.started_by ? ' · ' + esc(st.started_by) : ''}</div>
              <span class="onsite-flag ${st.is_live ? 'live' : 'rec'}">${st.is_live ? '● مباشر الآن' : '🎥 تسجيل'}</span>
            </div>
            <div class="onsite-tm">
              <b>${esc((st.start || '').slice(11))}</b>
              <span>${esc((st.start || '').slice(0, 10))}</span>
            </div>
          </div>`).join('');
        box.querySelectorAll('.stream-card').forEach(c =>
            c.addEventListener('click', () => {
                const st = S.streams[parseInt(c.dataset.i)];
                if (!st) return;
                if (st.mosque_id) focusMosque(st.mosque_id);
                openLiveStream({name: `${st.mosque || ''} — ${st.name}`, url: st.url,
                                is_live: st.is_live, start: st.start});
            }));
    }

    /* ── ساعة الرياض ──────────────────────────────────────────── */
    function initFinToggle() {
        const btn = $('fin-toggle');
        const apply = hidden => {
            document.body.classList.toggle('hide-fin', hidden);
            if (btn) {
                btn.classList.toggle('on', hidden);
                btn.title = hidden ? 'إظهار التفاصيل المالية' : 'إخفاء التفاصيل المالية';
                const lbl = btn.querySelector('span');
                if (lbl) lbl.textContent = hidden ? 'إظهار المالية' : 'إخفاء المالية';
            }
        };
        let hidden = false;
        try { hidden = localStorage.getItem('waqf_hide_fin') === '1'; } catch (e) { /* ignore */ }
        apply(hidden);
        btn?.addEventListener('click', () => {
            hidden = !document.body.classList.contains('hide-fin');
            apply(hidden);
            try { localStorage.setItem('waqf_hide_fin', hidden ? '1' : '0'); } catch (e) { /* ignore */ }
        });
    }

    function startClock() {
        const el = $('riyadh-clock');
        if (!el) return;
        const f = new Intl.DateTimeFormat('en-GB', {
            timeZone: 'Asia/Riyadh', hour: '2-digit', minute: '2-digit', hour12: false,
        });
        const tick = () => { el.textContent = f.format(new Date()); };
        tick();
        setInterval(tick, 15000);
    }

    /* ══════════════════════════════════════════════════════════
       SCOPE (المرحلة المختارة)
       ══════════════════════════════════════════════════════════ */
    function applyScope() {
        const pkg = S.packages.find(p => p.id === S.scopePkgId);
        const chip = $('scope-chip');
        if (chip) chip.textContent = pkg ? `المرحلة: ${pkg.name}` : 'كل المراحل';
        $('sb-scope-all')?.classList.toggle('active', !pkg);
        document.querySelectorAll('.sb-pkg-card').forEach(c =>
            c.classList.toggle('active', parseInt(c.dataset.pkgId) === S.scopePkgId));

        const list = scopedMosques();
        renderKPIs(list, S.summary);
        buildHeatmap(list);
        buildPhaseGantt(pkg || S.packages.find(p => p.is_current));
        refreshMapMarkers();
    }

    /* ══════════════════════════════════════════════════════════
       KPI STRIP — محسوبة من بيانات المساجد الحية
       ══════════════════════════════════════════════════════════ */
    function renderKPIs(list, summary) {
        const set = (id, v) => { const el = $(id); if (el) el.innerHTML = v; };
        const n = list.length;
        const contract = list.reduce((s, m) => s + (m.contract_value || 0), 0);
        const boq = list.reduce((s, m) => s + (m.boq_value || 0), 0);
        const executed = list.reduce((s, m) => s + (m.executed_value || 0), 0);
        // الإنجاز = متوسط إنجاز المساجد (بعدد الأعمال المعتمدة) — الكميات للمعلومية
        const avg = k => n ? list.reduce((s, m) => s + (m[k] || 0), 0) / n : 0;
        const sum = k => list.reduce((s, m) => s + (m[k] || 0), 0);
        const actual = avg('actual_pct');
        const inprogPct = avg('inprogress_pct');
        const inprog = sum('inprogress_value');
        const awaiting = sum('wo_awaiting_grade');
        const planned = avg('planned_pct');
        const by = st => list.filter(m => m.status === st).length;
        const active = n - by('not_started');

        const c = money(contract);
        set('kpi-total-value', c.val); set('kpi-total-unit', c.unit);
        set('kpi-total-sub', `<b>${n}</b> مسجد · جدول الكميات ${money(boq).val} ${money(boq).unit}`);

        set('kpi-actual', Math.round(actual));
        const bar = $('kpi-actual-bar'); if (bar) bar.style.width = Math.min(100, actual) + '%';
        const ipb = $('kpi-inprog-bar');
        if (ipb) { ipb.style.right = Math.min(100, actual) + '%'; ipb.style.width = Math.min(100 - Math.min(100, actual), inprogPct) + '%'; }
        const mark = $('kpi-plan-mark'); if (mark) mark.style.right = Math.min(100, planned) + '%';
        const diff = Math.round(actual - planned);
        set('kpi-actual-sub', `المخطط <b>${Math.round(planned)}%</b> · ` +
            (diff >= 0 ? `<span style="color:var(--green)">متقدم ${diff}%</span>`
                       : `<span style="color:var(--red)">متأخر ${Math.abs(diff)}%</span>`) +
            (inprogPct >= 0.1 ? ` · <span class="ip-txt" title="أوامر عمل معتمدة البدء أو مسلّمة ولم تُقيَّم بعد">جارٍ ${inprogPct.toFixed(1)}%</span>` : '') +
            `<br/>مهام معتمدة <b>${sum('task_done')}/${sum('task_total')}</b> · أوامر مقبولة <b>${sum('wo_done')}/${sum('wo_total')}</b>`);

        const e = money(executed);
        set('kpi-executed', e.val); set('kpi-executed-unit', e.unit);
        set('kpi-executed-sub', `للمعلومية — لا تدخل في الإنجاز · الكميات ${boq ? (executed / boq * 100).toFixed(1) : 0}%` +
            (inprog ? ` · جارٍ <span class="fin">${money(inprog).val} ${money(inprog).unit}</span>` : '') +
            (awaiting ? ` · <b style="color:var(--orange)">${awaiting}</b> بانتظار التقييم` : ''));

        set('kpi-ontime', by('ok') + by('done'));
        set('kpi-ontime-of', ` / ${active}`);
        set('kpi-ontime-sub', `<b>${by('done')}</b> مكتمل · <b>${by('not_started')}</b> لم يبدأ`);

        set('kpi-critical', by('critical'));
        const late = list.filter(m => m.days_delay > 0).length;
        set('kpi-critical-sub', `<b>${late}</b> تجاوز المدة · <b>${by('warning')}</b> تأخر بسيط`);

        const p = summary?.pending || {};
        set('kpi-pending', summary?.pending_total ?? '—');
        set('kpi-pending-sub',
            `أوامر عمل <b>${p.work_orders || 0}</b> · مستخلصات <b>${(p.certs || 0) + (p.claims || 0)}</b>` +
            ` · تغيير <b>${p.cos || 0}</b>`);
    }

    /* ══════════════════════════════════════════════════════════
       SMART ALERT CENTER
       ══════════════════════════════════════════════════════════ */
    const SEV = {
        critical: {cls: 'cr', label: 'حرج', icon: '🔴'},
        high:     {cls: 'hi', label: 'مرتفع', icon: '🟠'},
        medium:   {cls: 'md', label: 'متوسط', icon: '🟡'},
        low:      {cls: 'low', label: 'منخفض', icon: '🟢'},
    };

    function renderAlerts(data) {
        S.allAlerts = data.alerts || [];
        const countEl = $('alert-count');
        if (countEl) countEl.textContent = data.total ?? S.allAlerts.length;
        const counts = data.counts || {};
        document.querySelectorAll('[data-an]').forEach(el => {
            const v = counts[el.dataset.an];
            el.textContent = v ? v : '';
        });
        const srcEl = $('alert-source-badge');
        if (srcEl) srcEl.textContent = data.source === 'ai_center'
            ? '🤖 من مركز المخاطر الذكي' : '⚙ محسوبة من البيانات الحية';
        const runEl = $('alert-run');
        if (runEl) runEl.textContent = data.last_run ? `آخر تحليل: ${data.last_run}` : '';
        renderAlertList(S.alertFilter);
    }

    function initAlertFilters() {
        document.querySelectorAll('.alert-filter').forEach(btn =>
            btn.addEventListener('click', function () {
                document.querySelectorAll('.alert-filter').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                S.alertFilter = this.dataset.filter;
                renderAlertList(S.alertFilter);
            }));
    }

    function renderAlertList(filter) {
        const list = $('alert-list');
        if (!list) return;
        const items = filter === 'all' ? S.allAlerts
            : filter === 'critical' ? S.allAlerts.filter(a => a.severity === 'critical')
            : S.allAlerts.filter(a => a.group === filter);

        if (!items.length) {
            list.innerHTML = `<div style="padding:28px;text-align:center;color:var(--text3)">
                ✓ لا توجد تنبيهات في هذا التصنيف</div>`;
            return;
        }
        list.innerHTML = items.map((a, i) => {
            const sv = SEV[a.severity] || SEV.medium;
            const more = a.root_cause || a.recommendation;
            return `
          <div class="alert-item" data-i="${i}">
            <div class="alert-severity ${sv.cls}"></div>
            <div class="alert-body">
              <div class="alert-title">${esc(a.title)}</div>
              <div class="alert-desc">${esc(a.description)}</div>
              ${a.mosque_name ? `<div class="alert-sub">🕌 ${esc(a.mosque_name)}${a.mosque_code ? ' · ' + esc(a.mosque_code) : ''}</div>` : ''}
            </div>
            <div class="alert-actions">
              <span class="alert-badge ${sv.cls}">${sv.label}</span>
              ${a.mosque_id ? `<button class="alert-cta" data-mosque="${a.mosque_id}">فتح المسجد</button>` : ''}
            </div>
            ${more ? `<dl class="alert-more">
                ${a.root_cause && a.root_cause !== a.description ? `<dt>السبب</dt><dd>${esc(a.root_cause)}</dd>` : ''}
                ${a.recommendation ? `<dt>التوصية</dt><dd>${esc(a.recommendation)}</dd>` : ''}
                ${a.created_at ? `<dd style="color:var(--text3);font-size:10px">${esc(a.created_at)} (توقيت الرياض)${a.confidence ? ' · ثقة ' + a.confidence + '%' : ''}</dd>` : ''}
              </dl>` : ''}
          </div>`;
        }).join('');

        list.querySelectorAll('.alert-item').forEach(el =>
            el.addEventListener('click', () => el.classList.toggle('open')));
        list.querySelectorAll('.alert-cta').forEach(btn =>
            btn.addEventListener('click', e => {
                e.stopPropagation();
                loadMosqueDetail(parseInt(btn.dataset.mosque));
            }));
    }

    /* ══════════════════════════════════════════════════════════
       PHASE GANTT — الفعلي مقابل المخطط
       ══════════════════════════════════════════════════════════ */
    function buildPhaseGantt(pkg) {
        const el = $('gantt-rows'), monthsEl = $('gantt-months');
        if (!el) return;
        if (!pkg || !pkg.planned_start || !pkg.planned_end) {
            el.innerHTML = `<div style="padding:30px;text-align:center;color:var(--text3)">
                لا توجد مرحلة نشطة بتواريخ محددة</div>`;
            if (monthsEl) monthsEl.innerHTML = '';
            return;
        }
        const start = new Date(pkg.planned_start), end = new Date(pkg.planned_end);
        const total = Math.max(1, end - start);
        const todayP = Math.min(100, Math.max(0, (Date.now() - start) / total * 100));

        if (monthsEl) {
            const names = ['ينا', 'فبر', 'مار', 'أبر', 'ماي', 'يون', 'يول', 'أغس', 'سبت', 'أكت', 'نوف', 'ديس'];
            const months = [];
            const d = new Date(start.getFullYear(), start.getMonth(), 1);
            while (d <= end && months.length < 24) {
                months.push(names[d.getMonth()] + (d.getMonth() === 0 ? ' ' + String(d.getFullYear()).slice(2) : ''));
                d.setMonth(d.getMonth() + 1);
            }
            monthsEl.innerHTML = months.map(m => `<div class="gantt-month">${m}</div>`).join('');
        }

        const mosques = S.mosques.filter(m => m.package_id === pkg.id);
        const list = mosques.length ? mosques : (pkg.mosques || []);
        const avg = list.length ? list.reduce((s, m) => s + (m.actual_pct || 0), 0) / list.length : 0;

        el.innerHTML = `
      <div style="position:relative;height:30px;margin-bottom:16px;background:var(--surface3);border-radius:8px">
        <div style="position:absolute;top:0;bottom:0;right:0;width:${todayP}%;
             background:linear-gradient(90deg,rgba(35,114,146,.25),rgba(35,114,146,.12));border-radius:8px"></div>
        <span style="position:relative;z-index:1;font-size:10.5px;font-weight:700;padding:0 12px;
             line-height:30px;color:var(--navy)">
          ${esc(pkg.name)} · ${list.length} مسجد · متوسط الإنجاز ${Math.round(avg)}% · ${pkg.planned_start} ← ${pkg.planned_end}
        </span>
        <div class="gantt-today" style="right:${todayP}%"><div class="gantt-today-label">اليوم</div></div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;max-height:420px;overflow-y:auto">
        ${list.slice().sort((a, b) => (a.variance ?? 0) - (b.variance ?? 0)).map(m => {
            const col = statusColor(m.status);
            const act = Math.min(100, m.actual_pct || 0), plan = Math.min(100, m.planned_pct || 0);
            return `
          <div class="gantt-mrow" data-id="${m.id}" style="display:flex;align-items:center;gap:10px;padding:8px 12px;
               border-radius:10px;cursor:pointer;background:#fff;border:1px solid var(--border)">
            <span style="width:9px;height:9px;border-radius:50%;background:${col};flex-shrink:0"></span>
            <span style="font-size:10px;font-weight:700;color:var(--primary);min-width:54px">${esc(m.code)}</span>
            <span style="flex:1;font-size:11.5px;font-weight:600;color:var(--text1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(m.name)}</span>
            <div style="width:110px;height:7px;background:var(--surface3);border-radius:4px;position:relative;flex-shrink:0" title="الفعلي ${act}% · المخطط ${plan}%">
              <div style="width:${act}%;height:100%;background:${col};border-radius:4px"></div>
              ${m.inprogress_pct ? `<div class="ip-seg" style="right:${act}%;width:${Math.min(100 - act, m.inprogress_pct)}%"></div>` : ''}
              <div style="position:absolute;top:-3px;right:${plan}%;width:2px;height:13px;background:var(--gold)"></div>
            </div>
            <span style="font-size:11.5px;font-weight:800;color:${col};min-width:38px;text-align:left">${Math.round(act)}%</span>
            ${m.days_delay > 0
                ? `<span style="font-size:10px;font-weight:700;color:var(--red);background:rgba(217,73,59,.1);padding:1px 8px;border-radius:999px">+${m.days_delay} يوم</span>`
                : ''}
          </div>`;
        }).join('')}
      </div>`;
        el.querySelectorAll('.gantt-mrow').forEach(r =>
            r.addEventListener('click', () => loadMosqueDetail(parseInt(r.dataset.id))));
    }

    window.loadMosqueDetailGlobal = id => {
        document.querySelectorAll('.gantt-popup').forEach(p => p.classList.remove('show'));
        loadMosqueDetail(id);
    };

    /* ══════════════════════════════════════════════════════════
       HEATMAP — بيانات حقيقية فقط
       ══════════════════════════════════════════════════════════ */
    function buildHeatmap(mosques) {
        const el = $('heatmap-grid');
        if (!el) return;
        const onsiteIds = new Set(S.onsite.map(p => p.mosque_id));
        const counts = {all: mosques.length, onsite: 0};
        mosques.forEach(m => {
            counts[m.status] = (counts[m.status] || 0) + 1;
            if (onsiteIds.has(m.id)) counts.onsite++;
        });
        document.querySelectorAll('[data-n]').forEach(n => {
            n.textContent = counts[n.dataset.n] ? ' ' + counts[n.dataset.n] : '';
        });

        if (!mosques.length) {
            el.innerHTML = `<div style="grid-column:1/-1;padding:24px;text-align:center;color:var(--text3)">لا توجد مساجد في هذا النطاق</div>`;
            return;
        }
        el.innerHTML = '';
        mosques.slice().sort((a, b) => (a.code || '').localeCompare(b.code || '')).forEach(m => {
            const cell = document.createElement('div');
            cell.className = `hm-cell ${m.status || 'not_started'}${onsiteIds.has(m.id) ? ' onsite' : ''}`;
            cell.dataset.id = m.id;
            cell.innerHTML = `
              <span class="hm-code">${esc((m.code || '').replace(/^[A-Z]+-0?/, ''))}</span>
              <span class="hm-val">${m.status === 'not_started' ? '—' : Math.round(m.actual_pct) + '%'}</span>
              ${m.inprogress_pct >= 0.5 ? `<span class="hm-ip">جارٍ ${Math.round(m.inprogress_pct)}%</span>` : ''}
              <div class="hm-tooltip">
                <strong>${esc(m.code)}</strong> — ${esc(truncate(m.name, 26))}<br/>
                الإنجاز <b>${m.actual_pct}%</b> · المخطط <b>${m.planned_pct}%</b><br/>
                مهام معتمدة ${m.task_done || 0}/${m.task_total || 0} · أوامر مقبولة ${m.wo_done || 0}/${m.wo_total || 0}
                · الكميات ${m.qty_pct || 0}% (معلومة)<br/>
                ${m.inprogress_pct ? ` · جارٍ <b>${m.inprogress_pct}%</b>` : ''}<br/>
                أوامر مفتوحة ${m.wo_open || 0}${m.wo_awaiting_grade ? ` (${m.wo_awaiting_grade} بانتظار التقييم)` : ''}
                · هذا الأسبوع: ${m.wo_week || 0} أمر، ${m.reports_week || 0} تقرير<br/>
                ${(STATUS[m.status] || STATUS.not_started).label}
                ${m.days_delay > 0 ? ` · <span style="color:#FFB4A8">تجاوز المدة ${m.days_delay} يوم</span>` : ''}
                ${onsiteIds.has(m.id) ? '<br/>👷 مستشار في الموقع الآن' : ''}
              </div>`;
            cell.addEventListener('click', () => {
                document.querySelectorAll('.hm-cell').forEach(c => c.classList.remove('active'));
                cell.classList.add('active');
                focusMosque(m.id);
                loadMosqueDetail(m.id);
            });
            el.appendChild(cell);
        });
        applyHeatmapFilter();
    }

    function initQuickFilters() {
        document.querySelectorAll('.qf-btn').forEach(btn =>
            btn.addEventListener('click', function () {
                document.querySelectorAll('.qf-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                S.hmFilter = this.dataset.filter;
                applyHeatmapFilter();
            }));
    }

    function applyHeatmapFilter() {
        const f = S.hmFilter;
        const onsiteIds = new Set(S.onsite.map(p => p.mosque_id));
        document.querySelectorAll('.hm-cell').forEach(cell => {
            const m = S.mosques.find(x => x.id === parseInt(cell.dataset.id));
            if (!m) return;
            const show = f === 'all' ? true
                : f === 'onsite' ? onsiteIds.has(m.id)
                : m.status === f;
            cell.classList.toggle('dim', !show);
        });
    }

    /* ══════════════════════════════════════════════════════════
       INTERACTIVE MAP + ON-SITE CONSULTANTS
       ══════════════════════════════════════════════════════════ */
    function initMap() {
        const mapEl = $('mosque-map');
        if (!mapEl) return;
        if (!document.getElementById('leaflet-css')) {
            const css = document.createElement('link');
            css.id = 'leaflet-css';
            css.rel = 'stylesheet';
            css.href = 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css';
            document.head.appendChild(css);
        }
        const loadCluster = () => {
            if (L.markerClusterGroup) return _buildMap();
            const c = document.createElement('script');
            c.src = 'https://cdn.jsdelivr.net/npm/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js';
            c.onload = _buildMap;
            c.onerror = _buildMap;          // بدون تجميع إن تعذر التحميل
            document.head.appendChild(c);
        };
        if (window.L) return loadCluster();
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js';
        script.onload = loadCluster;
        script.onerror = () => {
            mapEl.innerHTML = `<div class="mapx-empty">تعذر تحميل الخريطة</div>`;
        };
        document.head.appendChild(script);
    }

    function _buildMap() {
        if (!window.L || !$('mosque-map')) return;
        if (S.map) { S.map.remove(); S.map = null; }
        S.map = L.map('mosque-map', {
            center: [23.8859, 45.0792], zoom: 5, minZoom: 4, maxZoom: 19,
            zoomControl: true, attributionControl: true,
        });
        S.map.attributionControl.setPrefix(false);
        S.cluster = L.markerClusterGroup ? L.markerClusterGroup({
            maxClusterRadius: 45, showCoverageOnHover: false, spiderfyOnMaxZoom: true,
            iconCreateFunction: c => {
                const ms = c.getAllChildMarkers();
                const worst = ms.some(x => x.options.status === 'critical') ? 'critical'
                    : ms.some(x => x.options.status === 'warning') ? 'warning' : 'ok';
                const people = ms.reduce((n, x) => n + (x.options.people || 0), 0);
                return L.divIcon({
                    className: '',
                    html: `<div class="mk-cluster" style="border-color:${statusColor(worst)}">${ms.length}
                           ${people ? `<span class="mk-badge">👷${people}</span>` : ''}</div>`,
                    iconSize: [42, 42], iconAnchor: [21, 21],
                });
            },
        }).addTo(S.map) : null;
        // خريطة فاتحة بأسماء عربية (OpenStreetMap) — مُلطّفة بالـ CSS لتناسب الهوية
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19, attribution: '© OpenStreetMap',
        }).addTo(S.map);
        refreshMapMarkers(true);
    }

    // إحداثيات تقريبية للمساجد بدون موقع محفوظ — حول مركز المدينة
    const CITY_BASE = {
        riyadh: [24.7136, 46.6753], jeddah: [21.4858, 39.1925], taif: [21.2703, 40.4158],
        jazan: [16.8892, 42.5511], yara: [18.3059, 42.7337], aflaj: [22.2641, 46.7159],
        rafha: [29.6267, 43.4914],
    };
    function mosqueLatLng(m, idx) {
        if (m.lat && m.lng) return [m.lat, m.lng];
        const base = CITY_BASE[(m.city || '').toLowerCase()] || CITY_BASE.riyadh;
        const a = idx * 2.399963;               // توزيع حلزوني
        const r = 0.025 + 0.012 * Math.sqrt(idx);
        return [base[0] + Math.cos(a) * r, base[1] + Math.sin(a) * r];
    }

    function markerVisible(m, onsiteMap) {
        const f = S.mapFilter;
        return f === 'all' ? true
            : f === 'onsite' ? !!onsiteMap[m.id]
            : f === 'critical' ? (m.status === 'critical' || m.status === 'warning')
            : f === 'stream' ? !!(S.liveStreams[m.id] || S.streamByMosque[m.id]) : true;
    }

    function refreshMapMarkers(fit) {
        if (!S.map || !window.L) return;
        const layer = S.cluster || S.map;
        if (S.cluster) S.cluster.clearLayers();
        else Object.values(S.mapMarkers).forEach(mk => S.map.removeLayer(mk));
        S.mapMarkers = {};
        const onsiteMap = {};
        S.onsite.forEach(p => { if (p.mosque_id) (onsiteMap[p.mosque_id] = onsiteMap[p.mosque_id] || []).push(p); });

        const cityIdx = {};
        const pts = [];
        scopedMosques().forEach(m => {
            const key = (m.city || 'riyadh').toLowerCase();
            cityIdx[key] = (cityIdx[key] || 0) + 1;
            if (!markerVisible(m, onsiteMap)) return;
            const ll = mosqueLatLng(m, cityIdx[key]);
            const people = onsiteMap[m.id] || [];
            const icon = L.divIcon({
                className: '',
                html: `<div class="mk${people.length ? ' onsite' : ''}" style="background:${statusColor(m.status)}">
                         ${m.status === 'not_started' ? '•' : Math.round(m.actual_pct) + '%'}
                         ${people.length ? `<span class="mk-badge">👷${people.length > 1 ? people.length : ''}</span>` : ''}
                         ${S.liveStreams[m.id] ? '<span class="mk-live"></span>'
                            : S.streamByMosque[m.id] ? '<span class="mk-rec">🎥</span>' : ''}
                       </div>`,
                iconSize: [34, 34], iconAnchor: [17, 17], popupAnchor: [0, -18],
            });
            const mk = L.marker(ll, {icon, zIndexOffset: people.length ? 500 : 0,
                                     status: m.status, people: people.length}).addTo(layer);
            mk.bindPopup(() => _buildMapPopup(m, people), {maxWidth: 280, className: 'waqf-map-popup'});
            mk.on('popupopen', e => {
                const node = e.popup.getElement();
                node?.querySelector('.map-detail-btn')?.addEventListener('click', () => {
                    mk.closePopup(); loadMosqueDetail(m.id);
                });
                node?.querySelector('.map-stream-btn')?.addEventListener('click', () => {
                    mk.closePopup(); _openMosqueStream(m.id, m.name);
                });
            });
            S.mapMarkers[m.id] = mk;
            pts.push(ll);
        });
        if (fit && pts.length) S.map.fitBounds(pts, {padding: [50, 50], maxZoom: 12});
    }

    function _buildMapPopup(m, people) {
        const alert = S.allAlerts.find(a => a.mosque_id === m.id);
        const col = statusColor(m.status);
        return `
      <div style="direction:rtl;min-width:220px">
        <div style="font-size:13px;font-weight:800;color:#1B3A52">${esc(m.name)}</div>
        <div style="font-size:10px;color:#8C98A2;margin-bottom:9px">${esc(m.code)} · ${esc(m.package || '')}</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:9px">
          <div style="text-align:center;background:#FBF8F1;border:1px solid #EAE1CE;border-radius:8px;padding:6px 2px">
            <div style="font-size:15px;font-weight:800;color:${col}">${Math.round(m.actual_pct)}%</div>
            <div style="font-size:9px;color:#8C98A2">فعلي</div></div>
          <div style="text-align:center;background:#FBF8F1;border:1px solid #EAE1CE;border-radius:8px;padding:6px 2px">
            <div style="font-size:15px;font-weight:800;color:#1B3A52">${Math.round(m.planned_pct)}%</div>
            <div style="font-size:9px;color:#8C98A2">مخطط</div></div>
          <div style="text-align:center;background:#FBF8F1;border:1px solid #EAE1CE;border-radius:8px;padding:6px 2px">
            <div style="font-size:13px;font-weight:800;color:${m.days_delay > 0 ? '#D9493B' : '#1F9D6B'}">
              ${m.days_delay > 0 ? m.days_delay + ' يوم' : '✓'}</div>
            <div style="font-size:9px;color:#8C98A2">تأخير</div></div>
        </div>
        ${people.length ? `
          <div style="background:rgba(31,157,107,.07);border:1px solid rgba(31,157,107,.2);border-radius:8px;padding:7px 9px;margin-bottom:8px">
            <div style="font-size:10px;font-weight:800;color:#1F9D6B;margin-bottom:3px">👷 في الموقع الآن</div>
            ${people.map(p => `<div style="font-size:11px;color:#1B3A52">${esc(p.name)}
               <span style="color:#8C98A2">· دخول ${esc(p.checkin)} · منذ ${elapsedLabel(p.elapsed_min)}</span></div>`).join('')}
          </div>` : ''}
        ${alert ? `<div style="background:rgba(217,73,59,.07);border:1px solid rgba(217,73,59,.2);border-radius:8px;
             padding:6px 9px;margin-bottom:8px;font-size:11px;color:#D9493B">⚠ ${esc(alert.title)}</div>` : ''}
        ${S.liveStreams[m.id] ? `<button class="map-stream-btn" style="width:100%;padding:7px;background:#D9493B;color:#fff;
             border:none;border-radius:8px;font-size:11px;font-weight:700;cursor:pointer;margin-bottom:6px;font-family:inherit">
             ● مشاهدة البث المباشر</button>`
          : S.streamByMosque[m.id] ? `<button class="map-stream-btn" style="width:100%;padding:7px;background:#fff;color:#1B3A52;
             border:1px solid #EAE1CE;border-radius:8px;font-size:11px;font-weight:700;cursor:pointer;margin-bottom:6px;font-family:inherit">
             🎥 عرض آخر بث · ${esc(S.streamByMosque[m.id].start)}</button>` : ''}
        <button class="map-detail-btn" style="width:100%;padding:8px;background:#237292;color:#fff;border:none;
             border-radius:8px;font-size:11px;font-weight:700;cursor:pointer;font-family:inherit">عرض التفاصيل ›</button>
      </div>`;
    }

    function focusMosque(id) {
        const mk = S.mapMarkers[id];
        if (!S.map || !mk) return;
        if (S.cluster) {
            S.cluster.zoomToShowLayer(mk, () => {
                S.map.flyTo(mk.getLatLng(), Math.max(S.map.getZoom(), 14), {duration: .6});
                setTimeout(() => mk.openPopup(), 650);
            });
            return;
        }
        S.map.flyTo(mk.getLatLng(), Math.max(S.map.getZoom(), 13), {duration: .8});
        setTimeout(() => mk.openPopup(), 850);
    }

    function initMapFilters() {
        document.querySelectorAll('.mapx-filter').forEach(btn =>
            btn.addEventListener('click', function () {
                document.querySelectorAll('.mapx-filter').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                S.mapFilter = this.dataset.f;
                refreshMapMarkers(true);
            }));
        $('onsite-top-badge')?.addEventListener('click', () => {
            $('map-card')?.scrollIntoView({behavior: 'smooth', block: 'start'});
        });
    }

    function renderOnsite(list) {
        S.onsite = list || [];
        const n = S.onsite.length;
        const badge = $('onsite-count-badge');
        if (badge) badge.textContent = `${n} في الموقع`;
        const cnt = $('onsite-count');
        if (cnt) cnt.textContent = n;
        const box = $('onsite-list');
        if (!box) return;
        if (!n) {
            box.innerHTML = `<div class="mapx-empty">لا يوجد مستشارون في المواقع حالياً</div>`;
            return;
        }
        box.innerHTML = S.onsite.map(p => `
          <div class="onsite-card" data-mosque="${p.mosque_id || ''}">
            <div class="onsite-av">${esc((p.name || 'م')[0])}</div>
            <div class="onsite-info">
              <div class="onsite-nm">${esc(p.name)}</div>
              <div class="onsite-ms">🕌 ${esc(p.mosque)}${p.code ? ' · ' + esc(p.code) : ''}</div>
              <span class="onsite-flag ${p.validated || p.gps ? 'ok' : 'no'}">
                ${p.validated || p.gps ? '✓ موقع موثّق' : 'غير موثّق'}</span>
              ${p.today_target_min ? `
              <div class="onsite-day" title="مجموع ساعات اليوم على كل المساجد — المطلوب 8 ساعات">
                <div class="onsite-day-bar"><i style="width:${Math.min(100, p.today_min / p.today_target_min * 100)}%;
                     background:${p.today_min >= p.today_target_min ? 'var(--green)' : 'var(--primary)'}"></i></div>
                <span>اليوم ${elapsedLabel(p.today_min)} / 8س${p.today_mosques > 1 ? ` · ${p.today_mosques} مساجد` : ''}</span>
              </div>` : ''}
            </div>
            <div class="onsite-tm">
              <b>${esc(p.checkin)}</b>
              <span>منذ ${elapsedLabel(p.elapsed_min || 0)}</span>
            </div>
          </div>`).join('');
        box.querySelectorAll('.onsite-card').forEach(c =>
            c.addEventListener('click', () => {
                const id = parseInt(c.dataset.mosque);
                if (!id) return;
                box.querySelectorAll('.onsite-card').forEach(x => x.classList.remove('active'));
                c.classList.add('active');
                $('map-card')?.scrollIntoView({behavior: 'smooth', block: 'center'});
                focusMosque(id);
            }));
        const upd = $('onsite-updated');
        if (upd) upd.textContent = 'اضغط على المستشار لتحديد موقعه على الخريطة';
    }

    function _openMosqueStream(mosqueId, mosqueName) {
        const st = S.streamByMosque[mosqueId];
        const url = S.liveStreams[mosqueId] || st?.url;
        if (!url) return;
        openLiveStream({name: mosqueName, url, is_live: !!S.liveStreams[mosqueId], start: st?.start});
    }

    /* ══════════════════════════════════════════════════════════
       RISK MATRIX
       ══════════════════════════════════════════════════════════ */
    function renderRiskMatrix(points) {
        const container = $('risk-dots');
        if (!container) return;
        container.innerHTML = '';

        points.forEach(p => {
            const dot = document.createElement('div');
            dot.className = `risk-dot ${p.risk_level || 'medium'}`;
            // right = impact%, top = (100 - probability)%
            const size = Math.max(18, Math.min(30,
                18 + (p.size || 0) / 1000000 * 3));
            dot.style.cssText = `
        right:${p.impact}%;top:${100 - p.probability}%;
        width:${size}px;height:${size}px;
        transform:translate(50%,-50%)`;
            dot.title = `${p.mosque_code} — KPI ${p.kpi}%`;
            dot.textContent = (p.mosque_code || '').split('-').pop() || '';

            dot.addEventListener('click', () => loadMosqueDetail(p.mosque_id));
            container.appendChild(dot);
        });
    }

    /* ══════════════════════════════════════════════════════════
       FORECAST ENGINE
       ══════════════════════════════════════════════════════════ */
    function renderForecast(rows) {
        const el = $('forecast-rows');
        if (!el) return;

        if (!rows.length) {
            el.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text3)">
        لا توجد بيانات توقعات</div>`;
            return;
        }

        el.innerHTML = rows.map(r => {
            const late = r.variance_days > 0;
            const conf = r.confidence_pct || 0;
            const confColor = conf >= 80 ? 'var(--green)' :
                conf >= 60 ? 'var(--orange)' : 'var(--red)';
            return `
        <div style="display:grid;grid-template-columns:1fr 80px 80px 60px 100px;
                    align-items:center;gap:6px;padding:9px 14px;
                    border-bottom:1px solid var(--border);cursor:pointer;
                    transition:background .12s"
             onclick="loadMosqueDetailGlobal(${r.mosque_id})"
             onmouseover="this.style.background='var(--surface2)'"
             onmouseout="this.style.background=''">
          <div>
            <div style="font-size:12px;font-weight:600;color:var(--text1)">
              ${truncate(r.mosque_name, 20)}
            </div>
            <div style="font-size:10px;color:var(--text3);font-family:monospace">
              ${r.mosque_code}
            </div>
          </div>
          <div style="font-size:10px;color:var(--text3);font-family:monospace">
            ${r.planned_finish ? r.planned_finish.substring(0, 10) : '—'}
          </div>
          <div style="font-size:10px;font-weight:700;font-family:monospace;
                      color:${late ? 'var(--red)' : 'var(--green)'}">
            ${r.forecast_finish ? r.forecast_finish.substring(0, 10) : '—'}
          </div>
          <div style="font-size:10px;font-weight:700;text-align:center;
                      color:${late ? 'var(--red)' : 'var(--green)'}">
            ${late ? '+' : ''}${r.variance_days}د
          </div>
          <div style="display:flex;align-items:center;gap:6px">
            <div style="flex:1;height:5px;background:var(--surface3);
                        border-radius:3px;overflow:hidden">
              <div style="width:${conf}%;height:100%;border-radius:3px;
                          background:${confColor};transition:width 1s ease"></div>
            </div>
            <span style="font-size:9px;font-weight:700;color:${confColor}">
              ${conf}%
            </span>
          </div>
        </div>`;
        }).join('');
    }

    /* ══════════════════════════════════════════════════════════
       QUALITY INTELLIGENCE
       ══════════════════════════════════════════════════════════ */
    function renderQuality(d) {
        const el = $('quality-panel');
        if (!el || !d) return;

        const score = d.quality_score || 0;
        const ratingLabel = score >= 85 ? 'ممتاز' : score >= 70 ? 'جيد' :
            score >= 55 ? 'يحتاج تحسين' : 'حرج';
        const ratingColor = score >= 85 ? 'var(--green)' : score >= 70 ? 'var(--primary)' :
            score >= 55 ? 'var(--orange)' : 'var(--red)';

        el.innerHTML = `
      <div style="display:grid;grid-template-columns:auto 1fr;gap:14px">
        <div style="display:flex;flex-direction:column;align-items:center;
                    justify-content:center;padding:16px 20px;
                    background:linear-gradient(135deg,rgba(35,114,146,.05),rgba(27,58,82,.03));
                    border-radius:var(--r-lg);border:1px solid var(--border)">
          <div style="font-size:38px;font-weight:800;color:${ratingColor};line-height:1">
            ${Math.round(score)}
          </div>
          <div style="font-size:10px;color:var(--text3);margin-top:4px">Quality Score</div>
          <div style="margin-top:8px;font-size:9px;font-weight:700;
                      background:${ratingColor}18;color:${ratingColor};
                      padding:3px 10px;border-radius:999px">${ratingLabel}</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          ${[
            ['NCR مفتوح', d.ncr_total || 0, 'var(--red)'],
            ['إعادة العمل', (d.itp_rate ? (100 - d.itp_rate).toFixed(0) + '%' : '—'), 'var(--orange)'],
            ['فحوصات فاشلة', d.failed_inspections || 0, 'var(--red)'],
            ['مشاكل مفتوحة', d.open_issues || 0, 'var(--orange)'],
        ].map(([lbl, val, col]) => `
            <div style="background:var(--surface2);border-radius:var(--r-md);
                        padding:10px 12px;border:1px solid var(--border)">
              <div style="font-size:17px;font-weight:800;color:${col}">${val}</div>
              <div style="font-size:10px;color:var(--text3);margin-top:2px">${lbl}</div>
            </div>`).join('')}
        </div>
      </div>`;
    }

    /* ══════════════════════════════════════════════════════════
       AI INSIGHTS
       ══════════════════════════════════════════════════════════ */
    function renderAIInsights(data) {
        const el = $('merged-panel');
        if (!el) return;

        const insights = data?.insights || [];
        const src = data?.source || 'computed';
        const upd = data?.last_updated || '';

        // إحضار بيانات الجودة
        apiGet('/dashboard/api/quality').then(quality => {
            const q = quality || {};
            const score = q.quality_score || 0;
            const scoreColor = score >= 85 ? 'var(--green)' : score >= 70 ? 'var(--primary)' :
                score >= 55 ? 'var(--orange)' : 'var(--red)';
            const scoreLabel = score >= 85 ? 'ممتاز' : score >= 70 ? 'جيد' :
                score >= 55 ? 'يحتاج تحسين' : 'حرج';

            const typeColor = {
                risk: 'var(--red)', opportunity: 'var(--green)',
                action: 'var(--gold)', info: 'var(--primary)', phase: 'var(--primary)',
            };

            el.innerHTML = `
      <!-- Tabs -->
      <div style="display:flex;border-bottom:1px solid var(--border);margin-bottom:14px">
        <button class="merged-tab active" data-panel="insights">
          🤖 تحليلات ذكية
          ${src === 'ai_center' ? '<span style="font-size:9px;color:var(--primary);margin-right:4px">AI</span>' : ''}
        </button>
        <button class="merged-tab" data-panel="quality">🔍 جودة التنفيذ</button>
        <button class="merged-tab" data-panel="forecast">📊 توقعات الإنجاز</button>
      </div>

      <!-- AI Insights -->
      <div class="merged-panel-content active" data-panel-content="insights">
        ${upd ? `<div style="font-size:10px;color:var(--text3);margin-bottom:10px;text-align:left">
          آخر تحديث: ${upd.substring(0, 16)}</div>` : ''}
        ${insights.length ? insights.slice(0, 5).map(ins => `
          <div class="ai-insight-item"
               style="${ins.mosque_id ? 'cursor:pointer' : ''}"
               ${ins.mosque_id ? `onclick="loadMosqueDetailGlobal(${ins.mosque_id})"` : ''}>
            <div class="ai-insight-icon">${ins.icon || '📊'}</div>
            <div class="ai-insight-text">
              <strong style="color:${typeColor[ins.type] || 'var(--text1)'}">
                ${ins.title}:
              </strong>
              <span>${ins.body || ''}</span>
              ${ins.mosque_name ? `<span style="font-size:10px;color:var(--text3);margin-right:6px">
                — ${ins.mosque_name}</span>` : ''}
              ${ins.action_label ? `
                <button onclick="event.stopPropagation();
                  ${ins.mosque_id ? `loadMosqueDetailGlobal(${ins.mosque_id})` : ''}"
                  style="font-size:10px;font-weight:700;padding:2px 10px;border-radius:999px;
                  border:1px solid var(--border);background:transparent;color:var(--primary);
                  cursor:pointer;margin-right:8px;margin-top:4px;display:inline-block">
                  ${ins.action_label} ›
                </button>` : ''}
            </div>
          </div>`).join('')
                : `<div style="padding:16px;text-align:center;color:var(--text3)">
           لا توجد تحليلات متاحة حالياً</div>`}
      </div>

      <!-- Quality -->
      <div class="merged-panel-content" data-panel-content="quality">
        <div style="display:grid;grid-template-columns:auto 1fr;gap:14px;margin-bottom:14px">
          <div style="display:flex;flex-direction:column;align-items:center;
            justify-content:center;padding:20px;background:${scoreColor}12;
            border-radius:var(--r-lg);border:1px solid ${scoreColor}30;min-width:100px">
            <div style="font-size:42px;font-weight:800;color:${scoreColor};line-height:1">
              ${Math.round(score)}
            </div>
            <div style="font-size:10px;color:var(--text3);margin-top:4px">Quality Score</div>
            <div style="margin-top:8px;font-size:9px;font-weight:700;
              background:${scoreColor}18;color:${scoreColor};
              padding:3px 10px;border-radius:999px">${scoreLabel}</div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
            ${[
                ['NCR مفتوح', q.ncr_total || 0, 'var(--red)'],
                ['إعادة العمل', q.itp_rate ? (100 - q.itp_rate).toFixed(0) + '%' : '—', 'var(--orange)'],
                ['فحوصات فاشلة', q.failed_inspections || 0, 'var(--red)'],
                ['مشاكل مفتوحة', q.open_issues || 0, 'var(--orange)'],
            ].map(([lbl, val, col]) => `
              <div style="background:var(--surface2);border-radius:var(--r-md);
                padding:10px 12px;border:1px solid var(--border)">
                <div style="font-size:17px;font-weight:800;color:${col}">${val}</div>
                <div style="font-size:10px;color:var(--text3);margin-top:2px">${lbl}</div>
              </div>`).join('')}
          </div>
        </div>
      </div>

      <!-- Forecast -->
      <div class="merged-panel-content" data-panel-content="forecast">
        <div id="forecast-rows-merged">
          <div style="text-align:center;padding:20px">
            <div class="loading-spinner" style="width:18px;height:18px;margin:0 auto"></div>
          </div>
        </div>
      </div>`;

            // Tab events
            el.querySelectorAll('.merged-tab').forEach(btn => {
                btn.addEventListener('click', function () {
                    el.querySelectorAll('.merged-tab').forEach(b => b.classList.remove('active'));
                    el.querySelectorAll('.merged-panel-content').forEach(p => p.classList.remove('active'));
                    this.classList.add('active');
                    el.querySelector(`[data-panel-content="${this.dataset.panel}"]`)?.classList.add('active');
                    if (this.dataset.panel === 'forecast') loadForecast();
                });
            });
        });
    }

    /* ══════════════════════════════════════════════════════════
       CONTRACTORS
       ══════════════════════════════════════════════════════════ */
    function renderContractors(contractors) {
        const el = $('contractor-list');
        if (!el) return;

        if (!contractors.length) {
            el.innerHTML = `<div style="padding:16px;text-align:center;color:var(--text3)">
        لا توجد بيانات مقاولين</div>`;
            return;
        }

        const rankClass = ['r1', 'r2', 'r3'];
        el.innerHTML = contractors.slice(0, 6).map((c, i) => {
            const barColor = c.avg_kpi >= 70 ? 'var(--green)' :
                c.avg_kpi >= 50 ? 'var(--orange)' : 'var(--red)';
            const kpiClass = c.avg_kpi >= 70 ? 'good' : c.avg_kpi >= 50 ? 'warn' : 'bad';
            return `
        <div class="contractor-row">
          <div class="contractor-rank ${rankClass[i] || 'rank-n'}">${i + 1}</div>
          <div style="flex:1;min-width:0">
            <div class="contractor-name">${truncate(c.name, 20)}</div>
            <div style="font-size:10px;color:var(--text3)">
              ${c.mosque_count}م · NCR:${c.ncr_total} · CO:${c.co_count}
            </div>
          </div>
          <div class="contractor-kpi ${kpiClass}">${c.avg_kpi}%</div>
          <div class="contractor-bar-wrap">
            <div class="contractor-bar-fill"
                 style="width:${c.avg_kpi}%;background:${barColor};
                        transition:width 1s ease"></div>
          </div>
        </div>`;
        }).join('');
    }

    /* ══════════════════════════════════════════════════════════
       CRITICAL PROJECTS
       ══════════════════════════════════════════════════════════ */
    function renderCriticalProjects(mosques) {
        const el = $('critical-projects-list');
        const badge = $('critical-count-badge');
        if (!el) return;

        const critical = mosques
            .filter(m => m.overall_kpi > 0 && m.overall_kpi < 60)
            .sort((a, b) => a.overall_kpi - b.overall_kpi)
            .slice(0, 5);

        if (badge) badge.textContent = critical.length + ' مشاريع';

        if (!critical.length) {
            el.innerHTML = `<div style="text-align:center;padding:24px;color:var(--green);
        font-size:12px">✓ لا توجد مشاريع حرجة</div>`;
            return;
        }

        el.innerHTML = critical.map(m => {
            const level = m.overall_kpi < 40 ? 'critical' : 'high';
            return `
        <div class="critical-item" onclick="loadMosqueDetailGlobal(${m.id})">
          <div class="critical-item-top">
            <span class="critical-item-name">${truncate(m.name, 22)} — ${m.code}</span>
            <span class="critical-item-level ${level}">
              ${level === 'critical' ? 'حرج' : 'مرتفع'}
            </span>
          </div>
          <div class="critical-item-reason">
            ${m.days_delay > 0 ? `تأخير ${m.days_delay} يوم · ` : ''}
            ${m.overall_kpi < 40 ? 'يحتاج تدخل فوري' : 'أداء منخفض'}
          </div>
          <div class="critical-item-kpi"
               style="color:${m.overall_kpi < 40 ? 'var(--red)' : 'var(--orange)'}">
            ${m.overall_kpi}%
          </div>
        </div>`;
        }).join('');
    }

    /* ══════════════════════════════════════════════════════════
       SIDEBAR
       ══════════════════════════════════════════════════════════ */
    function buildSidebar(pkgs) {
        const container = $('sb-packages');
        if (!container) return;
        container.innerHTML = '';
        pkgs.forEach(pkg => {
            const color = pkg.is_current ? '#237292' : pkg.is_past ? '#1F9D6B' : '#B9AE96';
            const card = document.createElement('div');
            card.className = `sb-pkg-card ${pkg.is_current ? 'current' : pkg.is_past ? 'past' : 'future'}`;
            card.dataset.pkgId = pkg.id;
            card.innerHTML = `
      <div class="sb-pkg-card-inner">
        <div class="sb-pkg-top">
          <div class="sb-pkg-dot" style="background:${color}"></div>
          <div style="flex:1;min-width:0">
            <div class="sb-pkg-code">${esc(pkg.code || '')}</div>
            <div class="sb-pkg-name">${esc(pkg.name)}</div>
          </div>
          ${pkg.is_current ? '<div class="sb-pkg-live">● الحالية</div>' : ''}
          ${pkg.is_past ? '<div class="sb-pkg-done">✓</div>' : ''}
        </div>
        <div class="sb-pkg-stats">
          <div class="sb-pkg-stat"><span class="sb-pkg-stat-val">${pkg.avg_kpi}%</span><span class="sb-pkg-stat-lbl">إنجاز</span></div>
          <div class="sb-pkg-stat"><span class="sb-pkg-stat-val">${pkg.mosque_count}</span><span class="sb-pkg-stat-lbl">مسجد</span></div>
          ${pkg.delayed_count ? `<div class="sb-pkg-stat"><span class="sb-pkg-stat-val" style="color:var(--red)">${pkg.delayed_count}</span><span class="sb-pkg-stat-lbl">حرج</span></div>` : ''}
        </div>
        <div class="sb-pkg-bar"><div class="sb-pkg-bar-fill" style="width:${Math.min(100, pkg.avg_kpi)}%;background:${color}"></div></div>
      </div>`;
            card.addEventListener('click', () => { S.scopePkgId = pkg.id; applyScope(); refreshMapMarkers(true); });
            container.appendChild(card);
        });
        $('sb-scope-all')?.addEventListener('click', () => { S.scopePkgId = null; applyScope(); refreshMapMarkers(true); });
    }

    /* ══════════════════════════════════════════════════════════
       GLOBAL SEARCH
       ══════════════════════════════════════════════════════════ */
    function initSearch() {
        const input = $('global-search');
        const dropdown = $('search-dropdown');
        if (!input || !dropdown) return;

        input.addEventListener('input', function () {
            const q = this.value.trim().toLowerCase();
            if (q.length < 2) {
                dropdown.classList.remove('show');
                return;
            }

            const results = [];
            S.mosques.filter(m =>
                m.name?.toLowerCase().includes(q) ||
                m.code?.toLowerCase().includes(q)
            ).slice(0, 6).forEach(m => results.push({
                type: 'mosque', label: m.name,
                meta: `${m.code} · الإنجاز ${Math.round(m.actual_pct || 0)}%`,
                color: statusColor(m.status), id: m.id,
            }));

            S.packages.filter(p =>
                p.name?.toLowerCase().includes(q) ||
                p.code?.toLowerCase().includes(q)
            ).slice(0, 3).forEach(p => results.push({
                type: 'package', label: p.name,
                meta: `${p.mosque_count} مساجد · الإنجاز ${p.avg_kpi}%`,
                color: 'var(--primary)', id: p.id,
            }));

            dropdown.innerHTML = results.length
                ? results.map(r => `
            <div class="search-item" data-type="${r.type}" data-id="${r.id}">
              <div class="search-item-dot" style="background:${r.color}"></div>
              <div class="search-item-body">
                <div class="search-item-label">${r.label}</div>
                <div class="search-item-meta">${r.meta}</div>
              </div>
              <div class="search-item-icon">
                ${r.type === 'mosque' ? '🕌' : '📦'}
              </div>
            </div>`).join('')
                : '<div class="search-empty">لا توجد نتائج</div>';

            dropdown.querySelectorAll('.search-item').forEach(item => {
                item.addEventListener('click', function () {
                    dropdown.classList.remove('show');
                    input.value = '';
                    if (this.dataset.type === 'mosque')
                        loadMosqueDetail(parseInt(this.dataset.id));
                    else { S.scopePkgId = parseInt(this.dataset.id); applyScope(); refreshMapMarkers(true); }
                });
            });
            dropdown.classList.add('show');
        });

        input.addEventListener('keydown', e => {
            if (e.key === 'Escape') {
                dropdown.classList.remove('show');
                input.value = '';
            }
        });
        document.addEventListener('click', e => {
            if (!input.contains(e.target) && !dropdown.contains(e.target))
                dropdown.classList.remove('show');
        });
    }

    /* ══════════════════════════════════════════════════════════
       MOSQUE DETAIL — PRESERVED WITH ALL FEATURES
       ══════════════════════════════════════════════════════════ */
    async function loadMosqueDetail(mosqueId, silent) {
        S.activeMosqueId = mosqueId;
        const mosque = S.mosques.find(m => m.id === mosqueId);

        if (mosque) {
            $('topbar-title').textContent = mosque.name;
            $('topbar-sub').textContent =
                `${mosque.code} · ${mosque.package || ''} · ${stateLabel(mosque.state)} · الإنجاز ${Math.round(mosque.actual_pct || 0)}%` +
                (mosque.days_delay > 0 ? ` · ⚠ تأخير ${mosque.days_delay} يوم` : '');
        }

        const content = $('mosque-detail-content');
        if (content && !silent) {
            content.innerHTML = `
        <div style="padding:40px;text-align:center">
          <div class="loading-spinner" style="width:32px;height:32px;margin:0 auto"></div>
          <div style="margin-top:12px;color:var(--text3);font-size:12px">
            جاري تحميل بيانات المسجد...
          </div>
        </div>`;
        }

        const data = await apiGet(`/dashboard/api/mosque/${mosqueId}`);
        if (!data || !data.mosque) return;

        const m = data.mosque;
        S.mosqueContext = {
            name: m.name,
            overall_kpi: m.overall_kpi,
            financial_pct: m.financial_kpi,
            time_pct: m.time_kpi,
            days_delay: m.days_delay,
        };

        if (content) {
            content.innerHTML = buildMosqueDetailHTML(data);
            initMosqueDetailEvents(data);
            drawKpiRings(m);
            drawBoqChart(data.boq_categories);
        }

        if (!silent) $('section-mosque')?.scrollIntoView({behavior: 'smooth', block: 'start'});
    }

    window.toggleBOQCat = function (id) {
        const el = document.getElementById(id);
        if (!el) return;
        const arrow = document.getElementById(`${id}-arrow`);
        const open = el.style.display !== 'none';
        document.querySelectorAll('[id^="boq-cat-"]').forEach(e => {
            if (e.id !== id) {
                e.style.display = 'none';
                const a = document.getElementById(`${e.id}-arrow`);
                if (a) a.style.transform = '';
            }
        });
        el.style.display = open ? 'none' : 'block';
        if (arrow) arrow.style.transform = open ? '' : 'rotate(180deg)';
    };
    function buildBOQHTML(data) {
 const cats = data.boq_categories || [];
  if (!cats.length) return `
    <div style="padding:40px;text-align:center;color:var(--text3)">
      <div style="font-size:32px;margin-bottom:8px">📋</div>
      لا توجد بنود كميات
    </div>`;

  const total_contracted = cats.reduce((s,c) => s + c.contracted, 0);
  const total_executed   = cats.reduce((s,c) => s + c.executed, 0);
  const total_pct = total_contracted > 0
    ? Math.round(total_executed / total_contracted * 100) : 0;

  return `
    <!-- Summary bar -->
    <div style="background:linear-gradient(135deg,var(--navy),var(--navy-deep));
      border-radius:var(--r-lg);padding:16px 20px;margin-bottom:16px;color:#fff">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <div style="font-size:13px;font-weight:700">إجمالي جداول الكميات</div>
        <div style="font-size:20px;font-weight:800;color:var(--gold)">${total_pct}%</div>
      </div>
      <div style="height:8px;background:rgba(255,255,255,0.15);border-radius:4px;overflow:hidden">
        <div style="width:${total_pct}%;height:100%;border-radius:4px;
          background:linear-gradient(90deg,var(--primary),var(--gold));
          transition:width 1.2s ease"></div>
      </div>
      <div style="display:flex;justify-content:space-between;margin-top:8px;
        font-size:10px;color:rgba(255,255,255,0.5)">
        <span>الكمية الكلية: ${mny(total_contracted)}</span>
        <span>منفذ: <span style="color:var(--green);font-weight:700">${mny(total_executed)}</span></span>
      </div>
    </div>

    <!-- Chart -->
    <div style="position:relative;width:100%;height:180px;margin-bottom:16px">
      <canvas id="boq-chart" class="fin-block"></canvas>
    </div>

    <!-- Categories -->
    <div style="display:flex;flex-direction:column;gap:8px">
      ${cats.map((cat, idx) => {
        const pv = cat.contracted > 0
          ? Math.round(cat.executed / cat.contracted * 100) : 0;
        const barColor = pv >= 90 ? 'var(--orange)' :
                         pv >= 60 ? 'var(--primary)' : 'var(--green)';
        const catId = `boq-cat-${idx}`;
        const lines = cat.boq_lines || [];

        return `
          <div style="border:1px solid var(--border);border-radius:var(--r-lg);
            overflow:hidden;background:var(--surface);
            transition:box-shadow var(--t-base)">

            <!-- Category Header -->
            <div onclick="toggleBOQCat('${catId}')"
              style="display:flex;align-items:center;gap:14px;
                padding:14px 18px;cursor:pointer;background:var(--surface2);
                transition:background var(--t-fast)"
              onmouseover="this.style.background='var(--surface3)'"
              onmouseout="this.style.background='var(--surface2)'">

              <!-- Icon -->
              <div style="width:38px;height:38px;border-radius:10px;flex-shrink:0;
                background:${barColor}18;border:1px solid ${barColor}30;
                display:flex;align-items:center;justify-content:center;
                font-size:16px">
                🏗
              </div>

              <!-- Info -->
              <div style="flex:1;min-width:0">
                <div style="font-size:13px;font-weight:700;color:var(--text1);
                  margin-bottom:6px">${cat.name}</div>
                <div style="display:flex;align-items:center;gap:8px">
                  <div style="flex:1;height:6px;background:var(--surface3);
                    border-radius:3px;overflow:hidden">
                    <div style="width:${pv}%;height:100%;background:${barColor};
                      border-radius:3px;transition:width 1.2s ease"></div>
                  </div>
                  <span style="font-size:11px;font-weight:800;
                    color:${barColor};min-width:35px">${pv}%</span>
                </div>
              </div>

              <!-- Values -->
              <div style="text-align:left;min-width:110px">
                <div style="font-size:10px;color:var(--text3)">منفذ</div>
                <div style="font-size:13px;font-weight:700;color:var(--primary)">
                  ${mny(cat.executed)}
                </div>
              </div>
              <div style="text-align:left;min-width:110px">
                <div style="font-size:10px;color:var(--text3)">الكلي</div>
                <div style="font-size:13px;font-weight:600;color:var(--text2)">
                  ${mny(cat.contracted)}
                </div>
              </div>

              <!-- Count badge -->
              ${lines.length ? `
                <div style="background:rgba(35,114,146,0.1);color:var(--primary);
                  font-size:10px;font-weight:700;padding:3px 9px;
                  border-radius:999px;flex-shrink:0">
                  ${lines.length} بند
                </div>` : ''}

              <!-- Arrow -->
              <div id="${catId}-arrow"
                style="font-size:14px;color:var(--text4);
                  transition:transform var(--t-base);flex-shrink:0">▾</div>
            </div>

            <!-- BOQ Lines -->
            <div id="${catId}" style="display:none;border-top:1px solid var(--border)">
              ${lines.length ? `
                <div style="overflow-x:auto">
                  <table style="width:100%;border-collapse:collapse">
                    <thead>
                      <tr style="background:var(--surface2)">
                        <th style="padding:9px 14px;text-align:right;font-size:10px;
                          font-weight:700;color:var(--text3);white-space:nowrap">الكود</th>
                        <th style="padding:9px 14px;text-align:right;font-size:10px;
                          font-weight:700;color:var(--text3)">الوصف</th>
                        <th style="padding:9px 14px;text-align:center;font-size:10px;
                          font-weight:700;color:var(--text3)">الوحدة</th>
                        <th style="padding:9px 14px;text-align:center;font-size:10px;
                          font-weight:700;color:var(--text3)">الكلي</th>
                        <th style="padding:9px 14px;text-align:center;font-size:10px;
                          font-weight:700;color:var(--text3)">منفذ</th>
                        <th style="padding:9px 14px;text-align:left;font-size:10px;
                          font-weight:700;color:var(--text3)">السعر</th>
                        <th style="padding:9px 14px;text-align:right;font-size:10px;
                          font-weight:700;color:var(--text3)">نسبة</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${lines.map((line, li) => {
                        const lpv = line.contracted_qty > 0
                          ? Math.round(line.executed_qty / line.contracted_qty * 100) : 0;
                        const lColor = lpv >= 90 ? 'var(--orange)' :
                                       lpv >= 60 ? 'var(--primary)' : 'var(--green)';
                        return `
                          <tr style="border-bottom:1px solid var(--border);
                            transition:background var(--t-fast)"
                            onmouseover="this.style.background='var(--surface2)'"
                            onmouseout="this.style.background=''">
                            <td style="padding:9px 14px">
                              <span style="font-family:'IBM Plex Mono',monospace;
                                font-size:10px;color:var(--primary);font-weight:600">
                                ${line.code || '—'}
                              </span>
                            </td>
                            <td style="padding:9px 14px;font-size:12px;color:var(--text2);
                              max-width:200px">
                              ${line.description || '—'}
                            </td>
                            <td style="padding:9px 14px;text-align:center;
                              font-size:11px;color:var(--text3)">
                              ${line.unit || '—'}
                            </td>
                            <td style="padding:9px 14px;text-align:center;
                              font-size:12px;color:var(--text2)">
                              ${line.contracted_qty || 0}
                            </td>
                            <td style="padding:9px 14px;text-align:center;
                              font-size:12px;font-weight:700;color:var(--primary)">
                              ${line.executed_qty || 0}
                            </td>
                            <td style="padding:9px 14px;text-align:left;
                              font-size:11px;color:var(--text2);
                              font-family:'IBM Plex Mono',monospace">
                              ${fmt(line.unit_price || 0)}
                            </td>
                            <td style="padding:9px 14px">
                              <div style="display:flex;align-items:center;gap:6px">
                                <div style="width:50px;height:5px;background:var(--surface3);
                                  border-radius:3px;overflow:hidden">
                                  <div style="width:${lpv}%;height:100%;
                                    background:${lColor};border-radius:3px;
                                    transition:width 1s ease"></div>
                                </div>
                                <span style="font-size:10px;font-weight:700;
                                  color:${lColor};min-width:28px">${lpv}%</span>
                              </div>
                            </td>
                          </tr>`;
                      }).join('')}
                    </tbody>
                    <!-- Footer totals -->
                    <tfoot>
                      <tr style="background:var(--surface2);font-weight:700">
                        <td colspan="3" style="padding:9px 14px;font-size:11px;
                          color:var(--text1)">الإجمالي</td>
                        <td style="padding:9px 14px;text-align:center;
                          font-size:11px;color:var(--text2)">—</td>
                        <td style="padding:9px 14px;text-align:center;
                          font-size:11px;color:var(--primary)">—</td>
                        <td style="padding:9px 14px;text-align:left;
                          font-size:12px;color:var(--primary)">
                          ${mny(cat.contracted)}
                        </td>
                        <td style="padding:9px 14px">
                          <span style="font-size:11px;font-weight:800;
                            color:${barColor}">${pv}%</span>
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>` : `
                <div style="padding:20px;text-align:center;color:var(--text3);font-size:12px">
                  <div style="font-size:24px;margin-bottom:6px">📋</div>
                  لا توجد بنود تفصيلية في هذه الفئة
                </div>`}
            </div>
          </div>`;
      }).join('')}
    </div>`;
}

    function buildMosqueDetailHTML(data) {
        const m = data.mosque;
        const ai = data.ai || {};
        const pendingCerts = data.certs.filter(c =>
            ['submitted', 'consultant_approved'].includes(c.state)).length;
        const pendingCOs = data.change_orders.filter(co => co.state === 'review').length;
        const totalCertVal = data.certs.reduce((s, c) => s + (c.total_value || 0), 0);

        return `
<!-- Hero -->
<div class="mosque-hero">
  <div class="mosque-hero-main">
    <div class="mosque-hero-name">${m.name}</div>
    <div class="mosque-hero-meta">
      ${m.code} · ${m.city} ${m.district ? '· ' + m.district : ''}
    </div>
    <div class="mosque-hero-tags">
      <span class="mosque-hero-tag state">${stateLabel(m.state)}</span>
      ${m.days_delay > 0
            ? `<span class="mosque-hero-tag delay">⚠ تأخير ${m.days_delay} يوم</span>`
            : `<span class="mosque-hero-tag ok">✓ في الموعد</span>`}
      ${m.contractor
            ? `<span class="mosque-hero-tag company">${m.contractor}</span>` : ''}
      ${ai.risk_level
            ? `<span class="mosque-hero-tag" style="background:rgba(232,85,85,.2);
             color:#FCA5A5">⚖ خطر ${ai.risk_level === 'critical' ? 'حرج' :
                ai.risk_level === 'high' ? 'مرتفع' : 'متوسط'}</span>` : ''}
    </div>
  </div>
 
</div>

${ai.forecast_finish ? `
<!-- AI Forecast mini-bar -->
<div style="background:rgba(35,114,146,.07);border:1px solid rgba(35,114,146,.15);
            border-radius:var(--r-md);padding:10px 16px;margin-bottom:14px;
            display:flex;align-items:center;gap:14px;flex-wrap:wrap">
  <div class="ai-badge" style="font-size:10px">🤖 AI Forecast</div>
  <span style="font-size:11px;color:var(--text2)">
    الإنجاز المتوقع: <strong>${ai.forecast_finish.substring(0, 10)}</strong>
  </span>
  ${ai.variance_days > 0
            ? `<span style="font-size:11px;color:var(--red);font-weight:700">
       انحراف +${ai.variance_days} يوم</span>` : ''}
  ${ai.confidence_pct
            ? `<span style="font-size:11px;color:var(--text3)">
       ثقة ${ai.confidence_pct}%</span>` : ''}
</div>` : ''}

<!-- KPI Rings -->
<div class="card" style="margin-bottom:14px">
  <div class="card-hdr">
    <div class="card-title">مؤشرات الأداء الرئيسية</div>
    <span style="font-size:11px;background:rgba(200,164,84,.1);
                 color:var(--gold);padding:2px 10px;border-radius:999px;font-weight:600">
      قيمة العقد: ${mny(m.contract_value)}
    </span>
    ${m.progress_parts ? `<span class="kpi-parts">
      مهام معتمدة <b>${m.progress_parts.task_done || 0}/${m.progress_parts.task_total || 0}</b>
      · أوامر مقبولة <b>${m.progress_parts.wo_done || 0}/${m.progress_parts.wo_total || 0}</b>
      · الكميات المنفذة <b>${m.qty_pct || 0}%</b> (للمعلومية)</span>` : ''}
  </div>
  <div class="card-body">
    <div class="kpi-rings">
      <div class="kpi-ring-wrap">
        <canvas id="ring-financial" width="72" height="72"></canvas>
        <div class="kpi-ring-label">الإنجاز الفعلي</div>
        <div class="kpi-ring-val" style="color:var(--gold)">${pct(m.financial_kpi)}</div>
      </div>
      <div class="kpi-ring-wrap">
        <canvas id="ring-overall" width="88" height="88"></canvas>
        <div class="kpi-ring-label" style="font-weight:700" title="60% الالتزام بالجدول · 25% الحضور اليومي · 15% الالتزام بالمدة">مؤشر الأداء العام</div>
        <div class="kpi-ring-val" style="font-size:16px;color:var(--primary)">
          ${pct(m.overall_kpi)}
        </div>
      </div>
      <div class="kpi-ring-wrap">
        <canvas id="ring-time" width="72" height="72"></canvas>
        <div class="kpi-ring-label">المخطط حتى اليوم</div>
        <div class="kpi-ring-val" style="color:var(--green)">${pct(m.time_kpi)}</div>
      </div>
      <div class="kpi-ring-wrap">
        <canvas id="ring-visit" width="72" height="72"></canvas>
        <div class="kpi-ring-label" title="حضور يومي 8 ساعات من الأحد إلى الخميس عدا الإجازات الرسمية">الالتزام بالحضور اليومي</div>
        <div class="kpi-ring-val" style="color:var(--primary-l)">
          ${pct(m.visit_compliance)}
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Tabs -->
<div class="tab-row">
  <button class="tab-btn active" data-tab="boq">جداول الكميات</button>
  <button class="tab-btn" data-tab="tasks">المهام</button>
  <button class="tab-btn" data-tab="financial">
    المالي
    ${pendingCerts > 0 ? `<span class="tab-badge red">${pendingCerts}</span>` : ''}
    ${pendingCOs > 0 ? `<span class="tab-badge orange">${pendingCOs}</span>` : ''}
  </button>

  <button class="tab-btn" data-tab="works">
    الأعمال المنفذة
    ${(data.work_orders || []).length ? `<span class="tab-badge navy">${data.work_orders.length}</span>` : ''}
  </button>
  <button class="tab-btn" data-tab="samples">
    عينات المواد
    ${(data.submittals || []).filter(x => ['submitted','submitted_chief','submitted_waqf'].includes(x.state)).length
        ? `<span class="tab-badge orange">${data.submittals.filter(x => ['submitted','submitted_chief','submitted_waqf'].includes(x.state)).length}</span>` : ''}
  </button>
  <button class="tab-btn" data-tab="visits">الزيارات والحضور</button>
</div>

<!-- Work orders: documented executed works with quantities -->
<div class="tab-panel" data-tab-panel="works">${buildWorkOrdersHTML(data.work_orders || [])}</div>

<!-- Material samples -->
<div class="tab-panel" data-tab-panel="samples">${buildSubmittalsHTML(data.submittals || [])}</div>

<!-- Tasks -->
<div class="tab-panel" data-tab-panel="tasks">
  <div class="task-list">${buildTasksHTML(data.tasks)}</div>
</div>

<!-- Financial -->
<div class="tab-panel" data-tab-panel="financial">
  <div class="fin-kpi-row">
    <div class="fin-kpi-card">
      <div class="fin-kpi-val">${mny(totalCertVal)}</div>
      <div class="fin-kpi-label">إجمالي المستخلصات</div>
    </div>
    <div class="fin-kpi-card">
      <div class="fin-kpi-val"
           style="color:${pendingCerts > 0 ? 'var(--red)' : 'var(--green)'}">
        ${pendingCerts}
      </div>
      <div class="fin-kpi-label">بانتظار الاعتماد</div>
    </div>
    <div class="fin-kpi-card">
      <div class="fin-kpi-val" style="color:var(--gold)">
        ${fmt(data.change_orders.reduce((s, c) => s + (c.amount || 0), 0))}
      </div>
      <div class="fin-kpi-label">قيمة أوامر التغيير</div>
    </div>
  </div>
  <div class="section-row">
    <div class="section-title-txt">المستخلصات</div>
    <div class="section-line"></div>
    <div class="section-badge">${data.certs.length}</div>
  </div>
  <div class="cert-list">${buildCertsHTML(data.certs)}</div>
  <div class="section-row" style="margin-top:16px">
    <div class="section-title-txt">أوامر التغيير</div>
    <div class="section-line"></div>
    <div class="section-badge">${data.change_orders.length}</div>
  </div>
  <div class="cert-list">${buildCOHTML(data.change_orders)}</div>
</div>

<!-- BOQ -->
<div class="tab-panel active" data-tab-panel="boq">
  ${buildBOQHTML(data)}
</div>




<!-- Visits -->
<div class="tab-panel" data-tab-panel="visits">
  <div class="section-row">
    <div class="section-title-txt">تقارير الزيارة الميدانية</div>
    <div class="section-line"></div>
    <div class="section-badge">${data.visits.length}</div>
  </div>
  <div class="visit-tl">
    ${data.visits.map((v, i) => `
      <div class="visit-item"
           onclick="window.showVisitDetail(${JSON.stringify(v).replace(/"/g, '&quot;')})">
        <div class="visit-dot-col">
          <div class="visit-dot"
               style="background:${v.state === 'approved' ? 'var(--green)' : 'var(--primary)'}">
          </div>
          ${i < data.visits.length - 1 ? '<div class="visit-line"></div>' : ''}
        </div>
        <div class="visit-body">
          <div class="visit-eng">${v.engineer}</div>
          <div class="visit-meta">
            ${v.date} · ${v.workers} عمال · NCR: ${v.ncr}
          </div>
          ${v.issues
            ? `<div style="font-size:10px;color:var(--orange);margin-top:2px">
               ⚠ ${v.issues.substring(0, 60)}</div>` : ''}
        </div>
        <div class="visit-dur">${v.photo_count} 📷</div>
      </div>`).join('')}
  </div>
  <div class="section-row" style="margin-top:16px">
    <div class="section-title-txt">سجل الحضور والانصراف</div>
    <div class="section-line"></div>
  </div>
  <div style="overflow-x:auto">
    <table class="boq-table">
      <tr>
        <th>المهندس</th><th>الدخول</th><th>الخروج</th>
        <th>المدة</th><th>حالة</th>
      </tr>
      ${data.attendance.map(a => `
        <tr>
          <td style="font-weight:600">${a.engineer}</td>
          <td style="font-family:monospace">${a.check_in}</td>
          <td style="font-family:monospace;color:var(--text3)">
            ${a.check_out || '—'}
          </td>
          <td>${a.duration ? Math.round(a.duration * 60) + 'د' : '—'}</td>
          <td>
            <span class="pill ${a.validated ? 'approved' : 'pending'}">
              ${a.validated ? 'موثق' : 'GPS'}
            </span>
          </td>
        </tr>`).join('')}
    </table>
  </div>
</div>`;
    }

    /* ── Task / Cert / CO HTML builders ──────────────────────── */
    /* ── أوامر العمل: الأعمال الموثقة وكمياتها ─────────────── */
    const WO_COLORS = {
        draft: '#8C98A2', submitted: '#D98A0B', approved: '#237292', delivered: '#C8A454',
        graded: '#1F9D6B', rework: '#D9493B', testing: '#7C5CBF', warranty: '#2E8FB5',
        closed: '#1F9D6B', rejected: '#D9493B',
    };
    function buildWorkOrdersHTML(wos) {
        if (!wos.length) return `<div class="wx-empty">لا توجد أوامر عمل لهذا المسجد</div>`;
        const accepted = wos.filter(w => w.posted);
        const accVal = accepted.reduce((s, w) => s + (w.total_value || 0), 0);
        const openCnt = wos.filter(w => ['submitted', 'approved', 'delivered', 'rework', 'testing'].includes(w.state)).length;
        return `
      <div class="wx-summary">
        <div><b>${wos.length}</b><span>أمر عمل</span></div>
        <div><b style="color:var(--green)">${accepted.length}</b><span>مقبول ومُرحّل للمنفذ</span></div>
        <div><b class="fin">${fmt(accVal)}</b><span>قيمة الأعمال المقبولة (ر)</span></div>
        <div><b style="color:var(--orange)">${openCnt}</b><span>قيد التنفيذ / المراجعة</span></div>
      </div>
      ${wos.map(w => `
        <div class="wx-card">
          <div class="wx-head">
            <span class="wx-code">${esc(w.name)}</span>
            <span class="wx-state" style="background:${WO_COLORS[w.state] || '#8C98A2'}1A;color:${WO_COLORS[w.state] || '#8C98A2'}">${esc(w.state_label)}</span>
            ${w.grade ? `<span class="wx-grade g-${w.grade.toLowerCase()}">${w.grade}</span>` : ''}
            ${w.posted ? '<span class="wx-posted">✓ مُرحّل للمنفذ</span>' : ''}
            <span class="wx-val">${mny(w.total_value)}</span>
          </div>
          <div class="wx-desc">${esc(w.description)}</div>
          <div class="wx-meta">
            ${w.supervisor ? `<span>👷 ${esc(w.supervisor)}</span>` : ''}
            ${w.date_requested ? `<span>طلب ${esc(w.date_requested)}</span>` : ''}
            ${w.date_delivered ? `<span>تسليم ${esc(w.date_delivered)}</span>` : ''}
            ${w.photos ? `<span>📷 ${w.photos} صورة تسليم</span>` : ''}
          </div>
          ${w.lines.length ? `
          <table class="boq-table wx-lines">
            <thead><tr><th>البند</th><th>الوصف</th><th>الكمية</th><th>الوحدة</th><th>سعر الوحدة</th><th>القيمة</th></tr></thead>
            <tbody>${w.lines.map(l => `
              <tr><td>${esc(l.code)}</td><td>${esc(l.description)}</td>
                  <td><b>${l.qty}</b></td><td>${esc(l.uom)}</td>
                  <td><span class="fin">${fmt(l.unit_price)}</span></td><td><span class="fin">${fmt(l.value)}</span></td></tr>`).join('')}
            </tbody>
          </table>` : ''}
        </div>`).join('')}`;
    }

    /* ── عينات المواد ───────────────────────────────────────── */
    function buildSubmittalsHTML(subs) {
        if (!subs.length) return `<div class="wx-empty">لا توجد عينات مواد لهذا المسجد</div>`;
        const col = st => st.startsWith('approved') ? '#1F9D6B' : st === 'rejected' ? '#D9493B'
            : st === 'revision' ? '#D98A0B' : st === 'draft' ? '#8C98A2' : '#237292';
        return `
      <div class="wx-summary">
        <div><b>${subs.length}</b><span>عينة</span></div>
        <div><b style="color:var(--green)">${subs.filter(x => x.state.startsWith('approved')).length}</b><span>معتمدة</span></div>
        <div><b style="color:var(--orange)">${subs.filter(x => ['submitted','submitted_chief','submitted_waqf'].includes(x.state)).length}</b><span>بانتظار المراجعة</span></div>
        <div><b style="color:var(--red)">${subs.filter(x => ['revision','rejected'].includes(x.state)).length}</b><span>تعديل / مرفوضة</span></div>
      </div>
      <div class="wx-grid">
      ${subs.map(x => `
        <div class="wx-card">
          <div class="wx-head">
            <span class="wx-code">${esc(x.name)}</span>
            <span class="wx-state" style="background:${col(x.state)}1A;color:${col(x.state)}">${esc(x.state_label)}</span>
            ${x.grade ? `<span class="wx-grade g-${x.grade.toLowerCase()}">${x.grade}</span>` : ''}
          </div>
          <div class="wx-desc"><b>${esc(x.material)}</b>${x.manufacturer ? ' · ' + esc(x.manufacturer) : ''}</div>
          <div class="wx-meta">
            ${x.boq ? `<span>📋 ${esc(x.boq)}</span>` : ''}
            ${x.work_order ? `<span>🔗 ${esc(x.work_order)}</span>` : ''}
            ${x.date ? `<span>${esc(x.date)}</span>` : ''}
          </div>
          ${x.notes ? `<div class="wx-note">${esc(x.notes)}</div>` : ''}
          ${x.docs.length ? `<div class="wx-docs">${x.docs.map(d =>
              `<a href="${d.url}" target="_blank">📎 ${esc(truncate(d.name, 28))}</a>`).join('')}</div>` : ''}
        </div>`).join('')}
      </div>`;
    }

    function buildTasksHTML(tasks) {
        if (!tasks?.length)
            return '<div style="padding:24px;text-align:center;color:var(--text3)">لا توجد مهام</div>';
        return tasks.map(t => `
      <div class="task-row">
        <div class="task-hdr" onclick="toggleTask(this)">
          <div class="task-dot" style="background:${kanbanColor(t.kanban_color)}"></div>
          <div class="task-name">${t.name}</div>
          <div class="task-count">${t.approved_count}/${t.subtask_count}</div>
          <span class="task-stage" style="${stageStyle(t.kanban_color)}">
            ${t.stage}
          </span>
          ${t.blocking_co
            ? `<span style="font-size:9px;background:rgba(240,165,0,.1);
               color:#A67800;padding:2px 6px;border-radius:999px">
               🔒 ${t.blocking_co}</span>` : ''}
          <div class="task-chevron">▾</div>
        </div>
        <div class="subtask-panel">
          ${t.subtasks.map(s => `
            <div class="subtask-item"
                 onclick="window.showSubtaskDetail(
                   ${JSON.stringify(s).replace(/"/g, '&quot;')})">
              <div class="sub-dot"
                   style="background:${kanbanColor(s.kanban_color)}"></div>
              <div class="sub-name">${s.name}</div>
              <div class="sub-status"
                   style="color:${kanbanColor(s.kanban_color)}">
                ${reviewStateLabel(s.review_state)}
              </div>
              ${s.photos?.length
            ? `<div class="sub-photos">📷${s.photos.length}</div>` : ''}
              ${s.docs?.length
            ? `<div class="sub-photos">📄${s.docs.length}</div>` : ''}
            </div>`).join('')}
        </div>
      </div>`).join('');
    }

    function buildCertsHTML(certs) {
        return certs.map(c => `
      <div class="cert-row"
           onclick="window.showCertDetailModal(
             ${JSON.stringify(c).replace(/"/g, '&quot;')})">
        <div class="cert-num">مستخلص #${c.number}</div>
        <div class="cert-amount">${mny(c.total_value)}</div>
        <div class="cert-date">${c.period_from} — ${c.period_to}</div>
        <div class="cert-status">
          <span class="pill ${certPillClass(c.state)}">
            ${certStateLabel(c.state)}
          </span>
        </div>
        <div class="cert-btns">
          ${c.state === 'consultant_approved' ? `
            <button class="act-btn approve"
                    onclick="event.stopPropagation();approveCert(${c.id},this)">
              ✓ اعتماد
            </button>
            <button class="act-btn reject"
                    onclick="event.stopPropagation();rejectCertDlg(${c.id},this)">
              ✗ رفض
            </button>` : ''}
        </div>
      </div>`).join('');
    }

    function buildCOHTML(cos) {
        return cos.map(co => `
      <div class="cert-row"
           onclick="window.showCODetailModal(
             ${JSON.stringify(co).replace(/"/g, '&quot;')})">
        <div class="cert-num">${co.name}</div>
        <div class="cert-amount">${mny(co.amount)}</div>
        <div class="cert-date">+${co.days_extension} يوم</div>
        <div class="cert-status">
          <span class="pill ${certPillClass(co.state)}">
            ${certStateLabel(co.state)}
          </span>
        </div>
        <div class="cert-btns">
          ${co.state === 'review' ? `
            <button class="act-btn approve"
                    onclick="event.stopPropagation();approveCO(${co.id},this)">
              ✓ اعتماد
            </button>
            <button class="act-btn reject"
                    onclick="event.stopPropagation();rejectCO(${co.id},this)">
              ✗ رفض
            </button>` : ''}
        </div>
      </div>`).join('');
    }

    function stageStyle(color) {
        return ({
            green: 'background:rgba(46,204,138,.12);color:#1A7A55',
            red: 'background:rgba(232,85,85,.1);color:#A33',
            yellow: 'background:rgba(240,165,0,.1);color:#A67800',
            grey: 'background:var(--surface2);color:var(--text3)',
        })[color] || 'background:var(--surface2);color:var(--text3)';
    }

    /* ── KPI Rings ───────────────────────────────────────────── */
    function drawRing(id, val, color, size) {
        const c = $(id);
        if (!c) return;
        const ctx = c.getContext('2d');
        const cx = size / 2, r = size * 0.4, lw = size * 0.12;
        ctx.clearRect(0, 0, size, size);
        ctx.lineWidth = lw;
        ctx.lineCap = 'round';
        ctx.strokeStyle = '#E8EDF2';
        ctx.beginPath();
        ctx.arc(cx, cx, r, -Math.PI / 2, Math.PI * 1.5);
        ctx.stroke();
        ctx.strokeStyle = color;
        ctx.beginPath();
        ctx.arc(cx, cx, r, -Math.PI / 2, (val / 100) * Math.PI * 2 - Math.PI / 2);
        ctx.stroke();
        ctx.fillStyle = '#0F2234';
        ctx.font = `600 ${Math.round(size * .19)}px IBM Plex Sans Arabic,sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(Math.round(val) + '%', cx, cx);
    }

    function drawKpiRings(m) {
        drawRing('ring-financial', m.financial_kpi, '#C8A454', 72);
        drawRing('ring-overall', m.overall_kpi, '#237292', 88);
        drawRing('ring-time', m.time_kpi, '#2ECC8A', 72);
        drawRing('ring-visit', m.visit_compliance, '#2E8FB5', 72);
    }

    /* ── BOQ Chart ───────────────────────────────────────────── */
    function drawBoqChart(cats) {
        const canvas = $('boq-chart');
        if (!canvas || !window.Chart || !cats?.length) return;
        if (window._boqChart) window._boqChart.destroy();
        window._boqChart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: cats.map(c => c.name),
                datasets: [
                    {
                        label: 'تعاقدي', data: cats.map(c => Math.round(c.contracted)),
                        backgroundColor: 'rgba(27,58,82,.15)', borderRadius: 4
                    },
                    {
                        label: 'منفذ', data: cats.map(c => Math.round(c.executed)),
                        backgroundColor: '#237292', borderRadius: 4
                    },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {legend: {position: 'top', labels: {font: {size: 11}}}},
                scales: {
                    x: {grid: {display: false}, ticks: {font: {size: 11}}},
                    y: {grid: {color: 'rgba(0,0,0,.04)'}, ticks: {font: {size: 11}}},
                },
            },
        });
    }

    /* ── Tabs ────────────────────────────────────────────────── */
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

    window.toggleTask = function (hdr) {
        const panel = hdr.nextElementSibling;
        const chevron = hdr.querySelector('.task-chevron');
        const open = panel.classList.contains('show');
        panel.classList.toggle('show', !open);
        chevron.classList.toggle('open', !open);
    };

    /* ── Subtask modal ───────────────────────────────────────── */
    window.showSubtaskDetail = function (s) {
        $('modal-subtask-title').textContent = s.name;
        let html = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">
        <div style="width:12px;height:12px;border-radius:50%;
             background:${kanbanColor(s.kanban_color)}"></div>
        <span style="font-size:12px;font-weight:600">
          ${reviewStateLabel(s.review_state)}
        </span>
        <span style="font-size:11px;color:var(--text3)">${s.stage}</span>
      </div>`;
        if (s.rejection_note)
            html += `<div style="background:rgba(232,85,85,.08);border:1px solid rgba(232,85,85,.2);
               border-radius:8px;padding:10px 12px;margin-bottom:14px;
               font-size:12px;color:var(--red)">
               سبب الرفض: ${s.rejection_note}</div>`;
        if (s.photos?.length) {
            html += `<div class="section-row">
        <div class="section-title-txt">صور الشاهد</div>
        <div class="section-line"></div>
        <div class="section-badge">${s.photos.length}</div>
      </div>
      <div class="photo-gallery">
        ${s.photos.map(ph => ph.is_360 ? `
          <div style="position:relative;border-radius:var(--r-md);overflow:hidden;
               cursor:pointer;grid-column:span 3"
               onclick="open360Viewer('${ph.url}','${ph.name}')">
            <img src="${ph.url}" style="width:100%;height:160px;object-fit:cover;filter:blur(1px)"/>
            <div style="position:absolute;inset:0;display:flex;align-items:center;
                 justify-content:center;background:rgba(0,0,0,.35)">
              <div style="background:rgba(255,255,255,.9);border-radius:999px;
                   padding:8px 16px;font-size:12px;font-weight:700;color:#1B3A52">
                🔮 صورة 360° — اضغط للعرض
              </div>
            </div>
          </div>` : `
          <div class="photo-thumb"
               onclick="openLightbox('${ph.url}','${ph.name}')">
            <img src="${ph.url}" alt="${ph.name}" loading="lazy"/>
          </div>`
            ).join('')}
      </div>`;
        }
        if (s.docs?.length) {
            html += `<div class="section-row" style="margin-top:14px">
        <div class="section-title-txt">الوثائق</div>
        <div class="section-line"></div>
      </div>
      <div class="doc-list">
        ${s.docs.map(doc => `
          <a class="doc-item" href="${doc.url}" target="_blank" download>
            <span class="doc-icon">${docIcon(doc.mimetype)}</span>
            <span class="doc-name">${doc.name}</span>
            <span class="doc-type">
              ${(doc.mimetype?.split('/')[1] || 'FILE').toUpperCase()}
            </span>
          </a>`).join('')}
      </div>`;
        }
        $('modal-subtask-body').innerHTML = html;
        openModal('modal-subtask');
    };

    /* ── Cert & CO modals ────────────────────────────────────── */
    window.showCertDetailModal = function (cert) {
        $('modal-cert-title').textContent = `مستخلص #${cert.number}`;
        $('modal-cert-body').innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
        ${[['القيمة الإجمالية', `${mny(cert.total_value)}`, 'var(--primary)'],
            ['القيمة الصافية', `${mny(cert.net_value || cert.total_value)}`, 'var(--navy)'],
            ['الفترة من', cert.period_from, ''],
            ['الفترة إلى', cert.period_to, ''],
        ].map(([l, v, c]) => `
          <div style="background:var(--surface2);border-radius:8px;padding:12px">
            <div style="font-size:10px;color:var(--text3)">${l}</div>
            <div style="font-size:14px;font-weight:700;${c ? 'color:' + c : ''}">${v}</div>
          </div>`).join('')}
      </div>
      <div style="margin-bottom:12px">
        <span class="pill ${certPillClass(cert.state)}"
              style="font-size:12px;padding:4px 14px">
          ${certStateLabel(cert.state)}
        </span>
      </div>
      ${cert.lines?.length ? `
        <div class="section-row">
          <div class="section-title-txt">بنود المستخلص</div>
          <div class="section-line"></div>
        </div>
        <table class="boq-table">
          <tr><th>الكود</th><th>الوصف</th><th>الكمية</th><th>القيمة</th></tr>
          ${cert.lines.map(l => `
            <tr>
              <td style="font-family:monospace;color:var(--primary);font-weight:600">
                ${l.boq_code}
              </td>
              <td>${l.desc}</td>
              <td>${l.qty}</td>
              <td>${mny(l.value)}</td>
            </tr>`).join('')}
        </table>` : ''}
      ${cert.state === 'consultant_approved' ? `
        <div style="display:flex;gap:10px;margin-top:16px">
          <button class="act-btn approve"
                  style="flex:1;padding:12px;font-size:13px"
                  onclick="approveCert(${cert.id},this);closeModal('modal-cert')">
            ✓ اعتماد المستخلص
          </button>
          <button class="act-btn reject"
                  style="flex:1;padding:12px;font-size:13px"
                  onclick="rejectCertDlg(${cert.id},this);closeModal('modal-cert')">
            ✗ رفض
          </button>
        </div>` : ''}`;
        openModal('modal-cert');
    };

    window.showCODetailModal = function (co) {
        $('modal-co-title').textContent = co.name;
        $('modal-co-body').innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
        ${[['قيمة التغيير', `${mny(co.amount)}`, 'var(--gold)'],
            ['تمديد زمني', `${co.days_extension} يوم`, 'var(--primary)'],
            ['النوع', co.type || '—', ''],
            ['الحالة', certStateLabel(co.state), ''],
        ].map(([l, v, c]) => `
          <div style="background:var(--surface2);border-radius:8px;padding:12px">
            <div style="font-size:10px;color:var(--text3)">${l}</div>
            <div style="font-size:14px;font-weight:700;${c ? 'color:' + c : ''}">${v}</div>
          </div>`).join('')}
      </div>
      ${co.reason ? `
        <div class="section-row">
          <div class="section-title-txt">سبب التغيير</div>
          <div class="section-line"></div>
        </div>
        <div style="background:var(--surface2);border-radius:8px;padding:12px;
                    font-size:13px;line-height:1.7;color:var(--text1)">
          ${co.reason}
        </div>` : ''}
      ${co.state === 'review' ? `
        <div style="display:flex;gap:10px;margin-top:16px">
          <button class="act-btn approve"
                  style="flex:1;padding:12px;font-size:13px"
                  onclick="approveCO(${co.id},this);closeModal('modal-co')">
            ✓ اعتماد
          </button>
          <button class="act-btn reject"
                  style="flex:1;padding:12px;font-size:13px"
                  onclick="rejectCO(${co.id},this);closeModal('modal-co')">
            ✗ رفض
          </button>
        </div>` : ''}`;
        openModal('modal-co');
    };

    /* ── Visit detail + 360 ──────────────────────────────────── */
    window.showVisitDetail = function (v) {
        $('modal-visit-title').textContent = `تقرير زيارة — ${v.date}`;
        const photos = v.photos || [];
        const photosHTML = photos.length ? `
      <div style="font-size:11px;font-weight:600;color:var(--text2);margin:12px 0 8px">
        الصور (${photos.length})
      </div>
      <div class="photo-gallery">
        ${photos.map(ph => ph.is_360 ? `
          <div style="position:relative;border-radius:var(--r-md);overflow:hidden;
               cursor:pointer;grid-column:span 3"
               onclick="open360Viewer('${ph.url}','${ph.name}')">
            <img src="${ph.url}" style="width:100%;height:160px;object-fit:cover;filter:blur(1px)"/>
            <div style="position:absolute;inset:0;display:flex;align-items:center;
                 justify-content:center;background:rgba(0,0,0,.35)">
              <div style="background:rgba(255,255,255,.9);border-radius:999px;
                   padding:8px 16px;font-size:12px;font-weight:700;color:#1B3A52">
                🔮 صورة 360° — اضغط للعرض
              </div>
            </div>
          </div>` : `
          <div class="photo-thumb"
               onclick="openLightbox('${ph.url}','${ph.name}')">
            <img src="${ph.url}" alt="${ph.name}" loading="lazy"
                 style="width:100%;height:100%;object-fit:cover"/>
          </div>`
        ).join('')}
      </div>` : '';

        $('modal-visit-body').innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px">
        ${[['المهندس', v.engineer, ''], ['العمال', v.workers, ''],
            ['تقارير NCR', v.ncr, v.ncr > 0 ? 'var(--red)' : 'var(--green)'],
            ['الصور', `${v.photo_count} 📷`, ''],
        ].map(([l, val, c]) => `
          <div style="background:var(--surface2);border-radius:8px;padding:10px 12px">
            <div style="font-size:10px;color:var(--text3)">${l}</div>
            <div style="font-size:13px;font-weight:700;${c ? 'color:' + c : ''}">${val}</div>
          </div>`).join('')}
      </div>
      ${v.activities ? `
        <div style="font-size:11px;font-weight:600;color:var(--text2);margin-bottom:5px">
          الأعمال المنجزة
        </div>
        <div style="font-size:12px;line-height:1.7;background:var(--surface2);
                    border-radius:8px;padding:10px 12px;margin-bottom:10px">
          ${v.activities}
        </div>` : ''}
      ${v.issues ? `
        <div style="font-size:11px;font-weight:600;color:var(--orange);margin-bottom:5px">
          المشكلات
        </div>
        <div style="font-size:12px;line-height:1.7;background:rgba(240,165,0,.05);
                    border:1px solid rgba(240,165,0,.2);border-radius:8px;
                    padding:10px 12px">${v.issues}
        </div>` : ''}
      ${photosHTML}
      ${v.photo_360_url ? `
        <div style="margin-top:12px">
          <button onclick="open360Viewer('${v.photo_360_url}','زيارة ${v.date}')"
                  style="width:100%;padding:12px;background:var(--navy);color:#fff;
                         border:none;border-radius:var(--r-md);font-size:13px;
                         font-weight:700;cursor:pointer;font-family:inherit">
            🔮 عرض صورة 360° — ${v.date}
          </button>
        </div>` : ''}`;
        openModal('modal-visit');
    };

    /* ── Lightbox + 360 ──────────────────────────────────────── */
    window.openLightbox = function (url, name) {
        $('lightbox-img').src = url;
        $('lightbox-caption').textContent = name;
        openModal('modal-lightbox');
    };

    window.open360Viewer = function (url, name) {
        if (!document.getElementById('pannellum-css')) {
            const css = document.createElement('link');
            css.id = 'pannellum-css';
            css.rel = 'stylesheet';
            css.href = 'https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.css';
            document.head.appendChild(css);
        }
        if (!window.pannellum) {
            const s = document.createElement('script');
            s.src = 'https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.js';
            s.onload = () => _show360(url, name);
            document.head.appendChild(s);
            return;
        }
        _show360(url, name);
    };

    function _show360(url, name) {
        let modal = document.getElementById('modal-360');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'modal-360';
            modal.className = 'modal-overlay';
            modal.innerHTML = `
        <div class="modal" style="max-width:900px;padding:0;overflow:hidden">
          <div class="modal-hdr"
               style="position:absolute;top:0;right:0;left:0;z-index:10;
                      background:rgba(0,0,0,.5);border:none">
            <div class="modal-title" id="360-title" style="color:#fff"></div>
            <button class="modal-close" style="color:#fff"
                    onclick="document.getElementById('modal-360').classList.remove('show');
                             document.getElementById('viewer-360').innerHTML=''">✕</button>
          </div>
          <div id="viewer-360" style="width:100%;height:500px"></div>
        </div>`;
            document.body.appendChild(modal);
            modal.addEventListener('click', function (e) {
                if (e.target === this) {
                    this.classList.remove('show');
                    document.getElementById('viewer-360').innerHTML = '';
                }
            });
        }
        document.getElementById('360-title').textContent = name || 'عرض 360°';
        document.getElementById('viewer-360').innerHTML = '';
        modal.classList.add('show');
        pannellum.viewer('viewer-360', {
            type: 'equirectangular', panorama: url,
            autoLoad: true, autoRotate: -2,
            compass: false, showControls: true, hfov: 100,
        });
    }

    /* ── Cert & CO actions ───────────────────────────────────── */
    window.approveCert = async function (id, btn) {
        btn.disabled = true;
        btn.textContent = '...';
        const res = await apiPost(`/dashboard/api/cert/${id}/approve`, {});
        if (res?.ok) btn.closest('.cert-row')?.querySelector('.cert-status')
            ?.replaceChildren(Object.assign(document.createElement('span'),
                {className: 'pill approved', textContent: '✓ معتمد'}));
        btn.closest('.cert-btns').innerHTML = '';
    };
    window.rejectCertDlg = function (id, btn) {
        const reason = prompt('سبب الرفض:');
        if (!reason) return;
        apiPost(`/dashboard/api/cert/${id}/reject`, {reason}).then(res => {
            if (res?.ok) btn.closest('.cert-row')?.querySelector('.cert-status')
                ?.replaceChildren(Object.assign(document.createElement('span'),
                    {className: 'pill rejected', textContent: '✗ مرفوض'}));
            btn.closest('.cert-btns').innerHTML = '';
        });
    };
    window.approveCO = async function (id, btn) {
        btn.disabled = true;
        btn.textContent = '...';
        await apiPost(`/dashboard/api/co/${id}/approve`, {});
        btn.closest('.cert-btns').innerHTML = '';
    };
    window.rejectCO = async function (id, btn) {
        btn.disabled = true;
        btn.textContent = '...';
        await apiPost(`/dashboard/api/co/${id}/reject`, {});
        btn.closest('.cert-btns').innerHTML = '';
    };

    /* ══════════════════════════════════════════════════════════
       ON-SITE
       ══════════════════════════════════════════════════════════ */
    async function loadOnSite() {
        const data = await apiGet('/dashboard/api/onsite');
        if (!Array.isArray(data)) return;
        renderOnsite(data);
        buildHeatmap(scopedMosques());
        refreshMapMarkers(false);
    }

    /* ══════════════════════════════════════════════════════════
       LIVE STREAM
       ══════════════════════════════════════════════════════════ */
    async function checkLiveStream() {
        const data = await apiGet('/dashboard/api/stream');
        const pill = $('live-pill');
        if (!pill) return;
        if (data?.url || data?.id) {
            pill.style.display = 'flex';
            pill.onclick = () => openLiveStream(data);
        } else {
            pill.style.display = 'none';
        }
    }

    function openLiveStream(data) {
        $('stream-modal-title').textContent = data.name || 'بث مباشر';
        const lbl = $('stream-modal-live');
        if (lbl) {
            const live = data.is_live !== false;
            lbl.textContent = live ? '● مباشر' : `🎥 تسجيل ${data.start || ''}`;
            lbl.style.color = live ? 'var(--red)' : 'var(--text3)';
        }
        const embed = $('stream-embed');
        const url = data.url || data.hls_url || '';

        // HLS with HLS.js or direct iframe
        if (url.includes('.m3u8')) {
            embed.innerHTML = `<video id="live-video" autoplay muted playsinline
        style="width:100%;height:100%;background:#000"
        src="${url}" controls></video>`;
            // Try HLS.js for broader support
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/hls.js@latest/dist/hls.min.js';
            script.onload = () => {
                const video = document.getElementById('live-video');
                if (Hls.isSupported()) {
                    const hls = new Hls({lowLatencyMode: true});
                    hls.loadSource(url);
                    hls.attachMedia(video);
                }
            };
            document.head.appendChild(script);
        } else if (url) {
            embed.innerHTML = `<iframe src="${url}" allowfullscreen
        allow="camera;microphone;autoplay"></iframe>`;
        }
        openModal('modal-stream');
    }

    /* ══════════════════════════════════════════════════════════
       CHATBOT
       ══════════════════════════════════════════════════════════ */
    const chatFab = $('chatbot-fab');
    const chatPanel = $('chatbot-panel');
    const chatMsgs = $('chat-msgs');
    const chatInput = $('chat-input');

    chatFab?.addEventListener('click', () => {
        chatPanel.classList.toggle('open');
        if (chatPanel.classList.contains('open')) chatInput?.focus();
    });
    $('chat-close')?.addEventListener('click', () =>
        chatPanel.classList.remove('open'));

    async function sendChat(msg) {
        if (!msg.trim()) return;
        chatInput.value = '';
        appendMsg('user', msg);
        S.chatHistory.push({role: 'user', content: msg});
        const thinking = appendMsg('bot', '...');
        const res = await apiPost('/dashboard/api/chat', {
            message: msg, mosque_context: S.mosqueContext,
            history: S.chatHistory.slice(-8),
        });
        thinking.textContent = res?.reply || 'تعذر الحصول على رد.';
        S.chatHistory.push({role: 'assistant', content: res?.reply || ''});
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
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChat(chatInput.value);
        }
    });
    document.querySelectorAll('.chat-sug').forEach(btn =>
        btn.addEventListener('click', function () {
            sendChat(this.textContent);
            chatPanel.classList.add('open');
        }));

    /* ══════════════════════════════════════════════════════════
       MODALS
       ══════════════════════════════════════════════════════════ */
    function openModal(id) {
        document.getElementById(id)?.classList.add('show');
    }

    window.closeModal = function (id) {
        document.getElementById(id)?.classList.remove('show');
        if (id === 'modal-stream') $('stream-embed').innerHTML = '';
        if (id === 'modal-lightbox') $('lightbox-img').src = '';
    };
    document.querySelectorAll('.modal-overlay').forEach(o =>
        o.addEventListener('click', function (e) {
            if (e.target === this) window.closeModal(this.id);
        }));

    /* ══════════════════════════════════════════════════════════
       AUTO REFRESH
       ══════════════════════════════════════════════════════════ */
    function startRefresh() {
        const interval = Math.max(30, CONFIG.refresh_interval || 60) * 1000;
        S.refreshTimer = setInterval(async () => {
            checkLiveStream();
            const [mosques, sum, alerts, onsite, streams] = await Promise.all([
                apiGet('/dashboard/api/mosques'),
                apiGet('/dashboard/api/summary'),
                apiGet('/dashboard/api/alerts'),
                apiGet('/dashboard/api/onsite'),
                apiGet('/dashboard/api/streams'),
            ]);
            if (Array.isArray(streams)) setStreams(streams);
            if (Array.isArray(mosques)) setMosques(mosques);
            if (sum) S.summary = sum;
            if (alerts) renderAlerts(alerts);
            if (Array.isArray(onsite)) renderOnsite(onsite);
            applyScope();
            if (S.activeMosqueId) loadMosqueDetail(S.activeMosqueId, true);
        }, interval);
    }

    /* ── Chart.js loader ─────────────────────────────────────── */
    function loadChartJS(cb) {
        if (window.Chart) {
            cb();
            return;
        }
        const s = document.createElement('script');
        s.src = 'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js';
        s.onload = cb;
        document.head.appendChild(s);
    }

    /* ── Start ───────────────────────────────────────────────── */
    init();
});