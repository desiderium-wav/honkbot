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


@dataclass
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
        return _make_item("url", random.choice(all_urls), "server", tags=[])\n
@dataclass\nclass TenorProvider(MediaProvider):\n    api_key: Optional[str] = field(default_factory=lambda: os.getenv("TENOR_API_KEY"))\n\n    async def search(self, query: str, context: Dict[str, object]) -> Optional[MediaItem]:\n        if not self._enabled:\n            return None\n        return await self._fetch_media(query)\n\n    async def get_random(self, context: Dict[str, object]) -> Optional[MediaItem]:\n        if not self._enabled:\n            return None\n        keywords = _extract_keywords(context)\n        query = " ".join(keywords) if keywords else "goose"\n        return await self._fetch_media(query)\n\n    @property\n    def _enabled(self) -> bool:\n        return bool(self.api_key) and aiohttp is not None\n\n    async def _fetch_media(self, query: str) -> Optional[MediaItem]:\n        params = {\n            "key": self.api_key,\n            "q": query,\n            "limit": 25,\n            "media_filter": "gif",\n        }\n        data = await _get_json("https://tenor.googleapis.com/v2/search", params)\n        if not data:\n            return None\n        results = data.get("results") or []\n        random.shuffle(results)\n        for item in results:\n            media_formats = item.get("media_formats") or {}\n            for key in ("gif", "mediumgif", "tinygif"):\n                candidate = media_formats.get(key)\n                url = candidate.get("url") if candidate else None\n                if url:\n                    tags = list(item.get("tags") or [])\n                    return _make_item("url", url, "tenor", tags=tags)\n        return None\n\n\n@dataclass\nclass GiphyProvider(MediaProvider):\n    api_key: Optional[str] = field(default_factory=lambda: os.getenv("GIPHY_API_KEY"))\n\n    async def search(self, query: str, context: Dict[str, object]) -> Optional[MediaItem]:\n        if not self._enabled:\n            return None\n        return await self._fetch_media(query)\n\n    async def get_random(self, context: Dict[str, object]) -> Optional[MediaItem]:\n        if not self._enabled:\n            return None\n        keywords = _extract_keywords(context)\n        query = " ".join(keywords) if keywords else "goose"\n        return await self._fetch_media(query)\n\n    @property\n    def _enabled(self) -> bool:\n        return bool(self.api_key) and aiohttp is not None\n\n    async def _fetch_media(self, query: str) -> Optional[MediaItem]:\n        params = {\n            "api_key": self.api_key,\n            "q": query,\n            "limit": 25,\n            "rating": "pg-13",\n        }\n        data = await _get_json("https://api.giphy.com/v1/gifs/search", params)\n        if not data:\n            return None\n        results = data.get("data") or []\n        random.shuffle(results)\n        for item in results:\n            images = item.get("images") or {}\n            for key in ("original", "downsized", "fixed_height"):\n                candidate = images.get(key)\n                url = candidate.get("url") if candidate else None\n                if url:\n                    tags = [tag for tag in item.get("tags") or []]\n                    return _make_item("url", url, "giphy", tags=tags)\n        return None\n\n\n@dataclass\nclass MediaProviderHub:\n    local: LocalMediaProvider = field(default_factory=lambda: LocalMediaProvider(name="local"))\n    server: ServerMediaProvider = field(default_factory=lambda: ServerMediaProvider(name="server"))\n    tenor: TenorProvider = field(default_factory=lambda: TenorProvider(name="tenor"))\n    giphy: GiphyProvider = field(default_factory=lambda: GiphyProvider(name="giphy"))\n\n    async def initialize(self) -> None:\n        await self.local.initialize()\n        await self.server.initialize()\n        await self.tenor.initialize()\n        await self.giphy.initialize()\n\n    async def search(self, query: str, context: Optional[Dict[str, object]] = None) -> Optional[MediaItem]:\n        context = context or {}\n        provider_chain = self._choose_providers(context, prefer_query=True)\n        for provider in provider_chain:\n            result = await provider.search(query, context)\n            if result:\n                return result\n        return None\n\n    async def get_random(self, context: Optional[Dict[str, object]] = None) -> Optional[MediaItem]:\n        context = context or {}\n        provider_chain = self._choose_providers(context, prefer_query=False)\n        for provider in provider_chain:\n            result = await provider.get_random(context)\n            if result:\n                return result\n        return None\n\n    def add_server_media(self, guild_id: int, keywords: Iterable[str], urls: Iterable[str]) -> None:\n        self.server.add_media(guild_id, keywords, urls)\n\n    def _choose_providers(self, context: Dict[str, object], *, prefer_query: bool) -> List[MediaProvider]:\n        keywords = _extract_keywords(context)\n        if context.get("takeover"):\n            return _provider_chain([self.tenor, self.giphy, self.local, self.server])\n\n        honk_density = float(context.get("honk_density", 0.0) or 0.0)\n        if honk_density >= HONK_DENSITY_THRESHOLD:\n            context.setdefault("preferred_categories", ["chaos", "angry"])\n            return _provider_chain([self.local, self.tenor, self.giphy, self.server])\n\n        if self.local.has_keyword_match(keywords):\n            return _provider_chain([self.local, self.server, self.tenor, self.giphy])\n\n        weights = [\n            (self.local, 0.4),\n            (self.tenor, 0.4),\n            (self.giphy, 0.2),\n        ]\n        selection = _weighted_choice(weights)\n        return _provider_chain([selection, self.server, self.local, self.tenor, self.giphy])\n\n\nasync def _get_json(url: str, params: Dict[str, object]) -> Optional[Dict[str, object]]:\n    if aiohttp is None:\n        return None\n    try:\n        async with aiohttp.ClientSession() as session:\n            async with session.get(url, params=params, timeout=10) as response:\n                if response.status != 200:\n                    return None\n                return await response.json()\n    except (aiohttp.ClientError, ValueError, TimeoutError):\n        return None\n\n\ndef _extract_keywords(context: Dict[str, object], *, query: Optional[str] = None) -> List[str]:\n    keywords: List[str] = []\n    for value in context.get("keywords", []) if context else []:\n        if isinstance(value, str) and value:\n            keywords.append(value)\n    if query:\n        keywords.extend(token for token in query.split() if token)\n    return keywords\n\n\ndef _weighted_choice(weighted: Sequence[tuple[MediaProvider, float]]) -> MediaProvider:\n    total = sum(weight for _, weight in weighted)\n    if total <= 0:\n        return weighted[0][0]\n    roll = random.random() * total\n    upto = 0.0\n    for provider, weight in weighted:\n        upto += weight\n        if roll <= upto:\n            return provider\n    return weighted[-1][0]\n\n\ndef _provider_chain(candidates: Sequence[MediaProvider]) -> List[MediaProvider]:\n    seen = set()\n    ordered = []\n    for provider in candidates:\n        if provider.name in seen:\n            continue\n        seen.add(provider.name)\n        ordered.append(provider)\n    return ordered\n\n\ndef _make_item(item_type: str, value: str, source: str, *, tags: Sequence[str]) -> MediaItem:\n    return {\n        "type": item_type,\n        "value": value,\n        "source": source,\n        "tags": list(tags),\n    }