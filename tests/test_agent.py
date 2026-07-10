import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

from httpx import AsyncClient

from recipebox.deps import get_anthropic_client
from recipebox.domain.schemas import ReferenceRecipeDetail, ReferenceRecipeHit
from recipebox.main import app

# ---- stub anthropic client ----


@dataclass
class _Block:
    type: str
    text: str = ""
    name: str = ""
    id: str = ""
    input: dict = None  # type: ignore[assignment]


@dataclass
class _Response:
    content: list[_Block]
    stop_reason: str


class _StubStream:
    """Async-context-manager stand-in for client.messages.stream(...).

    text_stream replays each response's text blocks as chunks; get_final_message
    returns the whole scripted response (for the stop_reason / tool_use decision).
    """

    def __init__(self, response: _Response) -> None:
        self._response = response

    async def __aenter__(self) -> "_StubStream":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    @property
    def text_stream(self) -> AsyncIterator[str]:
        return self._iter_text()

    async def _iter_text(self) -> AsyncIterator[str]:
        for block in self._response.content:
            if block.type == "text" and block.text:
                yield block.text

    async def get_final_message(self) -> _Response:
        return self._response


class StubAnthropic:
    """Replays a scripted list of `_Response` objects in order.

    Each call to `messages.create()` (or `messages.stream()`) pops the next response.
    Tests script the expected agent trajectory: tool use → tool use → end_turn.
    """

    def __init__(self, scripted: list[_Response]) -> None:
        self._scripted = list(scripted)
        self.calls: list[dict] = []
        self.messages = self  # client.messages.create(...) / .stream(...) route here

    async def create(self, **kwargs) -> _Response:
        self.calls.append(kwargs)
        return self._scripted.pop(0)

    def stream(self, **kwargs) -> _StubStream:
        self.calls.append(kwargs)
        return _StubStream(self._scripted.pop(0))


# ---- helpers ----


async def register_and_login(client: AsyncClient, email: str = "user@example.com") -> str:
    await client.post("/auth/register", json={"email": email, "password": "secret"})
    response = await client.post("/auth/login", data={"username": email, "password": "secret"})
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _hit(id: int, title: str) -> ReferenceRecipeHit:
    return ReferenceRecipeHit(
        id=id,
        title=title,
        description=None,
        url=f"https://example.com/{id}",
        source_site="testsite",
        cuisine=None,
        category=None,
        image_url=None,
        score=0.9,
    )


def _detail(id: int, title: str) -> ReferenceRecipeDetail:
    return ReferenceRecipeDetail(
        id=id,
        title=title,
        description=None,
        ingredients=["flour", "water"],
        instructions=["mix", "bake"],
        url=f"https://example.com/{id}",
        source_site="testsite",
        cuisine=None,
        category=None,
        servings="4",
        image_url=None,
    )


def _override_agent(stub: StubAnthropic, client: AsyncClient) -> None:
    app.dependency_overrides[get_anthropic_client] = lambda: stub
    # seed the reference repo with hits + details so tools return useful data
    client.reference_repo.add(_hit(1, "Pasta"), [1.0, 0.0])  # type: ignore[attr-defined]
    client.reference_repo.add(_hit(2, "Salad"), [0.0, 1.0])  # type: ignore[attr-defined]
    client.reference_repo.add_detail(_detail(1, "Pasta"))  # type: ignore[attr-defined]
    client.embedder.fixed["dinner"] = [1.0, 0.0]  # type: ignore[attr-defined]


# ---- tests ----


