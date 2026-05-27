"""
Recipe import tests.

Two test classes:
  TestRecipeImporter  — tests the importer class directly (mocks HTTP + scrape_html)
  TestImportEndpoint  — tests the POST /recipes/import route (replaces importer with a fake)

To see real extraction output from a live recipe page, run:
    pytest tests/test_import.py -k real -s -v
Then change REAL_URL below to any recipe URL you want to try.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from recipebox.core.importer import RecipeImporter
from recipebox.deps import get_importer
from recipebox.domain.errors import RecipeImportError
from recipebox.domain.schemas import Ingredient, RecipeCreate
from recipebox.main import app

# ---------------------------------------------------------------------------
# Fake scraped data
# These mirror what recipe_scrapers would return from a real carbonara page.
# Reading these constants tells you what the importer is expected to produce.
# ---------------------------------------------------------------------------

TEST_URL = "https://www.example-recipes.com/carbonara"
FAKE_HTML = "<html><body><!-- recipe site HTML --></body></html>"

SCRAPED_TITLE = "Spaghetti Carbonara"
SCRAPED_DESCRIPTION = "A classic Roman pasta dish with eggs, cheese, and guanciale."
SCRAPED_INGREDIENTS = [
    "200g spaghetti",
    "100g guanciale or pancetta",
    "2 large eggs",
    "50g Pecorino Romano, finely grated",
    "Freshly ground black pepper",
]
SCRAPED_STEPS = [
    "Bring a large pot of salted water to a boil.",
    "Fry guanciale in a pan over medium heat until crispy.",
    "Cook spaghetti until al dente, reserve 1 cup pasta water.",
    "Whisk eggs and cheese together in a bowl.",
    "Remove pasta from heat, add guanciale and egg mixture, toss quickly.",
]
SCRAPED_PREP_MINUTES = 10
SCRAPED_COOK_MINUTES = 20
SCRAPED_YIELDS = "4 servings"
SCRAPED_TAGS = ["Italian", "Pasta", "Quick"]

# Change this URL to any recipe page you want to inspect.
# Sites that work well: bbcgoodfood.com, simplyrecipes.com, seriouseats.com
# Sites that block scrapers: allrecipes.com, nytcooking.com, foodnetwork.com
REAL_URL = "https://www.americastestkitchen.com/recipes/17225-sheet-pan-onion-sliders"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_scraper(**overrides: object) -> MagicMock:
    """
    Builds a fake recipe_scrapers scraper populated with realistic carbonara data.
    Pass keyword args to override individual fields for edge-case tests.
    """
    s = MagicMock()
    s.title.return_value = overrides.get("title", SCRAPED_TITLE)
    s.description.return_value = overrides.get("description", SCRAPED_DESCRIPTION)
    s.ingredients.return_value = overrides.get("ingredients", SCRAPED_INGREDIENTS)
    s.instructions_list.return_value = overrides.get("steps", SCRAPED_STEPS)
    s.prep_time.return_value = overrides.get("prep_time", SCRAPED_PREP_MINUTES)
    s.cook_time.return_value = overrides.get("cook_time", SCRAPED_COOK_MINUTES)
    s.yields.return_value = overrides.get("yields", SCRAPED_YIELDS)
    s.tags.return_value = overrides.get("tags", SCRAPED_TAGS)
    return s


def build_mock_http_client(html: str = FAKE_HTML) -> tuple[MagicMock, MagicMock]:
    """Returns (mock_client_class, mock_response) with html baked in."""
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)

    mock_class = MagicMock()
    mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_http)
    mock_class.return_value.__aexit__ = AsyncMock(return_value=False)

    return mock_class, mock_response


async def register_and_login(client: AsyncClient) -> str:
    await client.post("/auth/register", json={"email": "chef@example.com", "password": "secret"})
    r = await client.post("/auth/login", data={"username": "chef@example.com", "password": "secret"})
    return r.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Unit tests — importer class in isolation
# ---------------------------------------------------------------------------


class TestRecipeImporter:
    """Tests the RecipeImporter class directly, mocking the network and scraper."""

    async def test_extracts_title_and_description(self) -> None:
        scraper = make_mock_scraper()
        mock_class, _ = build_mock_http_client()

        with (
            patch("recipebox.core.importer.httpx.AsyncClient", mock_class),
            patch("recipebox.core.importer.scrape_html", return_value=scraper),
        ):
            recipe = await RecipeImporter().extract(TEST_URL)

        assert recipe.title == SCRAPED_TITLE
        assert recipe.description == SCRAPED_DESCRIPTION

    async def test_stores_ingredients_as_raw_strings(self) -> None:
        # Ingredient parsing (e.g. "200g spaghetti" → name/amount/unit) is hard without NLP.
        # We store the full string in `name` and leave amount/unit as defaults.
        scraper = make_mock_scraper()
        mock_class, _ = build_mock_http_client()

        with (
            patch("recipebox.core.importer.httpx.AsyncClient", mock_class),
            patch("recipebox.core.importer.scrape_html", return_value=scraper),
        ):
            recipe = await RecipeImporter().extract(TEST_URL)

        assert len(recipe.ingredients) == len(SCRAPED_INGREDIENTS)
        assert recipe.ingredients[0] == Ingredient(name="200g spaghetti", amount=0, unit="")

    async def test_parses_servings_from_yields_string(self) -> None:
        # recipe_scrapers returns yields as a string like "4 servings", not an int
        scraper = make_mock_scraper(yields="4 servings")
        mock_class, _ = build_mock_http_client()

        with (
            patch("recipebox.core.importer.httpx.AsyncClient", mock_class),
            patch("recipebox.core.importer.scrape_html", return_value=scraper),
        ):
            recipe = await RecipeImporter().extract(TEST_URL)

        assert recipe.servings == 4

    async def test_sets_source_url_to_import_url(self) -> None:
        scraper = make_mock_scraper()
        mock_class, _ = build_mock_http_client()

        with (
            patch("recipebox.core.importer.httpx.AsyncClient", mock_class),
            patch("recipebox.core.importer.scrape_html", return_value=scraper),
        ):
            recipe = await RecipeImporter().extract(TEST_URL)

        assert recipe.source_url == TEST_URL

    async def test_raises_import_error_on_network_failure(self) -> None:
        import httpx as _httpx

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=_httpx.ConnectError("Connection refused"))
        mock_class = MagicMock()
        mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_class.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("recipebox.core.importer.httpx.AsyncClient", mock_class),
            pytest.raises(RecipeImportError, match="Could not fetch URL"),
        ):
            await RecipeImporter().extract(TEST_URL)

    async def test_raises_import_error_when_scraper_fails(self) -> None:
        mock_class, _ = build_mock_http_client()

        with (
            patch("recipebox.core.importer.httpx.AsyncClient", mock_class),
            patch("recipebox.core.importer.scrape_html", side_effect=Exception("No recipe schema found")),
            pytest.raises(RecipeImportError, match="Could not parse recipe"),
        ):
            await RecipeImporter().extract(TEST_URL)

    async def test_defaults_missing_fields_instead_of_crashing(self) -> None:
        # Some sites don't provide prep_time, cook_time, tags, etc.
        # recipe_scrapers raises an exception for missing fields; the importer catches them.
        scraper = make_mock_scraper()
        scraper.prep_time.side_effect = Exception("not provided")
        scraper.cook_time.side_effect = Exception("not provided")
        scraper.tags.side_effect = Exception("not provided")
        mock_class, _ = build_mock_http_client()

        with (
            patch("recipebox.core.importer.httpx.AsyncClient", mock_class),
            patch("recipebox.core.importer.scrape_html", return_value=scraper),
        ):
            recipe = await RecipeImporter().extract(TEST_URL)

        assert recipe.prep_time_minutes == 0
        assert recipe.cook_time_minutes == 0
        assert recipe.tags == []


# ---------------------------------------------------------------------------
# Endpoint tests — POST /recipes/import
# ---------------------------------------------------------------------------


class FakeImporter:
    """Stand-in for RecipeImporter — returns a known Carbonara recipe instantly."""

    async def extract(self, url: str) -> RecipeCreate:
        return RecipeCreate(
            title=SCRAPED_TITLE,
            description=SCRAPED_DESCRIPTION,
            ingredients=[Ingredient(name=raw, amount=0, unit="") for raw in SCRAPED_INGREDIENTS],
            steps=SCRAPED_STEPS,
            prep_time_minutes=SCRAPED_PREP_MINUTES,
            cook_time_minutes=SCRAPED_COOK_MINUTES,
            servings=4,
            tags=SCRAPED_TAGS,
            source_url=url,
        )


class TestImportEndpoint:
    """Tests the POST /recipes/import route.

    Uses FakeImporter via dependency injection so these tests don't touch the
    network or recipe-scrapers — that's covered in TestRecipeImporter above.
    """

    @pytest.fixture(autouse=True)
    def use_fake_importer(self) -> None:
        app.dependency_overrides[get_importer] = lambda: FakeImporter()

    async def test_returns_201_with_recipe_data(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.post("/recipes/import", json={"url": TEST_URL}, headers=auth(token))

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == SCRAPED_TITLE
        assert data["description"] == SCRAPED_DESCRIPTION
        assert len(data["ingredients"]) == len(SCRAPED_INGREDIENTS)
        assert data["steps"] == SCRAPED_STEPS
        assert data["servings"] == 4
        assert data["source_url"] == TEST_URL

    async def test_sets_owner_to_current_user(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.post("/recipes/import", json={"url": TEST_URL}, headers=auth(token))

        data = response.json()
        assert "owner_id" in data
        assert isinstance(data["owner_id"], int)

    async def test_normalizes_tags_to_lowercase(self, client: AsyncClient) -> None:
        # FakeImporter returns ["Italian", "Pasta", "Quick"] — schema validator lowercases them
        token = await register_and_login(client)
        response = await client.post("/recipes/import", json={"url": TEST_URL}, headers=auth(token))

        tags = response.json()["tags"]
        assert "italian" in tags
        assert "pasta" in tags

    async def test_requires_auth(self, client: AsyncClient) -> None:
        response = await client.post("/recipes/import", json={"url": TEST_URL})
        assert response.status_code == 401

    async def test_rejects_invalid_url_format(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        response = await client.post("/recipes/import", json={"url": "not-a-url"}, headers=auth(token))
        assert response.status_code == 422

    async def test_import_error_returns_422_with_detail(self, client: AsyncClient) -> None:
        class BrokenImporter:
            async def extract(self, url: str) -> RecipeCreate:
                raise RecipeImportError("No recipe schema found on page")

        app.dependency_overrides[get_importer] = lambda: BrokenImporter()

        token = await register_and_login(client)
        response = await client.post("/recipes/import", json={"url": TEST_URL}, headers=auth(token))

        assert response.status_code == 422
        assert "No recipe schema found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Real URL test — skipped by default, run manually to see actual extraction
# ---------------------------------------------------------------------------


@pytest.mark.real
async def test_real_url_scraping() -> None:
    """
    Scrapes REAL_URL (defined at the top of this file) and prints what the importer extracts.

    Run with:
        pytest tests/test_import.py -m real -s -v

    The -s flag shows the print output. Change REAL_URL to any recipe page you want to try.
    No mocking — this hits the actual website.
    """
    importer = RecipeImporter()
    recipe = await importer.extract(REAL_URL)

    print(f"\n{'=' * 55}")
    print(f"URL:         {REAL_URL}")
    print(f"TITLE:       {recipe.title}")
    print(f"DESCRIPTION: {recipe.description[:80]}{'...' if len(recipe.description) > 80 else ''}")
    print(f"SERVINGS:    {recipe.servings}")
    print(f"PREP:        {recipe.prep_time_minutes} min  |  COOK: {recipe.cook_time_minutes} min")
    print(f"TAGS:        {recipe.tags}")
    print(f"\nINGREDIENTS ({len(recipe.ingredients)}):")
    for ing in recipe.ingredients:
        print(f"  • {ing.name}")
    print(f"\nSTEPS ({len(recipe.steps)}):")
    for n, step in enumerate(recipe.steps, 1):
        truncated = step[:80] + "..." if len(step) > 80 else step
        print(f"  {n}. {truncated}")
    print(f"{'=' * 55}\n")

    assert recipe.title, "Title should not be empty"
    assert len(recipe.ingredients) > 0, "Should have extracted at least one ingredient"
    assert len(recipe.steps) > 0, "Should have extracted at least one step"
