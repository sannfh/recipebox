from httpx import AsyncClient

from recipebox.domain.schemas import ReferenceRecipeHit


def _hit(id: int, title: str, **kwargs) -> ReferenceRecipeHit:
    defaults = {
        "description": None,
        "url": f"https://example.com/{id}",
        "source_site": None,
        "cuisine": None,
        "category": None,
        "image_url": None,
        "score": 0.0,
    }
    defaults.update(kwargs)
    return ReferenceRecipeHit(id=id, title=title, **defaults)  # type: ignore[arg-type]


def _seed(client: AsyncClient) -> None:
    # Three orthogonal "topics" — vectors along three axes so cosine ranking is unambiguous.
    client.reference_repo.add(_hit(1, "Lasagna Bolognese"), [1.0, 0.0, 0.0])  # type: ignore[attr-defined]
    client.reference_repo.add(_hit(2, "Beef Tacos"), [0.0, 1.0, 0.0])  # type: ignore[attr-defined]
    client.reference_repo.add(_hit(3, "Apple Pie"), [0.0, 0.0, 1.0])  # type: ignore[attr-defined]


class TestRecipeSearch:
    async def test_returns_top_match(self, client: AsyncClient) -> None:
        _seed(client)
        client.embedder.fixed["italian comfort food"] = [1.0, 0.0, 0.0]  # type: ignore[attr-defined]
        response = await client.get("/recipes/search?q=italian comfort food&top_k=1")
        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        assert results[0]["title"] == "Lasagna Bolognese"
        assert results[0]["score"] == 1.0  # exact axis match

    async def test_top_k_caps_results(self, client: AsyncClient) -> None:
        _seed(client)
        client.embedder.fixed["food"] = [1.0, 1.0, 1.0]  # type: ignore[attr-defined]
        response = await client.get("/recipes/search?q=food&top_k=2")
        assert len(response.json()) == 2

    async def test_results_ordered_by_score_desc(self, client: AsyncClient) -> None:
        _seed(client)
        # Query closer to taco axis than lasagna axis
        client.embedder.fixed["mexican"] = [0.1, 0.9, 0.0]  # type: ignore[attr-defined]
        response = await client.get("/recipes/search?q=mexican&top_k=3")
        results = response.json()
        assert [r["title"] for r in results[:2]] == ["Beef Tacos", "Lasagna Bolognese"]
        # Scores monotonically decreasing
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    async def test_empty_corpus_returns_empty(self, client: AsyncClient) -> None:
        client.embedder.fixed["anything"] = [1.0, 0.0, 0.0]  # type: ignore[attr-defined]
        response = await client.get("/recipes/search?q=anything&top_k=5")
        assert response.status_code == 200
        assert response.json() == []

    async def test_missing_query_returns_422(self, client: AsyncClient) -> None:
        response = await client.get("/recipes/search")
        assert response.status_code == 422

    async def test_no_auth_required(self, client: AsyncClient) -> None:
        _seed(client)
        client.embedder.fixed["x"] = [1.0, 0.0, 0.0]  # type: ignore[attr-defined]
        response = await client.get("/recipes/search?q=x")
        assert response.status_code == 200
