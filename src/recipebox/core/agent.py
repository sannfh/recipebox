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
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

import truststore
from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, ToolParam, ToolResultBlockParam, ToolUseBlock

from recipebox.config import settings
from recipebox.domain.schemas import AgentChatResponse, AgentMessage, AgentToolCall

# Max tool-use rounds before we abort. Real agents go 5-15 calls.
MAX_ITERATIONS = 10
MAX_TOKENS = 4096

# Returned by both chat() and chat_stream() when the loop exhausts its budget.
BUDGET_EXCEEDED_REPLY = (
    "I couldn't reach a confident recommendation within the tool-call budget. Try a more specific question?"
)

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


def _extract_recipe_ids(output: list[dict[str, Any]] | dict[str, Any]) -> list[int]:
    """Pull recipe ids out of a tool result so we can build the citations list."""
    if isinstance(output, list):
        result: list[int] = []
        for item in output:
            value = item.get("id")
            if isinstance(value, int):
                result.append(value)
        return result
    value = output.get("id")
    if isinstance(value, int):
        return [value]
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
        messages: list[MessageParam] = [
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
                tools=cast(list[ToolParam], self._tool_schemas),
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
                step, result, cited = await self._run_one_tool(use)
                if step is not None:
                    steps.append(step)
                citations.update(cited)
                tool_results.append(result)

            messages.append({"role": "user", "content": cast(list[ToolResultBlockParam], tool_results)})

        # Loop hit its ceiling — give up gracefully.
        return AgentChatResponse(reply=BUDGET_EXCEEDED_REPLY, citations=sorted(citations), steps=steps)

    async def _run_one_tool(self, use: ToolUseBlock) -> tuple[AgentToolCall | None, dict[str, Any], list[int]]:
        """Execute one tool_use block. Returns (step, tool_result, cited_ids). Shared by chat()
        and chat_stream() so the two never drift. step is None for an unknown tool, which still
        returns an is_error result Claude can see and recover from."""
        tool = self._tools.get(use.name)
        if tool is None:
            error = {
                "type": "tool_result",
                "tool_use_id": use.id,
                "content": f"unknown tool: {use.name}",
                "is_error": True,
            }
            return None, error, []
        tool_input = dict(use.input)  # type: ignore[arg-type]
        output = await tool.handler(tool_input)
        step = AgentToolCall(tool=use.name, input=tool_input, output=output)
        cited = _extract_recipe_ids(output) if tool.cites_recipes else []
        result = {"type": "tool_result", "tool_use_id": use.id, "content": json.dumps(output, default=str)}
        return step, result, cited

    @staticmethod
    def _done_event(reply: str, citations: set[int], steps: list[AgentToolCall]) -> dict[str, Any]:
        """The terminal streaming event. steps are dumped to JSON-safe dicts so the payload
        matches what chat()'s AgentChatResponse would serialize."""
        return {
            "type": "done",
            "reply": reply,
            "citations": sorted(citations),
            "steps": [s.model_dump(mode="json") for s in steps],
        }

    async def chat_stream(self, user_message: str, history: list[AgentMessage]) -> AsyncIterator[dict[str, Any]]:
        """Streaming sibling of chat() for the UI. Yields events to render live:

            {"type": "step",  "tool": str, "input": dict}   — a tool is about to run
            {"type": "token", "text": str}                  — a chunk of assistant text
            {"type": "done",  "reply": str, "citations": list[int], "steps": list[dict]}

        token events are live and may include brief intermediate narration; done.reply is the
        authoritative final answer — the same value chat() returns. Exactly one done event is
        emitted, always last.
        """
        messages: list[MessageParam] = [
            *({"role": h.role, "content": h.content} for h in history),
            {"role": "user", "content": user_message},
        ]
        steps: list[AgentToolCall] = []
        citations: set[int] = set()

        for _ in range(MAX_ITERATIONS):
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=cast(list[ToolParam], self._tool_schemas),
                messages=messages,
                cache_control={"type": "ephemeral"},
            ) as stream:
                async for text in stream.text_stream:
                    yield {"type": "token", "text": text}
                final = await stream.get_final_message()

            tool_uses = [b for b in final.content if b.type == "tool_use"]
            if final.stop_reason == "end_turn" or not tool_uses:
                # Done: either a natural finish, or (defensively) a non-end_turn stop with no tools.
                reply = next((b.text for b in final.content if b.type == "text"), "")
                yield self._done_event(reply, citations, steps)
                return

            messages.append({"role": "assistant", "content": final.content})
            tool_results: list[dict[str, Any]] = []
            for use in tool_uses:
                yield {"type": "step", "tool": use.name, "input": dict(use.input)}  # type: ignore[arg-type]
                step, result, cited = await self._run_one_tool(use)
                if step is not None:
                    steps.append(step)
                citations.update(cited)
                tool_results.append(result)
            messages.append({"role": "user", "content": cast(list[ToolResultBlockParam], tool_results)})

        yield self._done_event(BUDGET_EXCEEDED_REPLY, citations, steps)


def build_anthropic_client() -> AsyncAnthropic:
    """Shared factory so settings + truststore live in one place."""
    truststore.inject_into_ssl()
    return AsyncAnthropic(api_key=settings.anthropic_api_key)
