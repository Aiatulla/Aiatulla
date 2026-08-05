import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/app")

# Read from the environment rather than written into source.
BILLING_API_SECRET = os.getenv("BILLING_API_SECRET")

# Not a defect: read from the environment, with an empty placeholder default.
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
