from typing import Annotated

from fastapi import Header, HTTPException, status
from pydantic import SecretStr

from app.llm.providers import UnknownProviderError, provider_for_key

HEADER_NAME = "X-LLM-Key"


def require_api_key(
    x_llm_key: Annotated[str | None, Header(alias=HEADER_NAME)] = None,
) -> SecretStr:
    """Take the caller's own model key from the request header.

    Bring your own key: the key belongs to whoever is calling. It is used for the
    length of one run and never written to the database, a log, or a response.
    Wrapping it in SecretStr means an accidental log line prints asterisks
    instead of the key.

    The key is validated here rather than at the first model call, so a caller
    with a bad key learns immediately instead of after a repository is cloned.
    """
    if not x_llm_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Provide your own model API key in the {HEADER_NAME} header.",
        )

    try:
        provider_for_key(x_llm_key)
    except UnknownProviderError as exc:
        # str(exc) never contains the key, by construction in provider_for_key.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SecretStr(x_llm_key)
