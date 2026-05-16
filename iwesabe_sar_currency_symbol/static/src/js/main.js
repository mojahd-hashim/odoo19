/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";

function applySymbolFont() {
    const currencyRegex = /[$€₹¥₩₽₺₪₫฿₴₦]/;
    document.querySelectorAll("*").forEach((el) => {
        const text = el.textContent?.trim();

        if (text) {
            // Apply to numeric text
            if (/^\d+(\.\d+)?$/.test(text)) {
                el.style.fontFamily = "'sr_symbol'";
            }

            // Apply to text with currency symbols
            if (currencyRegex.test(text)) {
                el.style.fontFamily = "'sr_symbol'";
            }
        }
    });
}

patch(WebClient.prototype, {
    setup() {
        super.setup();

        // Apply once DOM is ready
        setTimeout(() => applySymbolFont(), 500);

        // Observe changes
        const observer = new MutationObserver(() => {
            applySymbolFont();
        });
        observer.observe(document.body, { childList: true, subtree: true });
    },
});
