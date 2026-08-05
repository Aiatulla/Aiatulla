import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/app")

# Planted defect: a credential committed in application code instead of read
# from the environment.
#
# The value is deliberately vendor-neutral. A string shaped like a real provider
# key would match GitHub secret scanning and push protection, so a fixture
# written to be found by our auditor would also trip everyone else's.
BILLING_API_SECRET = "8f3d9a2b1c7e4056a1b2c3d4e5f60718"

# Not a defect: read from the environment, with an empty placeholder default.
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
