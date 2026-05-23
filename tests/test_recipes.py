from httpx import AsyncClient

# --- helpers ---

RECIPE_BODY = {
    "title": "Pasta",
    "description": "Simple pasta",
    "ingredients": [{"name": "pasta", "amount": 200, "unit": "grams"}],
    "steps": ["Boil water", "Cook pasta"],
    "servings": 2,
}


async def register_and_login(client: AsyncClient, email: str = "user@example.com") -> str:
    await client.post("/auth/register", json={"email": email, "password": "secret"})
    response = await client.post("/auth/login", data={"username": email, "password": "secret"})
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- POST /recipes ---


class TestCreateRecipe:
    async def test_returns_201(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.post("/recipes", json=RECIPE_BODY, headers=auth(token))
        assert response.status_code == 201

    async def test_returns_recipe_with_id(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.post("/recipes", json=RECIPE_BODY, headers=auth(token))
        data = response.json()
        assert "id" in data
        assert data["title"] == "Pasta"

    async def test_sets_owner_to_current_user(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        me = await client.get("/auth/me", headers=auth(token))
        recipe = await client.post("/recipes", json=RECIPE_BODY, headers=auth(token))
        assert recipe.json()["owner_id"] == me.json()["id"]

    async def test_requires_auth(self, client: AsyncClient) -> None:
        response = await client.post("/recipes", json=RECIPE_BODY)
        assert response.status_code == 401

    async def test_invalid_body_returns_422(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.post("/recipes", json={"title": "only title"}, headers=auth(token))
        assert response.status_code == 422


# --- GET /recipes/{id} ---


class TestGetRecipe:
    async def test_returns_recipe(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        created = await client.post("/recipes", json=RECIPE_BODY, headers=auth(token))
        recipe_id = created.json()["id"]
        response = await client.get(f"/recipes/{recipe_id}")
        assert response.status_code == 200
        assert response.json()["id"] == recipe_id

    async def test_no_auth_required(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        created = await client.post("/recipes", json=RECIPE_BODY, headers=auth(token))
        recipe_id = created.json()["id"]
        response = await client.get(f"/recipes/{recipe_id}")
        assert response.status_code == 200

    async def test_missing_id_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/recipes/999")
        assert response.status_code == 404


# --- GET /recipes ---


class TestListRecipes:
    async def test_returns_page(self, client: AsyncClient) -> None:
        response = await client.get("/recipes")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "skip" in data
        assert "limit" in data

    async def test_empty_store_returns_empty_items(self, client: AsyncClient) -> None:
        response = await client.get("/recipes")
        assert response.json()["total"] == 0
        assert response.json()["items"] == []

    async def test_pagination_limit(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        for _ in range(5):
            await client.post("/recipes", json=RECIPE_BODY, headers=auth(token))
        response = await client.get("/recipes?skip=0&limit=2")
        assert len(response.json()["items"]) == 2
        assert response.json()["total"] == 5

    async def test_pagination_skip(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        for _ in range(3):
            await client.post("/recipes", json=RECIPE_BODY, headers=auth(token))
        response = await client.get("/recipes?skip=2&limit=10")
        assert len(response.json()["items"]) == 1


# --- PATCH /recipes/{id} ---


class TestUpdateRecipe:
    async def test_returns_updated_recipe(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        created = await client.post("/recipes", json=RECIPE_BODY, headers=auth(token))
        recipe_id = created.json()["id"]
        response = await client.patch(f"/recipes/{recipe_id}", json={"title": "New Title"}, headers=auth(token))
        assert response.status_code == 200
        assert response.json()["title"] == "New Title"

    async def test_partial_update_preserves_other_fields(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        created = await client.post("/recipes", json=RECIPE_BODY, headers=auth(token))
        recipe_id = created.json()["id"]
        response = await client.patch(f"/recipes/{recipe_id}", json={"title": "New"}, headers=auth(token))
        assert response.json()["servings"] == RECIPE_BODY["servings"]

    async def test_requires_auth(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        created = await client.post("/recipes", json=RECIPE_BODY, headers=auth(token))
        recipe_id = created.json()["id"]
        response = await client.patch(f"/recipes/{recipe_id}", json={"title": "X"})
        assert response.status_code == 401

    async def test_non_owner_returns_403(self, client: AsyncClient) -> None:
        owner_token = await register_and_login(client, email="owner@example.com")
        other_token = await register_and_login(client, email="other@example.com")
        created = await client.post("/recipes", json=RECIPE_BODY, headers=auth(owner_token))
        recipe_id = created.json()["id"]
        response = await client.patch(f"/recipes/{recipe_id}", json={"title": "X"}, headers=auth(other_token))
        assert response.status_code == 403

    async def test_missing_recipe_returns_404(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.patch("/recipes/999", json={"title": "X"}, headers=auth(token))
        assert response.status_code == 404


# --- DELETE /recipes/{id} ---


class TestDeleteRecipe:
    async def test_returns_204(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        created = await client.post("/recipes", json=RECIPE_BODY, headers=auth(token))
        recipe_id = created.json()["id"]
        response = await client.delete(f"/recipes/{recipe_id}", headers=auth(token))
        assert response.status_code == 204

    async def test_recipe_no_longer_exists_after_delete(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        created = await client.post("/recipes", json=RECIPE_BODY, headers=auth(token))
        recipe_id = created.json()["id"]
        await client.delete(f"/recipes/{recipe_id}", headers=auth(token))
        response = await client.get(f"/recipes/{recipe_id}")
        assert response.status_code == 404

    async def test_requires_auth(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        created = await client.post("/recipes", json=RECIPE_BODY, headers=auth(token))
        recipe_id = created.json()["id"]
        response = await client.delete(f"/recipes/{recipe_id}")
        assert response.status_code == 401

    async def test_non_owner_returns_403(self, client: AsyncClient) -> None:
        owner_token = await register_and_login(client, email="owner@example.com")
        other_token = await register_and_login(client, email="other@example.com")
        created = await client.post("/recipes", json=RECIPE_BODY, headers=auth(owner_token))
        recipe_id = created.json()["id"]
        response = await client.delete(f"/recipes/{recipe_id}", headers=auth(other_token))
        assert response.status_code == 403

    async def test_missing_recipe_returns_404(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.delete("/recipes/999", headers=auth(token))
        assert response.status_code == 404
