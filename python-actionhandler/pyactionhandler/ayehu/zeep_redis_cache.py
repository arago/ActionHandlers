from zeep.cache import SqliteCache
import redis

class RedisCache(SqliteCache):
	_version = '1'

	def __init__(self, timeout=3600, redis=None):
		self._redis=redis
		self._timeout=timeout

	def add(self, url, content):
		self._redis.set(url, content, px=self._timeout * 1000)

	def get(self, url):
		return self._redis.get(url)
