# -*- coding: utf-8 -*-
"""Shared helpers for the executive dashboard.

- Riyadh time (UTC+3) conversion for anything shown to users.
- Live per-mosque progress: stored fields such as time_progress / days_delay
  depend on "today" but are only recomputed when their dependencies change,
  so the dashboard recomputes them on the fly from the planned dates.
"""
from datetime import date, datetime, time

import pytz

RIYADH = pytz.timezone('Asia/Riyadh')

DONE_STATES = ('initial_hov', 'final_hov', 'warranty', 'closed')


# ── Time ─────────────────────────────────────────────────────────
def riyadh_now():
    return datetime.now(pytz.utc).astimezone(RIYADH)


def riyadh_today():
    return riyadh_now().date()


def to_riyadh(dt):
    """Naive UTC datetime (as stored by Odoo) → aware Riyadh datetime."""
    if not dt:
        return None
    return pytz.utc.localize(dt).astimezone(RIYADH)


def fmt_riyadh(dt, pattern='%H:%M'):
    local = to_riyadh(dt)
    return local.strftime(pattern) if local else ''


def riyadh_day_start_utc(day=None):
    """Start of the given Riyadh day as a naive UTC datetime (for domains)."""
    day = day or riyadh_today()
    local_midnight = RIYADH.localize(datetime.combine(day, time.min))
    return local_midnight.astimezone(pytz.utc).replace(tzinfo=None)


# ── Domains ──────────────────────────────────────────────────────
def mosque_domain(env):
    Mosque = env['mosque.mosque']
    return [('is_demo', '=', False)] if 'is_demo' in Mosque._fields else []


def current_package(env, today=None):
    today = today or riyadh_today()
    return env['mosque.package'].sudo().search([
        ('planned_start', '<=', today),
        ('planned_end', '>=', today),
    ], order='planned_start desc', limit=1)


# ── Progress ─────────────────────────────────────────────────────
def mosque_perf(m, today=None):
    """Actual vs planned progress for one mosque, computed for today.

    actual   = executed BOQ value / contracted BOQ value (financial_progress)
    planned  = share of the planned duration already elapsed
    status   = done | not_started | critical | warning | ok
    """
    today = today or riyadh_today()
    actual = round(m.financial_progress or 0.0, 1)

    planned = 0.0
    delay = 0
    if m.planned_start and m.planned_end:
        total = (m.planned_end - m.planned_start).days or 1
        planned = max(0.0, min(100.0, (today - m.planned_start).days / total * 100))
        if today > m.planned_end and actual < 100 and m.state not in DONE_STATES:
            delay = (today - m.planned_end).days
    planned = round(planned, 1)
    variance = round(actual - planned, 1)

    started = bool(m.planned_start and m.planned_start <= today)
    if m.state in DONE_STATES or actual >= 100:
        status = 'done'
    elif not started and actual == 0:
        status = 'not_started'
    elif delay > 0 or variance <= -20:
        status = 'critical'
    elif variance <= -10:
        status = 'warning'
    else:
        status = 'ok'

    # Schedule performance index (actual / planned), capped at 100
    if planned > 0:
        spi = round(min(100.0, actual / planned * 100), 1)
    else:
        spi = 100.0 if actual > 0 else None

    contracted = m.total_boq_value or 0.0
    return {
        'actual_pct': actual,
        'planned_pct': planned,
        'variance': variance,
        'days_delay': delay,
        'status': status,
        'spi': spi,
        'contract_value': m.contract_value or contracted,
        'boq_value': contracted,
        'executed_value': round(contracted * actual / 100.0, 2),
    }


# ── On-site consultants ──────────────────────────────────────────
DAILY_HOURS = 8.0


def _person_key(a):
    if a.engineer_id:
        return ('e', a.engineer_id.id)
    if 'portal_user_id' in a._fields and a.portal_user_id:
        return ('u', a.portal_user_id.id)
    return ('a', a.id)


def onsite_list(env):
    """Open check-ins since the start of today (Riyadh time), with each
    engineer's total minutes today across all mosques (target: 8 hours)."""
    now_utc = datetime.utcnow()
    Att = env['mosque.attendance'].sudo()
    today_all = Att.search([('check_in', '>=', riyadh_day_start_utc())])
    day_minutes, day_mosques = {}, {}
    for a in today_all:
        key = _person_key(a)
        end = a.check_out or now_utc
        day_minutes[key] = day_minutes.get(key, 0) + max(0, int((end - a.check_in).total_seconds() // 60))
        day_mosques.setdefault(key, set()).add(a.mosque_id.id)

    result = []
    for a in today_all.filtered(lambda x: not x.check_out).sorted('check_in'):
        m = a.mosque_id
        person = a.engineer_id.name if a.engineer_id else ''
        if not person and 'portal_user_id' in a._fields and a.portal_user_id:
            person = a.portal_user_id.name
        minutes = int((now_utc - a.check_in).total_seconds() // 60) if a.check_in else 0
        result.append({
            'id': a.id,
            'name': person or 'مستشار',
            'mosque_id': m.id if m else None,
            'mosque': m.name if m else '',
            'code': m.code if m else '',
            'lat': m.latitude if m else 0,
            'lng': m.longitude if m else 0,
            'checkin': fmt_riyadh(a.check_in, '%H:%M'),
            'checkin_iso': to_riyadh(a.check_in).isoformat() if a.check_in else '',
            'elapsed_min': max(0, minutes),
            'validated': bool(a.is_validated),
            'gps': bool(a.gps_validated),
            'today_min': day_minutes.get(_person_key(a), 0),
            'today_target_min': int(DAILY_HOURS * 60),
            'today_mosques': len(day_mosques.get(_person_key(a), ())),
        })
    return result
