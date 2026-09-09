"""Safety-first Playwright application primitives.

Dedicated per-site adapters must explicitly opt into submission. This generic adapter
only prepares factual answers and never bypasses authentication, CAPTCHA, or controls.
"""
from backend.config import load_preferences
def prepare_answers(profile): return {k:profile.get(k,"") for k in ("name","email","phone","location")}
def may_submit(explicit_confirmation=False):
 return load_preferences().get("application_mode")=="AUTO_APPLY" and explicit_confirmation
