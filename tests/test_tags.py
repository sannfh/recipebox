from httpx import AsyncClient

RECIPE_BODY = {
    "title": "Pasta",
    "description": "Simple pasta",
    "ingredients": [{"name": "pasta", "amount": 200, "unit": "grams"}],
    "steps": ["Boil water", "Cook pasta"],
    "servings": 2,
}


async def register_and_login(client: AsyncClient) -> str:
    await client.post("/auth/register", json={"email": "user@example.com", "password": "secret"})
    response = await client.post("/auth/login", data={"username": "user@example.com", "password": "secret"})
    return response.json()["access_token"]


class TestListTags:
    async def test_returns_empty_list_when_no_recipes(self, client: AsyncClient) -> None:
        response = await client.get("/tags")
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_tags_with_counts(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}
        await client.post("/recipes", json={**RECIPE_BODY, "tags": ["italian", "pasta"]}, headers=headers)
        await client.post("/recipes", json={**RECIPE_BODY, "tags": ["italian", "quick"]}, headers=headers)

        response = await client.get("/tags")
        tags = {item["tag"]: item["count"] for item in response.json()}

        assert tags["italian"] == 2
        assert tags["pasta"] == 1
        assert tags["quick"] == 1

    async def test_sorted_by_most_popular_first(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}
        await client.post("/recipes", json={**RECIPE_BODY, "tags": ["rare"]}, headers=headers)
        await client.post("/recipes", json={**RECIPE_BODY, "tags": ["popular"]}, headers=headers)
        await client.post("/recipes", json={**RECIPE_BODY, "tags": ["popular"]}, headers=headers)

        response = await client.get("/tags")
        items = response.json()

        assert items[0]["tag"] == "popular"
        assert items[0]["count"] == 2

    async def test_no_auth_required(self, client: AsyncClient) -> None:
        response = await client.get("/tags")
        assert response.status_code == 200
