import asyncio
import time
import random
import json
import logging
from typing import Any, Dict, List, Optional, Set, Union
from config.settings import settings

logger = logging.getLogger(__name__)

class InMemoryPipeline:
    def __init__(self, cache: "InMemoryCache"):
        self.cache = cache
        self.commands = []

    def smembers(self, key: str):
        self.commands.append(("smembers", key))
        return self

    def scard(self, key: str):
        self.commands.append(("scard", key))
        return self

    def sadd(self, key: str, *members: str):
        self.commands.append(("sadd", key, members))
        return self

    def expire(self, key: str, seconds: int):
        self.commands.append(("expire", key, seconds))
        return self

    def spop(self, key: str, count: int = 1):
        self.commands.append(("spop", key, count))
        return self

    def delete(self, key: str):
        self.commands.append(("delete", key))
        return self

    async def exec(self):
        results = []
        for cmd in self.commands:
            action = cmd[0]
            if action == "smembers":
                res = await self.cache.smembers(cmd[1])
                results.append((True, list(res)))
            elif action == "scard":
                res = await self.cache.scard(cmd[1])
                results.append((True, res))
            elif action == "sadd":
                res = await self.cache.sadd(cmd[1], *cmd[2])
                results.append((True, res))
            elif action == "expire":
                res = await self.cache.expire(cmd[1], cmd[2])
                results.append((True, res))
            elif action == "spop":
                res = await self.cache.spop(cmd[1], cmd[2])
                results.append((True, res))
            elif action == "delete":
                res = await self.cache.delete(cmd[1])
                results.append((True, res))
        return results

class InMemoryCache:
    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._sets: Dict[str, Set[str]] = {}
        self._expirations: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    def _is_expired(self, key: str) -> bool:
        if key in self._expirations:
            if time.time() > self._expirations[key]:
                self._store.pop(key, None)
                self._sets.pop(key, None)
                self._expirations.pop(key, None)
                return True
        return False

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            if self._is_expired(key):
                return None
            val = self._store.get(key)
            return str(val) if val is not None else None

    async def set(self, key: str, value: Any, keep_ttl: bool = False) -> bool:
        async with self._lock:
            self._store[key] = str(value)
            if not keep_ttl:
                self._expirations.pop(key, None)
            return True

    async def setex(self, key: str, seconds: int, value: Any) -> bool:
        async with self._lock:
            self._store[key] = str(value)
            self._expirations[key] = time.time() + seconds
            return True

    async def delete(self, *keys: str) -> int:
        async with self._lock:
            count = 0
            for k in keys:
                self._expirations.pop(k, None)
                if self._store.pop(k, None) is not None:
                    count += 1
                if self._sets.pop(k, None) is not None:
                    count += 1
            return count

    async def sadd(self, key: str, *members: str) -> int:
        async with self._lock:
            if self._is_expired(key):
                self._sets[key] = set()
            if key not in self._sets:
                self._sets[key] = set()
            before = len(self._sets[key])
            for m in members:
                self._sets[key].add(str(m))
            return len(self._sets[key]) - before

    async def smembers(self, key: str) -> Set[str]:
        async with self._lock:
            if self._is_expired(key):
                return set()
            return set(self._sets.get(key, set()))

    async def scard(self, key: str) -> int:
        async with self._lock:
            if self._is_expired(key):
                return 0
            return len(self._sets.get(key, set()))

    async def spop(self, key: str, count: int = 1) -> List[str]:
        async with self._lock:
            if self._is_expired(key):
                return []
            s = self._sets.get(key, set())
            if not s:
                return []
            popped = []
            for _ in range(min(count, len(s))):
                elem = random.choice(list(s))
                s.remove(elem)
                popped.append(elem)
            return popped

    async def expire(self, key: str, seconds: int) -> bool:
        async with self._lock:
            if key in self._store or key in self._sets:
                self._expirations[key] = time.time() + seconds
                return True
            return False

    def pipeline(self):
        return InMemoryPipeline(self)


class CacheClient:
    def __init__(self):
        self._redis = None
        self._in_memory = InMemoryCache()
        self._is_redis_available = False
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        self._initialized = True
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(settings.REDIS_URI, decode_responses=True)
            await self._redis.ping()
            self._is_redis_available = True
            logger.info("Connected to Redis successfully.")
        except Exception as e:
            self._is_redis_available = False
            logger.warning(f"Redis connection failed ({e}). Falling back to In-Memory Cache.")

    async def get(self, key: str) -> Optional[str]:
        if not self._initialized:
            await self.initialize()
        if self._is_redis_available:
            try:
                return await self._redis.get(key)
            except Exception:
                pass
        return await self._in_memory.get(key)

    async def set(self, key: str, value: Any, keep_ttl: bool = False) -> bool:
        if not self._initialized:
            await self.initialize()
        if self._is_redis_available:
            try:
                if keep_ttl:
                    return await self._redis.set(key, value, keepttl=True)
                return await self._redis.set(key, value)
            except Exception:
                pass
        return await self._in_memory.set(key, value, keep_ttl=keep_ttl)

    async def setex(self, key: str, seconds: int, value: Any) -> bool:
        if not self._initialized:
            await self.initialize()
        if self._is_redis_available:
            try:
                return await self._redis.setex(key, seconds, value)
            except Exception:
                pass
        return await self._in_memory.setex(key, seconds, value)

    async def delete(self, *keys: str) -> int:
        if not self._initialized:
            await self.initialize()
        if self._is_redis_available:
            try:
                return await self._redis.delete(*keys)
            except Exception:
                pass
        return await self._in_memory.delete(*keys)

    async def sadd(self, key: str, *members: str) -> int:
        if not self._initialized:
            await self.initialize()
        if self._is_redis_available:
            try:
                return await self._redis.sadd(key, *members)
            except Exception:
                pass
        return await self._in_memory.sadd(key, *members)

    async def smembers(self, key: str) -> Set[str]:
        if not self._initialized:
            await self.initialize()
        if self._is_redis_available:
            try:
                res = await self._redis.smembers(key)
                return set(res)
            except Exception:
                pass
        return await self._in_memory.smembers(key)

    async def scard(self, key: str) -> int:
        if not self._initialized:
            await self.initialize()
        if self._is_redis_available:
            try:
                return await self._redis.scard(key)
            except Exception:
                pass
        return await self._in_memory.scard(key)

    async def spop(self, key: str, count: int = 1) -> List[str]:
        if not self._initialized:
            await self.initialize()
        if self._is_redis_available:
            try:
                res = await self._redis.spop(key, count)
                if res is None:
                    return []
                return [res] if isinstance(res, str) else list(res)
            except Exception:
                pass
        return await self._in_memory.spop(key, count)

    async def expire(self, key: str, seconds: int) -> bool:
        if not self._initialized:
            await self.initialize()
        if self._is_redis_available:
            try:
                return await self._redis.expire(key, seconds)
            except Exception:
                pass
        return await self._in_memory.expire(key, seconds)

    def pipeline(self):
        if self._is_redis_available and self._redis:
            return self._redis.pipeline()
        return self._in_memory.pipeline()

cache = CacheClient()