class TestAgentChat:
    async def test_returns_text_only_when_no_tool_use(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        stub = StubAnthropic(
            [
                _Response(content=[_Block(type="text", text="Hi there!")], stop_reason="end_turn"),
            ]
        )
        _override_agent(stub, client)
        response = await client.post(
            "/agent/chat",
            json={"message": "hello"},
            headers=auth(token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == "Hi there!"
        assert data["citations"] == []
        assert data["steps"] == []

    async def test_executes_tool_then_returns_final_reply(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        stub = StubAnthropic(
            [
                _Response(
                    content=[_Block(type="tool_use", name="search_recipes", id="t1", input={"query": "dinner"})],
                    stop_reason="tool_use",
                ),
                _Response(content=[_Block(type="text", text="Try recipe #1.")], stop_reason="end_turn"),
            ]
        )
        _override_agent(stub, client)
        response = await client.post(
            "/agent/chat",
            json={"message": "what's for dinner"},
            headers=auth(token),
        )
        data = response.json()
        assert data["reply"] == "Try recipe #1."
        # search_recipes returned id 1 and 2 → both in citations
        assert sorted(data["citations"]) == [1, 2]
        assert len(data["steps"]) == 1
        assert data["steps"][0]["tool"] == "search_recipes"

    async def test_pantry_tool_scoped_to_current_user(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        await client.post(
            "/pantry",
            json={"name": "flour", "quantity": 500, "unit": "grams"},
            headers=auth(token),
        )
        stub = StubAnthropic(
            [
                _Response(
                    content=[_Block(type="tool_use", name="get_pantry", id="t1", input={})],
                    stop_reason="tool_use",
                ),
                _Response(content=[_Block(type="text", text="You have flour.")], stop_reason="end_turn"),
            ]
        )
        _override_agent(stub, client)
        response = await client.post(
            "/agent/chat",
            json={"message": "what do I have"},
            headers=auth(token),
        )
        data = response.json()
        assert data["steps"][0]["output"] == [{"name": "flour", "quantity": 500.0, "unit": "grams"}]

    async def test_requires_auth(self, client: AsyncClient) -> None:
        stub = StubAnthropic(
            [
                _Response(content=[_Block(type="text", text="x")], stop_reason="end_turn"),
            ]
        )
        _override_agent(stub, client)
        response = await client.post("/agent/chat", json={"message": "x"})
        assert response.status_code == 401

    async def test_caps_loop_at_max_iterations(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        # Endless tool_use loop — the agent should give up gracefully.
        scripted = [
            _Response(
                content=[_Block(type="tool_use", name="search_recipes", id=f"t{i}", input={"query": "dinner"})],
                stop_reason="tool_use",
            )
            for i in range(20)
        ]
        stub = StubAnthropic(scripted)
        _override_agent(stub, client)
        response = await client.post(
            "/agent/chat",
            json={"message": "loop"},
            headers=auth(token),
        )
        assert response.status_code == 200
        # Hit the cap (MAX_ITERATIONS=10), not the end of the script
        assert len(stub.calls) == 10
        assert "couldn't reach" in response.json()["reply"].lower()

    async def test_stream_emits_step_token_and_done(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        stub = StubAnthropic(
            [
                _Response(
                    content=[_Block(type="tool_use", name="search_recipes", id="t1", input={"query": "dinner"})],
                    stop_reason="tool_use",
                ),
                _Response(content=[_Block(type="text", text="Try recipe #1.")], stop_reason="end_turn"),
            ]
        )
        _override_agent(stub, client)

        events: list[dict] = []
        async with client.stream(
            "POST", "/agent/chat/stream", json={"message": "what's for dinner"}, headers=auth(token)
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line.removeprefix("data: ")))

        # A step event fires before the tool runs, tokens stream the final turn, done comes last.
        assert events[-1]["type"] == "done"
        step = next(e for e in events if e["type"] == "step")
        assert step["tool"] == "search_recipes"
        assert "".join(e["text"] for e in events if e["type"] == "token") == "Try recipe #1."
        done = events[-1]
        assert done["reply"] == "Try recipe #1."
        assert sorted(done["citations"]) == [1, 2]  # search_recipes returned ids 1 and 2
        assert len(done["steps"]) == 1

    async def test_stream_requires_auth(self, client: AsyncClient) -> None:
        stub = StubAnthropic([_Response(content=[_Block(type="text", text="x")], stop_reason="end_turn")])
        _override_agent(stub, client)
        response = await client.post("/agent/chat/stream", json={"message": "x"})
        assert response.status_code == 401
