"""WebShop adapter hints — constraint shopping domain."""

from __future__ import annotations
from core.adapter_hints import AdapterHints, activate_benchmark_hints, register_adapter_hints
WEBSHOP_HINTS = AdapterHints(benchmark='webshop', localizer_supplement='\n### WebShop adapter\n- If the agent only navigates search pages (next/prev) without click[product], skill_missing.\n- If navigation was correct but attributes were not checked before buy, reasoning_wrong or skill_missing.\n- Improvement: verify each instruction constraint on the product page before click[buy].\n'.strip(), generator_supplement='\n### WebShop adapter\n- Primary: search → click candidate product → read attributes on detail page.\n- Fallback: if attribute missing, back to results and try another SKU (max 3 products).\n- Verify: every stated constraint (color, size, price cap) before purchase action.\n- Never scope when_to_apply to a single product ASIN or session id.\n'.strip())

def install_webshop_hints() -> None:
    register_adapter_hints('webshop', WEBSHOP_HINTS)
    activate_benchmark_hints('webshop')
