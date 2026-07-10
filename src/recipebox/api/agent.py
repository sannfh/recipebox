import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

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


@router.post("/chat/stream")
async def chat_stream(
    body: AgentChatRequest,
    agent: Annotated[Agent, Depends(get_agent)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> StreamingResponse:
    """SSE sibling of POST /agent/chat for the UI. Emits step/token/done events as the agent
    works. Rate-limit and auth are enforced before the stream opens (normal 4xx); a failure
    mid-stream arrives as a final {"type": "error"} event, since the HTTP status is already
    committed once streaming has started."""
    if not await limiter.allow(user_key=str(current_user.id)):
        raise RateLimitedError("Rate limit exceeded — try again in a moment")

    async def event_source() -> AsyncIterator[str]:
        try:
            async for event in agent.chat_stream(user_message=body.message, history=body.history):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as exc:  # headers already sent; surface failure as an SSE event, not a 500
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/cache-stats")
async def cache_stats() -> dict[str, Any]:
    """Cumulative hit/miss counts since process start. Used by the benchmark."""
    return {
        "embeddings": {"hits": EMBED_STATS.hits, "misses": EMBED_STATS.misses, "hit_rate": EMBED_STATS.hit_rate},
        "rag": {"hits": RAG_STATS.hits, "misses": RAG_STATS.misses, "hit_rate": RAG_STATS.hit_rate},
    }
