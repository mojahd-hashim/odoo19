from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
import werkzeug


class WaqfLandingController(http.Controller):

    @http.route('/', type='http', auth='public', website=True)
    def landing_page(self, **kwargs):
        """
        Waqf branded landing page.
        Logged-in users → redirect to /odoo.
        Public → show landing with 3 gates.
        """
        if request.env.user and request.env.user.id != request.env.ref('base.public_user').id:
            return request.redirect('/odoo')

        company = request.env.user.company_id
        return request.render('waqf_portal_theme.tmpl_landing', {
            'company': company,
        })


class WaqfLoginController(AuthSignupHome):
    """Override login page with branded split-screen design."""

    @http.route('/web/login', type='http', auth='none', sitemap=False)
    def web_login(self, redirect=None, **kw):
        """Render branded login page."""
        response = super().web_login(redirect=redirect, **kw)

        # If it's a redirect (already logged in), pass through
        if isinstance(response, werkzeug.wrappers.Response) and \
                response.status_code in (301, 302, 303):
            return response

        company = request.env['res.company'].sudo().search([], limit=1)

        # Get values from parent response
        qcontext = getattr(response, 'qcontext', {})
        qcontext['company'] = company

        return request.render('waqf_portal_theme.tmpl_login', qcontext)
