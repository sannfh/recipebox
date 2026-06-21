from httpx import AsyncClient

# --- helpers ---

ITEM_BODY = {"name": "flour", "quantity": 500, "unit": "grams"}


async def register_and_login(client: AsyncClient, email: str = "user@example.com") -> str:
    await client.post("/auth/register", json={"email": email, "password": "secret"})
    response = await client.post("/auth/login", data={"username": email, "password": "secret"})
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- POST /pantry ---


class TestAddPantryItem:
    async def test_returns_201(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.post("/pantry", json=ITEM_BODY, headers=auth(token))
        assert response.status_code == 201

    async def test_returns_item_with_id(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.post("/pantry", json=ITEM_BODY, headers=auth(token))
        data = response.json()
        assert "id" in data
        assert data["name"] == "flour"
        assert data["quantity"] == 500
        assert data["unit"] == "grams"

    async def test_normalizes_name_to_lowercase(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.post("/pantry", json={"name": "  FLOUR  ", "quantity": 1}, headers=auth(token))
        assert response.json()["name"] == "flour"

    async def test_sets_user_id_to_current_user(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        me = await client.get("/auth/me", headers=auth(token))
        item = await client.post("/pantry", json=ITEM_BODY, headers=auth(token))
        assert item.json()["user_id"] == me.json()["id"]

    async def test_requires_auth(self, client: AsyncClient) -> None:
        response = await client.post("/pantry", json=ITEM_BODY)
        assert response.status_code == 401

    async def test_invalid_body_returns_422(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.post("/pantry", json={"name": "x"}, headers=auth(token))
        assert response.status_code == 422

    async def test_negative_quantity_returns_422(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.post(
            "/pantry", json={"name": "flour", "quantity": -1, "unit": "grams"}, headers=auth(token)
        )
        assert response.status_code == 422

    async def test_duplicate_name_returns_409(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        await client.post("/pantry", json=ITEM_BODY, headers=auth(token))
        response = await client.post("/pantry", json=ITEM_BODY, headers=auth(token))
        assert response.status_code == 409

    async def test_same_name_different_user_allowed(self, client: AsyncClient) -> None:
        token_a = await register_and_login(client, "a@example.com")
        token_b = await register_and_login(client, "b@example.com")
        a = await client.post("/pantry", json=ITEM_BODY, headers=auth(token_a))
        b = await client.post("/pantry", json=ITEM_BODY, headers=auth(token_b))
        assert a.status_code == 201
        assert b.status_code == 201


# --- GET /pantry ---


class TestListPantry:
    async def test_empty_pantry_returns_empty_list(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.get("/pantry", headers=auth(token))
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_only_current_users_items(self, client: AsyncClient) -> None:
        token_a = await register_and_login(client, "a@example.com")
        token_b = await register_and_login(client, "b@example.com")
        await client.post("/pantry", json=ITEM_BODY, headers=auth(token_a))
        await client.post("/pantry", json={"name": "sugar", "quantity": 100}, headers=auth(token_b))

        response_a = await client.get("/pantry", headers=auth(token_a))
        assert [i["name"] for i in response_a.json()] == ["flour"]
        response_b = await client.get("/pantry", headers=auth(token_b))
        assert [i["name"] for i in response_b.json()] == ["sugar"]

    async def test_requires_auth(self, client: AsyncClient) -> None:
        response = await client.get("/pantry")
        assert response.status_code == 401


# --- PATCH /pantry/{id} ---


class TestUpdatePantryItem:
    async def test_returns_updated_item(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        created = await client.post("/pantry", json=ITEM_BODY, headers=auth(token))
        item_id = created.json()["id"]
        response = await client.patch(f"/pantry/{item_id}", json={"quantity": 200}, headers=auth(token))
        assert response.status_code == 200
        assert response.json()["quantity"] == 200

    async def test_partial_update_preserves_other_fields(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        created = await client.post("/pantry", json=ITEM_BODY, headers=auth(token))
        item_id = created.json()["id"]
        response = await client.patch(f"/pantry/{item_id}", json={"quantity": 200}, headers=auth(token))
        assert response.json()["unit"] == "grams"
        assert response.json()["name"] == "flour"

    async def test_requires_auth(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        created = await client.post("/pantry", json=ITEM_BODY, headers=auth(token))
        item_id = created.json()["id"]
        response = await client.patch(f"/pantry/{item_id}", json={"quantity": 1})
        assert response.status_code == 401

    async def test_non_owner_returns_403(self, client: AsyncClient) -> None:
        owner_token = await register_and_login(client, "owner@example.com")
        other_token = await register_and_login(client, "other@example.com")
        created = await client.post("/pantry", json=ITEM_BODY, headers=auth(owner_token))
        item_id = created.json()["id"]
        response = await client.patch(f"/pantry/{item_id}", json={"quantity": 1}, headers=auth(other_token))
        assert response.status_code == 403

    async def test_missing_item_returns_404(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.patch("/pantry/999", json={"quantity": 1}, headers=auth(token))
        assert response.status_code == 404


# --- DELETE /pantry/{id} ---


class TestDeletePantryItem:
    async def test_returns_204(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        created = await client.post("/pantry", json=ITEM_BODY, headers=auth(token))
        item_id = created.json()["id"]
        response = await client.delete(f"/pantry/{item_id}", headers=auth(token))
        assert response.status_code == 204

    async def test_item_no_longer_listed_after_delete(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        created = await client.post("/pantry", json=ITEM_BODY, headers=auth(token))
        item_id = created.json()["id"]
        await client.delete(f"/pantry/{item_id}", headers=auth(token))
        listed = await client.get("/pantry", headers=auth(token))
        assert listed.json() == []

    async def test_requires_auth(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        created = await client.post("/pantry", json=ITEM_BODY, headers=auth(token))
        item_id = created.json()["id"]
        response = await client.delete(f"/pantry/{item_id}")
        assert response.status_code == 401

    async def test_non_owner_returns_403(self, client: AsyncClient) -> None:
        owner_token = await register_and_login(client, "owner@example.com")
        other_token = await register_and_login(client, "other@example.com")
        created = await client.post("/pantry", json=ITEM_BODY, headers=auth(owner_token))
        item_id = created.json()["id"]
        response = await client.delete(f"/pantry/{item_id}", headers=auth(other_token))
        assert response.status_code == 403

    async def test_missing_item_returns_404(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.delete("/pantry/999", headers=auth(token))
        assert response.status_code == 404
