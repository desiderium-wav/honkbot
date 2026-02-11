"""Media Providers — External and Internal Media Fetching

THIS MODULE DEFINES NO COMMANDS.

Responsibilities:
- Fetch media from Tenor and Giphy APIs
- Index server-uploaded media
- Load curated local goose media folders
- Provide a unified media retrieval interface

This module performs no posting actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import random
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

try:
    import aiohttp
except ModuleNotFoundError:  # pragma: no cover - optional dependency for runtime
    aiohttp = None


MediaItem = Dict[str, object]

LOCAL_MEDIA_ROOT = Path("media/goose")
LOCAL_CATEGORIES = {"angry", "smug", "chaos", "honk", "misc"}
HONK_DENSITY_THRESHOLD = 0.65


dataclass
class MediaProvider:
    name: str

    async def initialize(self) -> None:
        return None

    async def search(self, query: str, context: Dict[str, object]) -> Optional[MediaItem]:
        raise NotImplementedError

    async def get_random(self, context: Dict[str, object]) -> Optional[MediaItem]:
        raise NotImplementedError


@dataclass
class LocalMediaProvider(MediaProvider):
    root: Path = LOCAL_MEDIA_ROOT
    _files_by_category: Dict[str, List[Path]] = field(default_factory=dict, init=False)

    async def initialize(self) -> None:
        self._files_by_category = {category: [] for category in LOCAL_CATEGORIES}
        if not self.root.exists():
            return
        for path in self.root.rglob("*"):
            if path.is_file():
                category = self._category_for_path(path)
                self._files_by_category.setdefault(category, []).append(path)

    async def search(self, query: str, context: Dict[str, object]) -> Optional[MediaItem]:
        keywords = _extract_keywords(context, query=query)
        category = self._select_category(keywords, context)
        path = self._choose_path(category, keywords)
        if not path:
            return None
        return _make_item("file", str(path), "local", tags=self._tags_for_path(path))

    async def get_random(self, context: Dict[str, object]) -> Optional[MediaItem]:
        keywords = _extract_keywords(context)
        category = self._select_category(keywords, context)
        path = self._choose_path(category, keywords)
        if not path:
            return None
        return _make_item("file", str(path), "local", tags=self._tags_for_path(path))

    def has_keyword_match(self, keywords: Sequence[str]) -> bool:
        if not keywords:
            return False
        lowered = {keyword.lower() for keyword in keywords}
        categories = {category for category, paths in self._files_by_category.items() if paths}
        return bool(categories.intersection(lowered))

    def _category_for_path(self, path: Path) -> str:
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            return "misc"
        parts = relative.parts
        if len(parts) <= 1:
            return "misc"
        candidate = parts[0].lower()
        return candidate if candidate in LOCAL_CATEGORIES else "misc"

    def _select_category(self, keywords: Sequence[str], context: Dict[str, object]) -> str:
        preferred = [value.lower() for value in context.get("preferred_categories", []) if isinstance(value, str)]
        if preferred:
            for category in preferred:
                if self._files_by_category.get(category):
                    return category

        for keyword in keywords:
            key = keyword.lower()
            if key in self._files_by_category and self._files_by_category[key]:
                return key

        categories = [category for category, paths in self._files_by_category.items() if paths]
        return random.choice(categories) if categories else "misc"

    def _choose_path(self, category: str, keywords: Sequence[str]) -> Optional[Path]:
        paths = list(self._files_by_category.get(category, []))
        if not paths:
            paths = [path for group in self._files_by_category.values() for path in group]
        if not paths:
            return None
        random.shuffle(paths)
        lowered_keywords = {keyword.lower() for keyword in keywords}
        for path in paths:
            tags = {tag.lower() for tag in self._tags_for_path(path)}
            if lowered_keywords.intersection(tags):
                return path
        return random.choice(paths)

    def _tags_for_path(self, path: Path) -> List[str]:
        tags = [self._category_for_path(path)]
        stem = path.stem.replace("_", " ").replace("-", " ")
        tags.extend(token for token in stem.split() if token)
        return sorted(set(tags))


@dataclass
class ServerMediaProvider(MediaProvider):
    _index: Dict[int, Dict[str, List[str]]] = field(default_factory=dict, init=False)

    async def search(self, query: str, context: Dict[str, object]) -> Optional[MediaItem]:
        return self._pick_from_index(context, query=query)

    async def get_random(self, context: Dict[str, object]) -> Optional[MediaItem]:
        return self._pick_from_index(context)

    def add_media(self, guild_id: int, keywords: Iterable[str], urls: Iterable[str]) -> None:
        if not urls:
            return
        guild_index = self._index.setdefault(guild_id, {})
        for keyword in keywords:
            key = keyword.lower()
            if not key:
                continue
            items = guild_index.setdefault(key, [])
            items.extend(urls)

    def _pick_from_index(self, context: Dict[str, object], *, query: Optional[str] = None) -> Optional[MediaItem]:
        guild_id = context.get("guild_id")
        if guild_id is None:
            return None
        guild_index = self._index.get(int(guild_id))
        if not guild_index:
            return None

        keywords = _extract_keywords(context, query=query)
        for keyword in keywords:
            choices = guild_index.get(keyword.lower())
            if choices:
                return _make_item("url", random.choice(choices), "server", tags=[keyword])

        all_urls = [url for urls in guild_index.values() for url in urls]
        if not all_urls:
            return None
        return _make_item("url", random.choice(all_urls), "server", tags=[]) 


@dataclass
class TenorProvider(MediaProvider):
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("TENOR_API_KEY"))

    async def search(self, query: str, context: Dict[str, object]) -> Optional[MediaItem]:
        if not self._enabled:
            return None
        return await self._fetch_media(query)

    async def get_random(self, context: Dict[str, object]) -> Optional[MediaItem]:
        if not self._enabled:
            return None
        keywords = _extract_keywords(context)
        query = " ".join(keywords) if keywords else "goose"
        return await self._fetch_media(query)

    @property
    def _enabled(self) -> bool:
        return bool(self.api_key) and aiohttp is not None

    async def _fetch_media(self, query: str) -> Optional[MediaItem]:
        params = {
            "key": self.api_key,
            "q": query,
            "limit": 25,
            "media_filter": "gif",
        }
        data = await _get_json("https://tenor.googleapis.com/v2/search", params)
        if not data:
            return None
        results = data.get("results") or []
        random.shuffle(results)
        for item in results:
            media_formats = item.get("media_formats") or {}
            for key in ("gif", "mediumgif", "tinygif"):
                candidate = media_formats.get(key)
                url = candidate.get("url") if candidate else None
                if url:
                    tags = list(item.get("tags") or [])
                    return _make_item("url", url, "tenor", tags=tags)
        return None


@dataclass
class GiphyProvider(MediaProvider):
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("GIPHY_API_KEY"))

    async def search(self, query: str, context: Dict[str, object]) -> Optional[MediaItem]:
        if not self._enabled:
            return None
        return await self._fetch_media(query)

    async def get_random(self, context: Dict[str, object]) -> Optional[MediaItem]:
        if not self._enabled:
            return None
        keywords = _extract_keywords(context)
        query = " ".join(keywords) if keywords else "goose"
        return await self._fetch_media(query)

    @property
    def _enabled(self) -> bool:
        return bool(self.api_key) and aiohttp is not None

    async def _fetch_media(self, query: str) -> Optional[MediaItem]:
        params = {
            "api_key": self.api_key,
            "q": query,
            "limit": 25,
            "rating": "pg-13",
        }
        data = await _get_json("https://api.giphy.com/v1/gifs/search", params)
        if not data:
            return None
        results = data.get("data") or []
        random.shuffle(results)
        for item in results:
            images = item.get("images") or {}
            for key in ("original", "downsized", "fixed_height"):
                candidate = images.get(key)
                url = candidate.get("url") if candidate else None
                if url:
                    tags = [tag for tag in item.get("tags") or []]
                    return _make_item("url", url, "giphy", tags=tags)
        return None


@dataclass
class MediaProviderHub:
    local: LocalMediaProvider = field(default_factory=lambda: LocalMediaProvider(name="local"))
    server: ServerMediaProvider = field(default_factory=lambda: ServerMediaProvider(name="server"))
    tenor: TenorProvider = field(default_factory=lambda: TenorProvider(name="tenor"))
    giphy: GiphyProvider = field(default_factory=lambda: GiphyProvider(name="giphy"))

    async def initialize(self) -> None:
        await self.local.initialize()
        await self.server.initialize()
        await self.tenor.initialize()
        await self.giphy.initialize()

    async def search(self, query: str, context: Optional[Dict[str, object]] = None) -> Optional[MediaItem]:
        context = context or {}
        provider_chain = self._choose_providers(context, prefer_query=True)
        for provider in provider_chain:
            result = await provider.search(query, context)
            if result:
                return result
        return None

    async def get_random(self, context: Optional[Dict[str, object]] = None) -> Optional[MediaItem]:
        context = context or {}
        provider_chain = self._choose_providers(context, prefer_query=False)
        for provider in provider_chain:
            result = await provider.get_random(context)
            if result:
                return result
        return None

    def add_server_media(self, guild_id: int, keywords: Iterable[str], urls: Iterable[str]) -> None:
        self.server.add_media(guild_id, keywords, urls)

    def _choose_providers(self, context: Dict[str, object], *, prefer_query: bool) -> List[MediaProvider]:
        keywords = _extract_keywords(context)
        if context.get("takeover"):
            return _provider_chain([self.tenor, self.giphy, self.local, self.server])

        honk_density = float(context.get("honk_density", 0.0) or 0.0)
        if honk_density >= HONK_DENSITY_THRESHOLD:
            context.setdefault("preferred_categories", ["chaos", "angry"])
            return _provider_chain([self.local, self.tenor, self.giphy, self.server])

        if self.local.has_keyword_match(keywords):
            return _provider_chain([self.local, self.server, self.tenor, self.giphy])

        weights = [
            (self.local, 0.4),
            (self.tenor, 0.4),
            (self.giphy, 0.2),
        ]
        selection = _weighted_choice(weights)
        return _provider_chain([selection, self.server, self.local, self.tenor, self.giphy])


async def _get_json(url: str, params: Dict[str, object]) -> Optional[Dict[str, object]]:
    if aiohttp is None:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as response:
                if response.status != 200:
                    return None
                return await response.json()
    except (aiohttp.ClientError, ValueError, TimeoutError):
        return None


def _extract_keywords(context: Dict[str, object], *, query: Optional[str] = None) -> List[str]:
    keywords: List[str] = []
    for value in context.get("keywords", []) if context else []:
        if isinstance(value, str) and value:
            keywords.append(value)
    if query:
        keywords.extend(token for token in query.split() if token)
    return keywords


def _weighted_choice(weighted: Sequence[tuple[MediaProvider, float]]) -> MediaProvider:
    total = sum(weight for _, weight in weighted)
    if total <= 0:
        return weighted[0][0]
    roll = random.random() * total
    upto = 0.0
    for provider, weight in weighted:
        upto += weight
        if roll <= upto:
            return provider
    return weighted[-1][0]


def _provider_chain(candidates: Sequence[MediaProvider]) -> List[MediaProvider]:
    seen = set()
    ordered = []
    for provider in candidates:
        if provider.name in seen:
            continue
        seen.add(provider.name)
        ordered.append(provider)
    return ordered


def _make_item(item_type: str, value: str, source: str, *, tags: Sequence[str]) -> MediaItem:
    return {
        "type": item_type,
        "value": value,
        "source": source,
        "tags": list(tags),
    }