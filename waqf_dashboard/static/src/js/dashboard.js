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
    const SUMMARY = JSON.parse(dataEl?.dataset.summary || '{}');
    const ONSITE = JSON.parse(dataEl?.dataset.onsite || '[]');
    const HAS_AI = dataEl?.dataset.hasAi === '1';

    /* ── State ─────────────────────────────────────────────── */
    const S = {
        mosques: [],
        packages: PKGS,
        allAlerts: [],
        activeMosqueId: null,
        mosqueContext: null,
        chatHistory: [],
        refreshTimer: null,
        map: null,
        mapMarkers: {},
        liveStreams: {},   // ← تأكد أنه موجود هنا
    };

    /* ── Helpers ────────────────────────────────────────────── */
    const $ = id => document.getElementById(id);
    const fmt = n => new Intl.NumberFormat('ar-SA').format(Math.round(n || 0));
    const pct = n => Math.round(n || 0) + '%';
    const dotColor = kpi =>
        kpi >= 70 ? '#2ECC8A' : kpi >= 50 ? '#F0A500' : kpi > 0 ? '#E85555' : '#B0C0CC';
    const truncate = (s, n) =>
        s && s.length > n ? s.substring(0, n) + '…' : (s || '');
    const kanbanColor = c =>
        ({
            green: '#2ECC8A', red: '#E85555', yellow: '#F0A500',
            orange: '#F0A500', grey: '#8FA3B3'
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

    /* ── API ────────────────────────────────────────────────── */
    async function apiGet(url) {
        const r = await fetch(url, {credentials: 'same-origin'});
        return r.json();
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
        loadChartJS(async () => {
            // Render immediately from server data
            renderSummary(SUMMARY);
            if (S.packages.length) {
                buildSidebar(S.packages);
                buildPhaseGantt(S.packages);
                S.packages.forEach(pkg =>
                    pkg.mosques?.forEach(m =>
                        S.mosques.push({...m, package: pkg.name})));
            }

            // Parallel API calls
            const [mosques, alerts, insights, risk, forecast, quality, contractors] =
                await Promise.all([
                    apiGet('/dashboard/api/mosques'),
                    apiGet('/dashboard/api/alerts'),
                    apiGet('/dashboard/api/ai_insights'),
                    apiGet('/dashboard/api/risk_matrix'),
                    apiGet('/dashboard/api/forecast'),
                    apiGet('/dashboard/api/quality'),
                    apiGet('/dashboard/api/contractors'),
                ]);

            S.mosques = mosques;
            buildHeatmap(mosques);
            initMap(mosques);
            renderAlerts(alerts);
            renderAIInsights(insights);
            renderRiskMatrix(risk.points || []);
            renderForecast(forecast.rows || []);
            renderQuality(quality);
            renderContractors(contractors.contractors || []);
            renderCriticalProjects(mosques);
            loadOnSite();
            checkLiveStream();
            initSearch();
            initQuickFilters();
            startRefresh();
        });
    }

    /* ══════════════════════════════════════════════════════════
       SUMMARY KPI STRIP
       ══════════════════════════════════════════════════════════ */
    function renderSummary(d) {
        if (!d || !Object.keys(d).length) return;

        const set = (id, val) => {
            const el = $(id);
            if (el) el.textContent = val;
        };
        const setTrend = (id, delta, labels) => {
            const el = $(id);
            if (!el) return;
            const up = delta > 0, dn = delta < 0;
            el.className = 'exec-kpi-trend ' + (up ? 'up' : dn ? 'down' : 'flat');
            el.innerHTML = `<span class="arrow">${up ? '↑' : dn ? '↓' : '→'}</span>
        ${Math.abs(delta)} ${labels[up ? 0 : dn ? 1 : 2]}`;
        };

        set('kpi-total-value', fmt(d.total_contract_value / 1000000));
        set('kpi-avg-kpi', Math.round(d.avg_kpi || 0));
        set('kpi-critical', d.critical_count || 0);
        set('kpi-total-delay', d.total_delay_days || 0);
        set('kpi-co-value', fmt((d.co_value || 0) / 1000));
        set('kpi-pending', (d.pending_certs || 0) + (d.pending_cos || 0));
        set('kpi-ontime', d.on_time_count || 0);

        setTrend('kpi-avg-trend', d.avg_kpi_delta || 0, ['%', '%', 'بدون تغيير']);
        setTrend('kpi-critical-trend', -(d.critical_delta || 0), ['مشروع', 'مشروع', '']);
        setTrend('kpi-pending-trend', -(d.pending_certs_delta || 0), ['جديد', 'أقل', '']);

        // Animate numbers
        animateCounters();
    }

    function animateCounters() {
        document.querySelectorAll('.exec-kpi-value').forEach(el => {
            el.style.opacity = '0';
            el.style.transform = 'translateY(8px)';
            setTimeout(() => {
                el.style.transition = 'opacity .4s ease, transform .4s ease';
                el.style.opacity = '1';
                el.style.transform = 'translateY(0)';
            }, 50);
        });
    }

    /* ══════════════════════════════════════════════════════════
       SMART ALERT CENTER
       ══════════════════════════════════════════════════════════ */
    function renderAlerts(data) {
        S.allAlerts = data.alerts || [];
        const countEl = $('alert-count');
        if (countEl) countEl.textContent = S.allAlerts.length;

        // Source badge
        const srcEl = $('alert-source-badge');
        if (srcEl) srcEl.textContent = data.source === 'ai_center' ? '🤖 AI Center' : '⚙ محسوب';

        renderAlertList('all');

        // Filter buttons
        document.querySelectorAll('.alert-filter').forEach(btn => {
            btn.addEventListener('click', function () {
                document.querySelectorAll('.alert-filter').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                renderAlertList(this.dataset.filter);
            });
        });
    }

    function renderAlertList(filter) {
        const list = $('alert-list');
        if (!list) return;

        const filtered = filter === 'all' ? S.allAlerts :
            S.allAlerts.filter(a => a.severity === filter || a.category === filter);

        if (!filtered.length) {
            list.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text3)">
        لا توجد تنبيهات في هذا التصنيف</div>`;
            return;
        }

        const sevIcon = {critical: '🔴', high: '🟠', medium: '🟡', low: '🟢'};
        const sevClass = {critical: 'cr', high: 'hi', medium: 'md', low: 'low'};

        list.innerHTML = filtered.slice(0, 6).map(a => `
      <div class="alert-item" data-mosque="${a.mosque_id || ''}"
           onclick="a.mosque_id && loadMosqueDetailGlobal(${a.mosque_id || 0})">
        <div class="alert-severity ${sevClass[a.severity] || 'md'}"></div>
        <div class="alert-icon">${sevIcon[a.severity] || '⚠️'}</div>
        <div class="alert-body">
          <div class="alert-title">${a.title}</div>
          <div class="alert-desc">${a.description}</div>
        </div>
        <span class="alert-badge ${sevClass[a.severity] || 'md'}">
          ${a.severity === 'critical' ? 'حرج' :
            a.severity === 'high' ? 'مرتفع' :
                a.severity === 'medium' ? 'متوسط' : 'منخفض'}
        </span>
        <button class="alert-cta" onclick="event.stopPropagation();
          ${a.mosque_id ? `loadMosqueDetailGlobal(${a.mosque_id})` : ''}">
          ${a.cta_label || 'عرض'}
        </button>
      </div>`).join('');
    }

    /* ══════════════════════════════════════════════════════════
       PHASE GANTT
       ══════════════════════════════════════════════════════════ */
    function buildPhaseGantt(pkgs) {
        const el = $('gantt-rows'), monthsEl = $('gantt-months');
        if (!el) return;

        // فقط المرحلة الحالية
        const currentPkg = pkgs.find(p => p.is_current);
        if (!currentPkg) {
            el.innerHTML = `<div style="padding:30px;text-align:center;color:var(--text3)">
      لا توجد مرحلة نشطة حالياً</div>`;
            return;
        }

        const pStart = new Date('2026-04-01');
        const pEnd = new Date('2027-04-30');
        const total = pEnd - pStart;
        const today = new Date();
        const todayP = Math.min(100, Math.max(0, (today - pStart) / total * 100));

        // Months header
        if (monthsEl) {
            monthsEl.innerHTML = '';
            ['أبر٢٦', 'مايو', 'يون', 'يول', 'أغس', 'سبت',
                'أكت', 'نوف', 'ديس', 'يناير٢٧', 'فبر', 'مارس'].forEach(m => {
                const d = document.createElement('div');
                d.className = 'gantt-month';
                d.textContent = m;
                monthsEl.appendChild(d);
            });
        }

        // شريط تقدم المرحلة
        const start = new Date(currentPkg.planned_start);
        const end = new Date(currentPkg.planned_end);
        const leftP = Math.max(0, (start - pStart) / total * 100);
        const widthP = Math.min(100 - leftP, (end - start) / total * 100);
        const progP = Math.min(100, Math.max(0, (today - start) / (end - start) * 100));
        const color = '#237292';

        el.innerHTML = `
    <!-- شريط التقدم الزمني -->
    <div style="position:relative;height:28px;margin-bottom:20px">
      <div style="position:absolute;right:${leftP}%;width:${widthP}%;
        top:0;bottom:0;background:${color}22;border:1px solid ${color}44;
        border-radius:8px;overflow:hidden">
        <div style="width:${progP}%;background:${color};height:100%;
          border-radius:7px;transition:width 1.2s ease"></div>
        <span style="position:relative;z-index:1;font-size:10px;font-weight:700;
          padding:0 10px;line-height:28px;color:${color}">
          ${currentPkg.avg_kpi}% · ${currentPkg.mosque_count} مسجد
          · ${currentPkg.planned_start} → ${currentPkg.planned_end}
        </span>
      </div>
      <div class="gantt-today" style="right:${todayP}%">
        <div class="gantt-today-label">اليوم</div>
      </div>
    </div>

    <!-- قائمة المساجد -->
    <div style="display:flex;flex-direction:column;gap:5px">
      ${(currentPkg.mosques || []).map(m => {
            const kpiColor = dotColor(m.overall_kpi);
            const kpiBg = m.overall_kpi >= 70 ? 'rgba(46,204,138,0.08)' :
                m.overall_kpi >= 50 ? 'rgba(240,165,0,0.08)' :
                    'rgba(232,85,85,0.08)';
            const kpiBorder = m.overall_kpi >= 70 ? 'rgba(46,204,138,0.2)' :
                m.overall_kpi >= 50 ? 'rgba(240,165,0,0.2)' :
                    'rgba(232,85,85,0.2)';
            return `
          <div onclick="loadMosqueDetailGlobal(${m.id})"
               style="display:flex;align-items:center;gap:12px;
                      padding:10px 14px;border-radius:10px;cursor:pointer;
                      background:${kpiBg};border:1px solid ${kpiBorder};
                      transition:.15s ease"
               onmouseover="this.style.transform='translateX(-3px)';this.style.boxShadow='0 4px 12px rgba(27,58,82,0.1)'"
               onmouseout="this.style.transform='';this.style.boxShadow=''">

            <!-- Dot -->
            <div style="width:10px;height:10px;border-radius:50%;
              flex-shrink:0;background:${kpiColor};
              box-shadow:0 0 0 3px ${kpiColor}30"></div>

            <!-- Code -->
            <span style="font-family:'IBM Plex Mono',monospace;font-size:10px;
              font-weight:700;color:var(--primary);min-width:60px">
              ${m.code}
            </span>

            <!-- Name — كامل -->
            <span style="flex:1;font-size:12px;font-weight:600;color:var(--text1)">
              ${m.name}
            </span>

            <!-- KPI bar -->
            <div style="display:flex;align-items:center;gap:8px;flex-shrink:0">
              <div style="width:80px;height:5px;background:var(--surface3);
                border-radius:3px;overflow:hidden">
                <div style="width:${m.overall_kpi}%;height:100%;
                  background:${kpiColor};border-radius:3px;
                  transition:width 1s ease"></div>
              </div>
              <span style="font-size:12px;font-weight:800;color:${kpiColor};
                min-width:38px;text-align:left">
                ${m.overall_kpi}%
              </span>
            </div>

            <!-- Delay -->
            ${m.days_delay > 0 ? `
              <span style="font-size:10px;font-weight:700;color:var(--red);
                background:rgba(232,85,85,0.1);padding:2px 8px;
                border-radius:999px;flex-shrink:0">
                -${m.days_delay}د
              </span>` : `
              <span style="font-size:10px;color:var(--green);flex-shrink:0">✓</span>`}

            <!-- Arrow -->
            <span style="color:var(--text4);font-size:14px">›</span>
          </div>`;
        }).join('')}
    </div>`;
    }

    window.loadMosqueDetailGlobal = id => {
        document.querySelectorAll('.gantt-popup').forEach(p => p.classList.remove('show'));
        loadMosqueDetail(id);
    };

    /* ══════════════════════════════════════════════════════════
       HEATMAP
       ══════════════════════════════════════════════════════════ */
    function buildHeatmap(mosques) {
        const el = $('heatmap-grid');
        if (!el) return;
        el.innerHTML = '';
        mosques.forEach(m => {
            const cell = document.createElement('div');
            cell.className = `hm-cell ${m.kpi_color}`;
            cell.dataset.id = m.id;
            cell.textContent = (m.code || '').replace(/^(RUH|JED|TIF|RFH|AFJ|YRA|GIZ)-0?/, '');

            const tip = document.createElement('div');
            tip.className = 'hm-tooltip';
            tip.innerHTML = `<strong>${m.code}</strong><br/>${truncate(m.name, 18)}<br/>
        KPI: ${m.overall_kpi}%
        ${m.days_delay > 0
                ? `<br/><span style="color:#F87171">تأخير ${m.days_delay} يوم</span>` : ''}`;
            cell.appendChild(tip);

            cell.addEventListener('click', function () {
                document.querySelectorAll('.hm-cell').forEach(c => c.classList.remove('active'));
                this.classList.add('active');
                document.querySelectorAll('.sb-mosque').forEach(s =>
                    s.classList.toggle('active', parseInt(s.dataset.id) === m.id));
                loadMosqueDetail(parseInt(this.dataset.id));
            });
            el.appendChild(cell);
        });
    }

    function initMap(mosques) {
        const mapEl = document.getElementById('mosque-map');
        if (!mapEl) return;

        // Load Leaflet CSS
        if (!document.getElementById('leaflet-css')) {
            const css = document.createElement('link');
            css.id = 'leaflet-css';
            css.rel = 'stylesheet';
            css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
            document.head.appendChild(css);
        }

        // Load Leaflet JS then build
        if (!window.L) {
            const script = document.createElement('script');
            script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
            script.onload = () => _buildMap(mosques);
            script.onerror = () => {
                mapEl.innerHTML = `
          <div style="display:flex;align-items:center;justify-content:center;
            height:100%;color:var(--text3);flex-direction:column;gap:8px">
            <div style="font-size:24px">🗺</div>
            <div style="font-size:12px">تعذر تحميل الخريطة</div>
          </div>`;
            };
            document.head.appendChild(script);
        } else {
            _buildMap(mosques);
        }
    }

    function _buildMap(mosques) {
        const mapEl = document.getElementById('mosque-map');
        if (!mapEl || !window.L) return;

        if (S.map) {
            S.map.remove();
            S.map = null;
            S.mapMarkers = {};
        }

        // إنشاء الخريطة — مركز السعودية دائماً
        S.map = L.map('mosque-map', {
            center: [23.8859, 45.0792],
            zoom: 5,
            zoomControl: true,
            attributionControl: false,
        });

        // Tile layer داكن
        // L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        //   maxZoom: 19,
        //   subdomains: 'abcd',
        // }).addTo(S.map);
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            maxZoom: 19,
        }).addTo(S.map);

        // حدود السعودية باللون الأخضر
        fetch('https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson')
            .then(r => r.json())
            .then(data => {
                const saudi = data.features.find(f =>
                    f.properties.ISO_A3 === 'SAU' || f.properties.ADMIN === 'Saudi Arabia'
                );
                if (!saudi || !S.map) return;

                L.geoJSON(saudi, {
                    style: {
                        color: '#2ECC8A',
                        weight: 2,
                        fillColor: '#2ECC8A',
                        fillOpacity: 0.06,
                        dashArray: '5 3',
                    },
                }).addTo(S.map);
            })
            .catch(() => {
            });

        // إضافة markers
        const withCoords = mosques.filter(m =>
            m && m.lat && m.lng && m.lat !== 0 && m.lng !== 0
        );

        if (withCoords.length) {
            withCoords.forEach(m => _addMapMarker(m));
        } else {
            const currentPkg = S.packages.find(p => p.is_current);
            const currentIds = (currentPkg?.mosques || []).map(m => m.id);
            const currentMosques = currentIds.length
                ? mosques.filter(m => currentIds.includes(m.id))
                : mosques;
            _addDemoMarkers(currentMosques);
        }
    }

    function _addMapMarker(m) {
        if (!S.map || !window.L) return;
        if (!m || m.lat === undefined || m.lng === undefined) return;  // ← أضف
        if (isNaN(m.lat) || isNaN(m.lng)) return;  // ← أضف

        const kpiColor = m.kpi_color === 'green' ? '#2ECC8A' :
            m.kpi_color === 'yellow' ? '#F0A500' :
                m.kpi_color === 'red' ? '#E85555' : '#8FA3B3';

        const hasStream = S.liveStreams ? !!S.liveStreams[m.id] : false;  // ← آمن
        const hasAlert = S.allAlerts
            ? S.allAlerts.some(a => a.mosque_id === m.id && a.severity === 'critical')
            : false;  // ← آمن

        const icon = L.divIcon({
            className: '',
            html: `
        <div style="position:relative;cursor:pointer">
          <div style="
            width:36px;height:36px;border-radius:50%;
            background:${kpiColor};
            border:3px solid rgba(255,255,255,0.85);
            display:flex;align-items:center;justify-content:center;
            font-size:9px;font-weight:800;color:#fff;
            box-shadow:0 4px 14px rgba(0,0,0,0.35);
            transition:.15s ease">
            ${Math.round(m.overall_kpi)}%
          </div>
          ${hasStream ? `
            <div style="position:absolute;top:-3px;right:-3px;
              width:13px;height:13px;background:#E85555;
              border-radius:50%;border:2px solid #fff;
              animation:mapLivePulse 1s infinite"></div>` : ''}
          ${hasAlert && !hasStream ? `
            <div style="position:absolute;top:-3px;right:-3px;
              width:13px;height:13px;background:#F0A500;
              border-radius:50%;border:2px solid #fff"></div>` : ''}
        </div>`,
            iconSize: [36, 36],
            iconAnchor: [18, 18],
            popupAnchor: [0, -20],
        });

        const marker = L.marker([m.lat, m.lng], {icon}).addTo(S.map);
        marker.bindPopup(_buildMapPopup(m), {
            maxWidth: 260,
            className: 'waqf-map-popup',
        });

        marker.on('popupopen', () => {
            setTimeout(() => {
                const btn = document.querySelector('.map-detail-btn');
                if (btn) btn.addEventListener('click', () => {
                    marker.closePopup();
                    loadMosqueDetail(m.id);
                });
                const streamBtn = document.querySelector('.map-stream-btn');
                if (streamBtn) streamBtn.addEventListener('click', () => {
                    marker.closePopup();
                    _openMosqueStream(m.id, m.name);
                });
            }, 50);
        });

        S.mapMarkers[m.id] = marker;
    }

    function _buildMapPopup(m) {
        const kpiColor = m.kpi_color === 'green' ? '#2ECC8A' :
            m.kpi_color === 'yellow' ? '#F0A500' :
                m.kpi_color === 'red' ? '#E85555' : '#8FA3B3';
        const alert = S.allAlerts.find(a => a.mosque_id === m.id);
        const hasStream = !!S.liveStreams[m.id];

        return `
      <div style="font-family:'IBM Plex Sans Arabic',sans-serif;
                  direction:rtl;min-width:210px">
        <div style="font-size:13px;font-weight:800;color:#1B3A52;margin-bottom:3px">
          ${m.name}
        </div>
        <div style="font-size:10px;color:#7A90A4;margin-bottom:10px">
          ${m.code} · ${m.package || ''}
        </div>
 
        <!-- KPI stats -->
        <div style="display:grid;grid-template-columns:repeat(3,1fr);
                    gap:6px;margin-bottom:10px">
          <div style="text-align:center;background:#F7F9FC;
                      border-radius:8px;padding:7px 4px">
            <div style="font-size:15px;font-weight:800;color:${kpiColor}">
              ${m.overall_kpi}%
            </div>
            <div style="font-size:9px;color:#7A90A4">KPI</div>
          </div>
          <div style="text-align:center;background:#F7F9FC;
                      border-radius:8px;padding:7px 4px">
            <div style="font-size:15px;font-weight:800;
                        color:${m.days_delay > 0 ? '#E85555' : '#2ECC8A'}">
              ${m.days_delay > 0 ? m.days_delay + 'د' : '✓'}
            </div>
            <div style="font-size:9px;color:#7A90A4">تأخير</div>
          </div>
          <div style="text-align:center;background:#F7F9FC;
                      border-radius:8px;padding:7px 4px">
            <div style="font-size:11px;font-weight:700;color:#237292">
              ${m.state === 'active' ? 'نشط' :
            m.state === 'draft' ? 'جديد' : (m.state || '—')}
            </div>
            <div style="font-size:9px;color:#7A90A4">الحالة</div>
          </div>
        </div>
 
        <!-- Alert -->
        ${alert ? `
          <div style="background:rgba(232,85,85,0.08);
                      border:1px solid rgba(232,85,85,0.2);
                      border-radius:8px;padding:7px 9px;
                      margin-bottom:8px;font-size:11px;color:#E85555">
            ⚠ ${alert.title}
          </div>` : ''}
 
        <!-- Live stream button -->
        ${hasStream ? `
          <button class="map-stream-btn"
            style="width:100%;padding:7px;background:#E85555;color:#fff;
                   border:none;border-radius:8px;font-size:11px;
                   font-weight:700;cursor:pointer;margin-bottom:6px;
                   font-family:inherit;display:flex;align-items:center;
                   justify-content:center;gap:5px">
            <span style="width:7px;height:7px;background:#fff;
                         border-radius:50%;display:inline-block;
                         animation:mapLivePulse 1s infinite"></span>
            مشاهدة البث المباشر
          </button>` : ''}
 
        <!-- Detail button -->
        <button class="map-detail-btn"
          style="width:100%;padding:8px;background:#237292;color:#fff;
                 border:none;border-radius:8px;font-size:11px;
                 font-weight:700;cursor:pointer;font-family:inherit">
          عرض التفاصيل ›
        </button>
      </div>`;
    }

    function _addDemoMarkers(mosques) {
        const cityBases = {
            riyadh: {lat: 24.7136, lng: 46.6753},
            jeddah: {lat: 21.4858, lng: 39.1925},
            taif: {lat: 21.2703, lng: 40.4158},
            jazan: {lat: 16.8892, lng: 42.5511},
            yara: {lat: 18.3059, lng: 42.7337},
            aflaj: {lat: 22.2641, lng: 46.7159},
            rafha: {lat: 29.6267, lng: 43.4914},
        };

        // أضف دائرة ملونة لكل مدينة فيها مساجد
        const citiesWithMosques = {};
        mosques.forEach(m => {
            if (!m) return;
            const city = m.city || 'riyadh';
            if (!citiesWithMosques[city]) citiesWithMosques[city] = [];
            citiesWithMosques[city].push(m);
        });

        Object.entries(citiesWithMosques).forEach(([city, cityMosques]) => {
            const base = cityBases[city] || cityBases.riyadh;

            // دائرة المدينة
            const avgKpi = cityMosques.reduce((s, m) => s + (m.overall_kpi || 0), 0)
                / cityMosques.length;
            const cityColor = avgKpi >= 70 ? '#2ECC8A' :
                avgKpi >= 50 ? '#F0A500' : '#E85555';

            // إضافة دائرة للمدينة
            if (S.map && window.L) {
                L.circle([base.lat, base.lng], {
                    radius: cityMosques.length * 3000,
                    color: cityColor,
                    fillColor: cityColor,
                    fillOpacity: 0.08,
                    weight: 1.5,
                    dashArray: '4 4',
                }).addTo(S.map).bindTooltip(
                    `${city === 'riyadh' ? 'الرياض' :
                        city === 'jeddah' ? 'جدة' :
                            city === 'taif' ? 'الطائف' :
                                city === 'jazan' ? 'جازان' :
                                    city === 'yara' ? 'يرى' :
                                        city === 'aflaj' ? 'الأفلاج' :
                                            city === 'rafha' ? 'رفحاء' : city}
         — ${cityMosques.length} مسجد`,
                    {direction: 'top', className: 'waqf-city-tooltip'}
                );
            }

            // توزيع المساجد داخل المدينة
            cityMosques.forEach((m, i) => {
                const total = cityMosques.length;
                const angle = (i / total) * Math.PI * 2 - Math.PI / 2;
                const rings = Math.ceil(total / 8);
                const ring = Math.floor(i / 8);
                const radius = 0.035 + ring * 0.035;

                const lat = base.lat + Math.cos(angle) * radius;
                const lng = base.lng + Math.sin(angle) * radius;

                // نمرر الـ mosque مع إحداثيات محسوبة
                _addMapMarker({...m, lat, lng});
            });
        });

        // Fit map على كل المدن
        if (S.map && window.L) {
            const allBases = Object.keys(citiesWithMosques)
                .map(city => cityBases[city] || cityBases.riyadh)
                .map(b => [b.lat, b.lng]);

            if (allBases.length === 1) {
                S.map.setView(allBases[0], 11);
            } else if (allBases.length > 1) {
                S.map.fitBounds(allBases, {padding: [60, 60]});
            }
        }
    }

    function filterMapByPackage(pkgId) {
        if (!S.map || !window.L) return;
        if (!pkgId) {
            Object.values(S.mapMarkers).forEach(m => {
                if (!S.map.hasLayer(m)) m.addTo(S.map);
            });
            return;
        }
        const pkg = S.packages.find(p => p.id === pkgId);
        if (!pkg) return;
        const mosqueIds = (pkg.mosques || []).map(m => m.id);
        Object.entries(S.mapMarkers).forEach(([id, marker]) => {
            if (mosqueIds.includes(parseInt(id))) {
                if (!S.map.hasLayer(marker)) marker.addTo(S.map);
            } else {
                if (S.map.hasLayer(marker)) S.map.removeLayer(marker);
            }
        });
    }

    function updateMapMarkers() {
        if (!S.map || !window.L) return;
        Object.entries(S.mapMarkers).forEach(([id, marker]) => {
            S.map.removeLayer(marker);
        });
        S.mapMarkers = {};
        S.mosques.forEach(m => {
            if (m.lat && m.lng && m.lat !== 0 && m.lng !== 0) {
                _addMapMarker(m);
            }
        });
    }

    function _openMosqueStream(mosqueId, mosqueName) {
        const url = S.liveStreams[mosqueId];
        if (!url) return;
        const titleEl = document.getElementById('stream-modal-title');
        if (titleEl) titleEl.textContent = mosqueName || 'بث مباشر';
        const embed = document.getElementById('stream-embed');
        if (!embed) return;
        if (url.includes('.m3u8')) {
            embed.innerHTML = `
        <video id="live-video" autoplay muted playsinline controls
               style="width:100%;height:100%;background:#000"
               src="${url}"></video>`;
            const s = document.createElement('script');
            s.src = 'https://cdn.jsdelivr.net/npm/hls.js@latest/dist/hls.min.js';
            s.onload = () => {
                const video = document.getElementById('live-video');
                if (window.Hls?.isSupported()) {
                    const hls = new Hls({lowLatencyMode: true});
                    hls.loadSource(url);
                    hls.attachMedia(video);
                }
            };
            document.head.appendChild(s);
        } else {
            embed.innerHTML = `
        <iframe src="${url}" allowfullscreen
                allow="camera;microphone;autoplay"
                style="width:100%;height:100%;border:none"></iframe>`;
        }
        document.getElementById('modal-stream')?.classList.add('show');
    }


    function initQuickFilters() {
        document.querySelectorAll('.qf-btn').forEach(btn => {
            btn.addEventListener('click', function () {
                document.querySelectorAll('.qf-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                const f = this.dataset.filter;
                document.querySelectorAll('.hm-cell').forEach(cell => {
                    const m = S.mosques.find(x => x.id === parseInt(cell.dataset.id));
                    if (!m) return;
                    const show = f === 'all' ? true :
                        f === 'ok' ? m.overall_kpi >= 70 :
                            f === 'warn' ? m.overall_kpi >= 50 && m.overall_kpi < 70 :
                                f === 'critical' ? m.overall_kpi < 50 && m.overall_kpi > 0 :
                                    f === 'delayed' ? m.days_delay > 0 : true;
                    cell.style.opacity = show ? '1' : '0.2';
                    cell.style.transform = show ? '' : 'scale(0.85)';
                });
            });
        });
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
  const el  = $('merged-panel');
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
      risk:'var(--red)', opportunity:'var(--green)',
      action:'var(--gold)', info:'var(--primary)', phase:'var(--primary)',
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
          آخر تحديث: ${upd.substring(0,16)}</div>` : ''}
        ${insights.length ? insights.slice(0,5).map(ins => `
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
              ['NCR مفتوح',     q.ncr_total||0,             'var(--red)'],
              ['إعادة العمل',   q.itp_rate?(100-q.itp_rate).toFixed(0)+'%':'—','var(--orange)'],
              ['فحوصات فاشلة', q.failed_inspections||0,    'var(--red)'],
              ['مشاكل مفتوحة', q.open_issues||0,           'var(--orange)'],
            ].map(([lbl,val,col]) => `
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
      btn.addEventListener('click', function() {
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
            const isCurrent = pkg.is_current;
            const isPast = pkg.is_past;
            const color = isCurrent ? '#237292' : isPast ? '#2ECC8A' : '#8FA3B3';
            const delayedCount = (pkg.mosques || []).filter(m => m.days_delay > 0).length;

            const card = document.createElement('div');
            card.className = `sb-pkg-card ${isCurrent ? 'current' : isPast ? 'past' : 'future'}`;
            card.dataset.pkgId = pkg.id;
            card.innerHTML = `
      <div class="sb-pkg-card-inner" onclick="loadMosqueDetailGlobal(${pkg.mosques?.[0]?.id || 0})">
        <div class="sb-pkg-top">
          <div class="sb-pkg-dot" style="background:${color}"></div>
          <div style="flex:1;min-width:0">
            <div class="sb-pkg-code">${pkg.code}</div>
            <div class="sb-pkg-name">${pkg.name}</div>
          </div>
          ${isCurrent ? '<div class="sb-pkg-live">● نشط</div>' : ''}
          ${isPast ? '<div class="sb-pkg-done">✓</div>' : ''}
        </div>
        <div class="sb-pkg-stats">
          <div class="sb-pkg-stat">
            <span class="sb-pkg-stat-val" style="color:${color}">${pkg.avg_kpi}%</span>
            <span class="sb-pkg-stat-lbl">KPI</span>
          </div>
          <div class="sb-pkg-stat">
            <span class="sb-pkg-stat-val">${pkg.mosque_count}</span>
            <span class="sb-pkg-stat-lbl">مسجد</span>
          </div>
          ${delayedCount > 0 ? `
          <div class="sb-pkg-stat">
            <span class="sb-pkg-stat-val" style="color:var(--red)">${delayedCount}</span>
            <span class="sb-pkg-stat-lbl">متأخر</span>
          </div>` : ''}
        </div>
        <div class="sb-pkg-bar">
          <div class="sb-pkg-bar-fill"
               style="width:${pkg.avg_kpi}%;background:${color}"></div>
        </div>
      </div>`;

            container.appendChild(card);
        });
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
                meta: `${m.code} · KPI ${m.overall_kpi}%`,
                color: dotColor(m.overall_kpi), id: m.id,
            }));

            S.packages.filter(p =>
                p.name?.toLowerCase().includes(q) ||
                p.code?.toLowerCase().includes(q)
            ).slice(0, 3).forEach(p => results.push({
                type: 'package', label: p.name,
                meta: `${p.mosque_count} مساجد · KPI ${p.avg_kpi}%`,
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
    async function loadMosqueDetail(mosqueId) {
        S.activeMosqueId = mosqueId;
        const mosque = S.mosques.find(m => m.id === mosqueId);

        if (mosque) {
            $('topbar-title').textContent = mosque.name;
            $('topbar-sub').textContent =
                `${mosque.code} · ${mosque.package || ''} · ${stateLabel(mosque.state)}` +
                (mosque.days_delay > 0 ? ` · ⚠ تأخير ${mosque.days_delay} يوم` : '');
        }

        const content = $('mosque-detail-content');
        if (content) {
            content.innerHTML = `
        <div style="padding:40px;text-align:center">
          <div class="loading-spinner" style="width:32px;height:32px;margin:0 auto"></div>
          <div style="margin-top:12px;color:var(--text3);font-size:12px">
            جاري تحميل بيانات المسجد...
          </div>
        </div>`;
        }

        const data = await apiGet(`/dashboard/api/mosque/${mosqueId}`);
        if (!data.mosque) return;

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

        $('section-mosque')?.scrollIntoView({behavior: 'smooth', block: 'start'});
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
      قيمة العقد: ${fmt(m.contract_value)} ر
    </span>
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
        <div class="kpi-ring-val" style="font-size:16px;color:var(--primary)">
          ${pct(m.overall_kpi)}
        </div>
      </div>
      <div class="kpi-ring-wrap">
        <canvas id="ring-time" width="72" height="72"></canvas>
        <div class="kpi-ring-label">زمني (35%)</div>
        <div class="kpi-ring-val" style="color:var(--green)">${pct(m.time_kpi)}</div>
      </div>
      <div class="kpi-ring-wrap">
        <canvas id="ring-visit" width="72" height="72"></canvas>
        <div class="kpi-ring-label">إشرافي (25%)</div>
        <div class="kpi-ring-val" style="color:var(--primary-l)">
          ${pct(m.visit_compliance)}
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Tabs -->
<div class="tab-row">
  <button class="tab-btn active" data-tab="tasks">المهام</button>
  <button class="tab-btn" data-tab="financial">
    المالي
    ${pendingCerts > 0 ? `<span class="tab-badge red">${pendingCerts}</span>` : ''}
    ${pendingCOs > 0 ? `<span class="tab-badge orange">${pendingCOs}</span>` : ''}
  </button>
  <button class="tab-btn" data-tab="boq">جداول الكميات</button>
  <button class="tab-btn" data-tab="visits">الزيارات والحضور</button>
</div>

<!-- Tasks -->
<div class="tab-panel active" data-tab-panel="tasks">
  <div class="task-list">${buildTasksHTML(data.tasks)}</div>
</div>

<!-- Financial -->
<div class="tab-panel" data-tab-panel="financial">
  <div class="fin-kpi-row">
    <div class="fin-kpi-card">
      <div class="fin-kpi-val">${fmt(totalCertVal)} ر</div>
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
<div class="tab-panel" data-tab-panel="boq">
  <div style="position:relative;width:100%;height:220px;margin-bottom:16px">
    <canvas id="boq-chart"></canvas>
  </div>
  <table class="boq-table">
    <tr><th>الفئة</th><th>تعاقدي (ر)</th><th>منفذ (ر)</th><th>نسبة</th></tr>
    ${(data.boq_categories || []).map(cat => {
            const pv = cat.contracted > 0
                ? Math.round(cat.executed / cat.contracted * 100) : 0;
            return `<tr>
        <td style="font-weight:600">${cat.name}</td>
        <td>${fmt(cat.contracted)}</td>
        <td style="color:var(--primary);font-weight:600">${fmt(cat.executed)}</td>
        <td>
          <div class="boq-bar-wrap">
            <div class="boq-bar-fill"
                 style="width:${pv}%;background:${pv > 90 ? 'var(--orange)' : 'var(--primary)'}">
            </div>
          </div>
          <span style="font-size:10px;color:var(--text3)">${pv}%</span>
        </td>
      </tr>`;
        }).join('')}
  </table>
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
        <div class="cert-amount">${fmt(c.total_value)} ر</div>
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
        <div class="cert-amount">${fmt(co.amount)} ر</div>
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
        ${[['القيمة الإجمالية', `${fmt(cert.total_value)} ر`, 'var(--primary)'],
            ['القيمة الصافية', `${fmt(cert.net_value || cert.total_value)} ر`, 'var(--navy)'],
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
              <td>${fmt(l.value)} ر</td>
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
        ${[['قيمة التغيير', `${fmt(co.amount)} ر`, 'var(--gold)'],
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
        const badge = $('onsite-count-badge');
        if (badge) badge.textContent = `${data.length} في الموقع`;
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
            : `<div style="text-align:center;padding:20px;color:var(--text3);font-size:12px">
           لا يوجد مستشارون في المواقع حالياً</div>`;
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
        const interval = (CONFIG.refresh_interval || 60) * 1000;
        S.refreshTimer = setInterval(async () => {
            loadOnSite();
            checkLiveStream();
            const [sum, alerts, insights] = await Promise.all([
                apiGet('/dashboard/api/summary'),
                apiGet('/dashboard/api/alerts'),
                apiGet('/dashboard/api/ai_insights'),
            ]);
            renderSummary(sum);
            renderAlerts(alerts);
            renderAIInsights(insights);
            if (S.activeMosqueId) loadMosqueDetail(S.activeMosqueId);
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