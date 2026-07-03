"""Claude-driven recipe agent.

Architecture: manual tool-use loop. We don't use anthropic's tool runner because we need
visibility into each tool call (citations, steps) to expose in the API response.

How hallucinations are eliminated:
- The system prompt is the *only* recipe knowledge Claude has.
- Recipes only enter the conversation through tool results we control.
- Claude is instructed to cite every recommendation by numeric id.
- The harness records every cited id; the caller can verify that no recipe was invented.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import truststore
from anthropic import AsyncAnthropic

from recipebox.config import settings
from recipebox.domain.schemas import AgentChatResponse, AgentMessage, AgentToolCall

# Max tool-use rounds before we abort. Real agents go 5-15 calls.
MAX_ITERATIONS = 10
MAX_TOKENS = 4096

SYSTEM_PROMPT = """You are RecipeBox, an AI cooking assistant.

Your job: help the user pick a recipe and adapt it to what they have on hand.

Available tools:
- search_recipes(query, top_k): semantic search over a verified corpus of 16,000 recipes. \
Call this BEFORE recommending anything — you may only recommend recipes that come back from this tool \
or get_recipe_details.
- get_pantry(): the user's current pantry inventory.
- get_recipe_details(recipe_id): full ingredients and instructions for one recipe.

Rules:
1. NEVER invent recipes, ingredients, or source URLs. Recommend only recipes returned by your tools.
2. ALWAYS cite recipes by their numeric id, like "(recipe #4950)".
3. Before recommending, check get_pantry() so you can flag what the user is missing and \
suggest substitutions from what they have.
4. Keep the final answer short and useful — a recipe pick, a quick reason it fits, what to swap \
or buy, and the source URL.
5. If the user asks something unrelated to cooking, politely redirect.
"""


@dataclass
class Tool:
    """One tool exposed to the agent. The schema is what Claude sees; handler is what we run."""

    schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[Any]]
    cites_recipes: bool = False  # if True, scrape ids from output for the citations list


def _extract_recipe_ids(output: Any) -> list[int]:
    """Pull recipe ids out of a tool result so we can build the citations list."""
    if isinstance(output, list):
        return [item["id"] for item in output if isinstance(item, dict) and "id" in item]
    if isinstance(output, dict) and "id" in output:
        return [output["id"]]
    return []


class Agent:
    def __init__(self, client: AsyncAnthropic, model: str, tools: list[Tool]) -> None:
        self._client = client
        self._model = model
        self._tools = {t.schema["name"]: t for t in tools}

    @property
    def _tool_schemas(self) -> list[dict[str, Any]]:
        return [t.schema for t in self._tools.values()]

    async def chat(self, user_message: str, history: list[AgentMessage]) -> AgentChatResponse:
        messages: list[dict[str, Any]] = [
            *({"role": h.role, "content": h.content} for h in history),
            {"role": "user", "content": user_message},
        ]
        steps: list[AgentToolCall] = []
        citations: set[int] = set()

        for _ in range(MAX_ITERATIONS):
            # cache_control on the top-level call caches system prompt + tool defs together
            # (tools render before system, so the marker covers both — see prompt-caching docs).
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=self._tool_schemas,
                messages=messages,
                cache_control={"type": "ephemeral"},
            )

            if response.stop_reason == "end_turn":
                reply = next((b.text for b in response.content if b.type == "text"), "")
                return AgentChatResponse(reply=reply, citations=sorted(citations), steps=steps)

            # tool_use: execute every tool block in the response, append results, loop.
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                # Defensive: stop_reason wasn't end_turn but no tools either; treat as done.
                reply = next((b.text for b in response.content if b.type == "text"), "")
                return AgentChatResponse(reply=reply, citations=sorted(citations), steps=steps)

            messages.append({"role": "assistant", "content": response.content})

            tool_results: list[dict[str, Any]] = []
            for use in tool_uses:
                tool = self._tools.get(use.name)
                if tool is None:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": use.id,
                            "content": f"unknown tool: {use.name}",
                            "is_error": True,
                        }
                    )
                    continue
                tool_input = dict(use.input)  # type: ignore[arg-type]
                output = await tool.handler(tool_input)
                steps.append(AgentToolCall(tool=use.name, input=tool_input, output=output))
                if tool.cites_recipes:
                    citations.update(_extract_recipe_ids(output))
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": use.id, "content": json.dumps(output, default=str)}
                )

            messages.append({"role": "user", "content": tool_results})

        # Loop hit its ceiling — give up gracefully.
        return AgentChatResponse(
            reply=(
                "I couldn't reach a confident recommendation within the tool-call budget. Try a more specific question?"
            ),
            citations=sorted(citations),
            steps=steps,
        )


def build_anthropic_client() -> AsyncAnthropic:
    """Shared factory so settings + truststore live in one place."""
    truststore.inject_into_ssl()
    return AsyncAnthropic(api_key=settings.anthropic_api_key)
