"""Eval-suite bootstrap.

Two jobs, both before any network client is constructed:

1. **truststore** — route outbound TLS (OpenAI judge + embeddings, Anthropic
   agent) through the OS certificate store. On a proxied/corporate network the
   proxy's CA lives in the OS store, not in certifi's bundle, so without this
   deepeval's HTTPS calls fail with an "unknown issuer" error. This is the same
   thing scripts/embed_reference_recipes.py does.

2. **key mapping** — the app reads ``APP_OPENAI_API_KEY`` (pydantic-settings
   prefix). deepeval's LLM-judge reads the unprefixed ``OPENAI_API_KEY``. Bridge
   the two so one .env drives both.
"""

import os

import truststore

truststore.inject_into_ssl()

os.environ.setdefault("APP_SECRET_KEY", "eval-secret-not-for-production")

from recipebox.config import settings  # noqa: E402

# deepeval's judge model looks for OPENAI_API_KEY; the app stores it prefixed.
if settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
