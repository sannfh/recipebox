from typing import Annotated, Any

from fastapi import APIRouter, Depends

from recipebox.core.agent import Agent
from recipebox.core.cache import EMBED_STATS, RAG_STATS
from recipebox.core.rate_limit import RateLimiter
from recipebox.deps import get_agent, get_current_user, get_rate_limiter
from recipebox.domain.errors import RateLimitedError
from recipebox.domain.schemas import AgentChatRequest, AgentChatResponse, UserInDB

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat", response_model=AgentChatResponse)
async def chat(
    body: AgentChatRequest,
    agent: Annotated[Agent, Depends(get_agent)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> AgentChatResponse:
    if not await limiter.allow(user_key=str(current_user.id)):
        raise RateLimitedError("Rate limit exceeded — try again in a moment")
    return await agent.chat(user_message=body.message, history=body.history)


@router.get("/cache-stats")
async def cache_stats() -> dict[str, Any]:
    """Cumulative hit/miss counts since process start. Used by the benchmark."""
    return {
        "embeddings": {"hits": EMBED_STATS.hits, "misses": EMBED_STATS.misses, "hit_rate": EMBED_STATS.hit_rate},
        "rag": {"hits": RAG_STATS.hits, "misses": RAG_STATS.misses, "hit_rate": RAG_STATS.hit_rate},
    }
