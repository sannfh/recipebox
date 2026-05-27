import re
import ssl
from collections.abc import Callable
from typing import TypeVar, cast

import httpx
import truststore
from recipe_scrapers import scrape_html

from recipebox.domain.errors import RecipeImportError
from recipebox.domain.schemas import Ingredient, RecipeCreate

# Use Windows Schannel / macOS Keychain instead of bundled OpenSSL
_ssl_ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

T = TypeVar("T")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class RecipeImporter:
    async def extract(self, url: str) -> RecipeCreate:
        html = await self._fetch(url)
        return self._parse(html, url)

    async def _fetch(self, url: str) -> str:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15, verify=_ssl_ctx) as client:
                response = await client.get(url, headers=_HEADERS)
                response.raise_for_status()
                return response.text
        except httpx.HTTPError as exc:
            raise RecipeImportError(f"Could not fetch URL: {exc}") from exc

    def _parse(self, html: str, url: str) -> RecipeCreate:
        try:
            scraper = scrape_html(html, org_url=url)
        except Exception as exc:
            raise RecipeImportError(f"Could not parse recipe from page: {exc}") from exc

        title = self._get(lambda: cast(str | None, scraper.title()), None)
        if not title:
            raise RecipeImportError("Page does not contain a recognizable recipe")

        return RecipeCreate(
            title=title,
            description=self._get(lambda: cast(str, scraper.description()), ""),
            ingredients=[
                Ingredient(name=raw, amount=0, unit="")
                for raw in self._get(lambda: cast(list[str], scraper.ingredients()), [])
            ],
            steps=self._get(lambda: scraper.instructions_list(), []),
            prep_time_minutes=self._get(lambda: cast(int, scraper.prep_time()), 0),
            cook_time_minutes=self._get(lambda: cast(int, scraper.cook_time()), 0),
            servings=self._parse_servings(self._get(lambda: cast(str, scraper.yields()), "1")),
            tags=list(self._get(lambda: cast(list[str], scraper.tags()), [])),  # type: ignore[attr-defined]
            source_url=url,
        )

    def _get(self, fn: Callable[[], T], default: T) -> T:
        try:
            result = fn()
            return result if result is not None else default
        except Exception:
            return default

    def _parse_servings(self, yields_str: str) -> int:
        match = re.search(r"\d+", str(yields_str))
        return int(match.group()) if match else 1
