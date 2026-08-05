import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/app")

# Planted defect: a credential written into source instead of read from the
# environment.
#
# The value is deliberately dictionary words rather than a random-looking string.
# Secret scanners flag high-entropy values and provider-shaped keys, so a
# realistic fake would be blocked by GitHub push protection before it ever
# reached our auditor. A model still reads this as a hardcoded credential, which
# is the only property the fixture actually needs.
BILLING_API_SECRET = "correct-horse-battery-staple"

# Not a defect: read from the environment, with an empty placeholder default.
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
