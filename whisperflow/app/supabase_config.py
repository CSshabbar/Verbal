"""Shared Supabase project constants — zero internal dependencies.

Split out of `app/sync.py` (MER-29) so `app/auth.py` can import these without
creating a cycle: auth.py needs the constants, and sync.py (plus most other
REST call sites) needs `app.auth.auth_header` for per-user JWT forwarding.
"""

SUPABASE_URL = "https://ovpcthjingugwvpxlsna.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92cGN0aGppbmd1Z3d2cHhsc25hIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNjQzMDYsImV4cCI6MjA5Mzg0MDMwNn0"
    ".XwTBo8L-aEUmmSl6dJXNqA2QXzGFOpIVB5W9eDI8j28"
)
REST_URL = f"{SUPABASE_URL}/rest/v1"
