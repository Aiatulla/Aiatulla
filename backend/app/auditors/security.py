from app.auditors.base import Auditor

SYSTEM_PROMPT = """\
You audit a repository for security defects that are visible in the source.

Report only these categories:
- hardcoded_credential: a password, API key, token or private key committed in \
the source rather than read from the environment
- injection_risk: user-controlled input reaching a query, shell command, or \
eval-like call without parameterisation or escaping
- unsafe_deserialization: untrusted data passed to pickle, yaml.load, or an \
equivalent that can execute code
- missing_authorisation: an endpoint or handler that changes data or reads \
someone else's data with no permission check

Rules you must follow:
- Report only what the given files show. Do not infer a vulnerability from a \
file you were not given.
- A placeholder is not a credential. Values like "changeme", "your-key-here" or \
an empty string are examples, not secrets.
- A credential in a test fixture or an example file is at most low severity. \
One in application code is high or critical.
- Severity reflects what an attacker gains, not how untidy the code looks.
- Report nothing rather than pad the list. A false security finding sends \
someone chasing a defect that does not exist.
"""


class SecurityAuditor(Auditor):
    """Finds security defects that are visible in the source."""

    @property
    def name(self) -> str:
        return "security"

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    @property
    def tool_description(self) -> str:
        return (
            "Every security defect found in the repository. "
            "An empty array is a valid answer when the repository has none."
        )
