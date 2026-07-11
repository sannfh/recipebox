"""Traced, hermetic runner for the RecipeBox agent.

This is the "app under eval". It runs the **real** ``Agent`` and the **real**
Claude tool-use loop — nothing about the agent is mocked. Only the environment is
swapped for a test double: retrieval is served by an in-memory repo seeded from
real recipes (see ``corpus.py``) instead of Postgres, and the pantry is fixed.
That keeps evals runnable with just the two API keys, no database.

Instrumentation is manual ``@observe`` (the app is a hand-rolled loop, not a
supported framework integration). Each decorated function becomes a span
DeepEval can score:

    recipe_agent (agent span)          <- final reply + all retrieved context
      └─ search_recipes (retriever)    <- query + retrieved recipes  [ContextualRelevancy]
      └─ get_recipe_details (tool)
      └─ get_pantry (tool)

``update_current_span`` writes the fields metrics read (``input``,
``output``, ``retrieval_context``). We accumulate retrieval_context across every
tool that feeds the model real recipe text, then attach it to the root span so
end-to-end Faithfulness scores the answer against everything the agent saw.
"""

from __future__ import annotations

from typing import Any

from deepeval.tracing import observe, update_current_span, update_current_trace

from recipebox.config import settings
from recipebox.core.agent import Agent, Tool, _extract_recipe_ids, build_anthropic_client
from recipebox.core.embeddings import OpenAIEmbedder
from recipebox.domain.schemas import AgentChatResponse
from recipebox.domain.services import RecipeSearchService
from recipebox.repositories.memory import InMemoryReferenceRecipeRepository
from tests.evals.corpus import build_reference_repo
from tests.evals.metrics import retriever_span_metrics

# A fixed pantry so pantry-aware advice (substitutions, "what you're missing") is
# actually exercised by the eval.
PANTRY: list[dict[str, Any]] = [
    {"name": "chicken breast", "quantity": 500, "unit": "g"},
    {"name": "rice", "quantity": 1, "unit": "kg"},
    {"name": "onion", "quantity": 3, "unit": ""},
    {"name": "garlic", "quantity": 1, "unit": "bulb"},
    {"name": "olive oil", "quantity": 500, "unit": "ml"},
    {"name": "canned tomatoes", "quantity": 2, "unit": "cans"},
    {"name": "pasta", "quantity": 500, "unit": "g"},
    {"name": "eggs", "quantity": 6, "unit": ""},
    {"name": "parmesan", "quantity": 100, "unit": "g"},
    {"name": "spinach", "quantity": 200, "unit": "g"},
]

# Seed the corpus + embedder once per process — reused across every golden.
_repo: InMemoryReferenceRecipeRepository | None = None
_embedder: OpenAIEmbedder | None = None


async def _seeded() -> tuple[InMemoryReferenceRecipeRepository, OpenAIEmbedder]:
    global _repo, _embedder
    if _repo is None:
        _embedder = OpenAIEmbedder()
        _repo = await build_reference_repo(_embedder)
    assert _embedder is not None
    return _repo, _embedder


def _build_tools(
    search_service: RecipeSearchService,
    repo: InMemoryReferenceRecipeRepository,
    retrieval_context: list[str],
) -> list[Tool]:
    """The three production tools, re-wired to the in-memory backend and wrapped
    in spans. Schemas are copied verbatim from deps.get_agent so Claude sees the
    exact same tool contract it sees in production."""

    @observe(type="retriever", name="search_recipes", metrics=retriever_span_metrics())
    async def _search(inp: dict[str, Any]) -> list[dict[str, Any]]:
        query = inp["query"]
        top_k = min(int(inp.get("top_k", 5)), 10)
        hits = await search_service.search(query=query, top_k=top_k)
        out = [
            {"id": h.id, "title": h.title, "url": h.url, "source_site": h.source_site, "score": round(h.score, 3)}
            for h in hits
        ]
        # Expose real recipe content (title + description + category), not just the
        # title — ContextualRelevancy judges each retrieved chunk against the query,
        # and a bare title gives it nothing to match the user's ingredients on.
        ctx = [
            f"Recipe #{h.id}: {h.title}."
            + (f" {h.description}" if h.description else "")
            + (f" [{h.category}]" if h.category else "")
            for h in hits
        ]
        retrieval_context.extend(ctx)
        update_current_span(input=query, retrieval_context=ctx)
        return out

    @observe(type="tool", name="get_pantry")
    async def _pantry(_inp: dict[str, Any]) -> list[dict[str, Any]]:
        update_current_span(output=PANTRY)
        return PANTRY

    @observe(type="tool", name="get_recipe_details")
    async def _details(inp: dict[str, Any]) -> dict[str, Any] | None:
        rid = int(inp["recipe_id"])
        detail = await repo.get_detail(rid)
        out = detail.model_dump() if detail else None
        if detail is not None:
            ctx = (
                f"Recipe #{detail.id} ({detail.title}) — ingredients: "
                f"{'; '.join(detail.ingredients)}. instructions: {' '.join(detail.instructions)}"
            )
            retrieval_context.append(ctx)
            update_current_span(input=str(rid), retrieval_context=[ctx])
        return out

    return [
        Tool(
            schema={
                "name": "search_recipes",
                "description": (
                    "Semantic search over a verified corpus of 16,000+ recipes. "
                    "Returns ranked hits with id, title, url, and similarity score."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural-language description of what to cook."},
                        "top_k": {"type": "integer", "description": "Number of results (max 10).", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            handler=_search,
            cites_recipes=True,
        ),
        Tool(
            schema={
                "name": "get_pantry",
                "description": "Return the current user's pantry inventory: list of {name, quantity, unit}.",
                "input_schema": {"type": "object", "properties": {}},
            },
            handler=_pantry,
        ),
        Tool(
            schema={
                "name": "get_recipe_details",
                "description": "Fetch full ingredients and instructions for a recipe by its numeric id.",
                "input_schema": {
                    "type": "object",
                    "properties": {"recipe_id": {"type": "integer"}},
                    "required": ["recipe_id"],
                },
            },
            handler=_details,
            cites_recipes=True,
        ),
    ]


@observe(type="agent", name="recipe_agent")
async def run_recipe_agent(user_message: str) -> AgentChatResponse:
    """Run the real agent on one user message and record the trace.

    Returns the full ``AgentChatResponse`` so the test can also assert the
    code-based citation invariant on the same single (paid) agent run.
    """
    repo, embedder = await _seeded()
    search_service = RecipeSearchService(repo=repo, embedder=embedder)
    retrieval_context: list[str] = []
    tools = _build_tools(search_service, repo, retrieval_context)
    agent = Agent(client=build_anthropic_client(), model=settings.anthropic_model, tools=tools)

    response = await agent.chat(user_message, history=[])

    # End-to-end metrics (Faithfulness, AnswerRelevancy, …) read the *trace*, not
    # this span — so retrieval_context must be set at the trace level or
    # Faithfulness is silently skipped for lack of a grounding context.
    update_current_trace(
        input=user_message,
        output=response.reply,
        retrieval_context=retrieval_context,
    )
    update_current_span(input=user_message, output=response.reply)
    return response


def citations_grounded(response: AgentChatResponse) -> bool:
    """Deterministic, judge-free invariant: every recipe id the agent *cited* was
    actually returned by some tool call. This is RecipeBox's anti-hallucination
    contract and needs no LLM to check."""
    returned: set[int] = set()
    for step in response.steps:
        returned.update(_extract_recipe_ids(step.output))  # type: ignore[arg-type]
    return set(response.citations) <= returned
