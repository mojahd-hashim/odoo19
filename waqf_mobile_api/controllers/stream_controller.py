# ── GET /api/waqf/livestream/url ─────────────────────────────
@http.route('/api/waqf/livestream/url',
            type='http', auth='none', methods=['GET'], csrf=False)
@require_token
def get_livestream_url(self, employee=None, **kwargs):
    """
    يرجع رابط البث المباشر للمسجد النشط حالياً.
    يحدد المسجد من:
    ① mosque_id في query params (اختياري)
    ② آخر checkin نشط للمستخدم
    """
    portal_user = kwargs.get('portal_user')
    mosque_id   = request.httprequest.args.get('mosque_id')

    # تحديد المسجد
    if not mosque_id:
        # من الـ checkin النشط
        if employee:
            active = request.env['mosque.attendance'].sudo().search([
                ('engineer_id', '=', employee.id),
                ('check_out',   '=', False),
            ], limit=1)
        elif portal_user:
            active = request.env['mosque.attendance'].sudo().search([
                ('portal_user_id', '=', portal_user.user_id.id),
                ('check_out',      '=', False),
            ], limit=1)
        else:
            return api_response(error='Unauthorized', status=401)

        if not active:
            return api_response(data={
                'has_stream': False,
                'message':    'لا يوجد تسجيل حضور نشط',
            })
        mosque_id = active.mosque_id.id
    else:
        mosque_id = int(mosque_id)

    # البحث عن بث نشط لهذا المسجد
    stream = request.env['waqf.live.stream'].sudo().search([
        ('mosque_id', '=', mosque_id),
        ('is_active', '=', True),
    ], order='start_time desc', limit=1)

    if not stream:
        mosque = request.env['mosque.mosque'].sudo().browse(mosque_id)
        return api_response(data={
            'has_stream':  False,
            'mosque_id':   mosque_id,
            'mosque_name': mosque.name if mosque.exists() else '',
            'message':     'لا يوجد بث مباشر نشط لهذا المسجد',
        })

    return api_response(data={
        'has_stream':  True,
        'stream_id':   stream.id,
        'stream_url':  stream.stream_url,
        'stream_name': stream.name,
        'mosque_id':   stream.mosque_id.id,
        'mosque_name': stream.mosque_id.name,
        'start_time':  str(stream.start_time) if stream.start_time else '',
        'viewers':     stream.viewers,
    })


# ── POST /api/waqf/livestream/start ──────────────────────────
@http.route('/api/waqf/livestream/start',
            type='http', auth='none', methods=['POST'], csrf=False)
@require_token
def start_livestream(self, employee=None, **kwargs):
    """
    ينشئ جلسة بث جديدة.
    Request: {"mosque_id": 12, "stream_url": "rtmp://...", "title": "زيارة ميدانية"}
    """
    portal_user = kwargs.get('portal_user')
    body        = get_json_body()
    mosque_id   = body.get('mosque_id')
    stream_url  = body.get('stream_url', '').strip()
    title       = body.get('title', 'بث مباشر').strip()

    if not mosque_id or not stream_url:
        return api_response(
            error='mosque_id و stream_url مطلوبان', status=400)

    # أوقف أي بث سابق لنفس المسجد
    request.env['waqf.live.stream'].sudo().search([
        ('mosque_id', '=', int(mosque_id)),
        ('is_active', '=', True),
    ]).write({'is_active': False,
              'end_time':  fields.Datetime.now()})

    stream = request.env['waqf.live.stream'].sudo().create({
        'name':       title,
        'mosque_id':  int(mosque_id),
        'stream_url': stream_url,
        'started_by': employee.id if employee else False,
        'is_active':  True,
    })

    return api_response(data={
        'stream_id':  stream.id,
        'stream_url': stream.stream_url,
        'mosque_id':  int(mosque_id),
    })


# ── POST /api/waqf/livestream/stop ───────────────────────────
@http.route('/api/waqf/livestream/stop',
            type='http', auth='none', methods=['POST'], csrf=False)
@require_token
def stop_livestream(self, employee=None, **kwargs):
    """إيقاف البث النشط. Request: {"stream_id": 5}"""
    body      = get_json_body()
    stream_id = body.get('stream_id')
    if not stream_id:
        return api_response(error='stream_id مطلوب', status=400)

    stream = request.env['waqf.live.stream'].sudo().browse(int(stream_id))
    if stream.exists():
        stream.write({'is_active': False, 'end_time': fields.Datetime.now()})

    return api_response(data={'stopped': True, 'stream_id': stream_id})