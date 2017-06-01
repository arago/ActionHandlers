import gevent
from gevent.queue import Queue, Empty, Full
from lz4 import compress, uncompress
import itertools
import lmdb
import sys, pickle, logging
from arago.common.helper import chunks
from functools import partial
from arago.common.helper import prettify

class LMDBQueue(Queue):
	def __init__(self, path, maxsize=-1, disksize = 100 * 1024 * 1024,
				 compression=False):
		self.path=path
		self.compression=compression
		self.disksize=disksize
		self.logger = logging.getLogger('root')
		self._sem = gevent.lock.BoundedSemaphore()
		super().__init__(maxsize=maxsize)

	def copy(self):
		raise NotImplementedError

	def _get_counter(self):
		with self._lmdb.begin() as txn:
			with txn.cursor(db=self._queue_db) as cursor:
				if cursor.last():
					end = int.from_bytes(
						cursor.key(), byteorder='big', signed=False)
					self._idx = itertools.count(start = end  + 1, step=1)
				else:
					self._idx = itertools.count(start=1, step=1)

	def _init(self, maxsize, items=None):
		self._lmdb = lmdb.open(
			self.path, map_size = self.disksize, subdir=False,
			max_dbs=5, writemap=True, map_async=True,
			max_readers=16, max_spare_txns=10)
		self._queue_db=self._lmdb.open_db(key=b'queue')
		self._get_counter()

	def _get(self):
		with self._sem:
			with self._lmdb.begin(write=True, buffers=True) as txn:
				with txn.cursor(db=self._queue_db) as cursor:
					if cursor.first():
						buf = cursor.pop(cursor.key())
						return pickle.loads(
							uncompress(buf)
						) if self.compression else pickle.loads(buf)
					else: raise Empty()

	def _peek(self):
		with self._lmdb.begin(write=False, buffers=True) as txn:
			with txn.cursor(db=self._queue_db) as cursor:
				if cursor.first():
					buf = cursor.value()
					return pickle.loads(
						uncompress(buf)
					) if self.compression else pickle.loads(buf)
				else: raise Empty()

	def _put(self, item):
		key = next(self._idx).to_bytes(
			length=511,
			byteorder=sys.byteorder,
			signed=False)
		data=compress(
			pickle.dumps(item, protocol=4)
		) if self.compression else pickle.dumps(item, protocol=4)
		with self._sem:
			with self._lmdb.begin(write=True) as txn:
				txn.put(key, data, append=True, db=self._queue_db)

	def _qsize(self):
		return self.qsize()

	def qsize(self):
		with self._lmdb.begin() as txn:
			return txn.stat(self._queue_db)['entries']


class LMDBHashQueue(LMDBQueue):
	def _init(self, maxsize, items=None):
		super()._init(maxsize, items=items)
		self._hashes_db=self._lmdb.open_db(key=b'hashes')

	def _get(self):
		with self._sem:
			with self._lmdb.begin(write=True, buffers=True) as txn:
				with txn.cursor(db=self._queue_db) as cursor:
					if cursor.first():
						hash_key = cursor.pop(cursor.key())
					else: raise Empty()
				buf = txn.pop(hash_key, db=self._hashes_db)
				return pickle.loads(
					uncompress(buf)
				) if self.compression else pickle.loads(buf)

	def _peek(self):
		with self._lmdb.begin(write=False, buffers=True) as txn:
			with txn.cursor(db=self._queue_db) as cursor:
				if cursor.first(): hash_key = cursor.value()
				else: raise Empty()
			buf = txn.get(hash_key, db=self._hashes_db)
			return pickle.loads(
				uncompress(buf)
			) if self.compression else pickle.loads(buf)

	def _put(self, item):
		hash_key=item.__hash__().to_bytes(
			length=20, byteorder=sys.byteorder, signed=True)
		data=compress(
			pickle.dumps(item, protocol=4)
		) if self.compression else pickle.dumps(item, protocol=4)
		with self._sem:
			try:
				with self._lmdb.begin(write=True) as txn:
					if not txn.replace(
							hash_key, data, db=self._hashes_db):
						key =next(self._idx).to_bytes(
							length=511, byteorder='big', signed=False)
						self.logger.debug(
							"Queuing new task with SERIAL {sn}".format(
								sn=int.from_bytes(
									key, byteorder='big', signed=False)))
						txn.put(key, hash_key, append=True,
							db=self._queue_db)
					else:
						self.logger.debug("Updating already queued task")
			except lmdb.MapFullError:
				self.logger.critical("Database file {path} reached maximum size!".format(path=self.path))
				raise Full()

class LMDBTaskQueue(LMDBHashQueue):

	class QueueTransaction(object):
		def __init__(self, releasefunc, items):
			self._releasefunc=releasefunc
			self._items=items

		def __enter__(self):
			return self._items

		def __exit__(self, exc_type, exc_value, traceback):
			if exc_type or exc_value or traceback:
				self.abort()
			else:
				self.commit()

		def commit(self):
			self._releasefunc(commit=True)
		def abort(self):
			self._releasefunc(commit=False)


	def _unpack(self, buf):
		if self.compression:
			return pickle.loads(uncompress(buf))
		else:
			return pickle.loads(buf)

	def _walk(self, txn, op, releasefunc, max_items=1):
		if max_items == None:
			max_items = self.qsize()
		with txn.cursor(db=self._queue_db) as cursor:
			if cursor.first():
				items = [
					op(serial, hash_key)
					for serial, hash_key
					in next(chunks(cursor.iternext(), size=max_items))
				]
				return self.QueueTransaction(releasefunc, items)
			else:
				raise Empty()

	def _get(self, max_items=1):
		def __get(serial, hash_key):
			txn.delete(serial, db=self._queue_db)
			payload=txn.pop(hash_key, db=self._hashes_db)
			if payload:
				return self._unpack(payload)
		def __release(commit=False):
			if commit:
				txn.commit()
			else:
				txn.abort()
			self._sem.release()
		self._sem.acquire()
		txn = self._lmdb.begin(write=True)
		return self._walk(txn, __get, __release, max_items)

	def _peek(self, max_items=1):
		txn = self._lmdb.begin()
		def __peek(serial, hash_key):
			payload=txn.get(hash_key, db=self._hashes_db)
			if payload:
				return self._unpack(payload)
		def __release(commit=False):
			if commit:
				txn.commit()
			else:
				txn.abort()
		return self._walk(txn, __peek, __release, max_items)

	def get(self, block=True, timeout=None, max_items=1):
		if self.qsize():
			if self.putters:
				self._schedule_unlock()
			return self._get(max_items=max_items)
		return self._Queue__get_or_peek(
			partial(self._get, max_items=max_items),
			block, timeout)

	def get_nowait(self, max_items=1):
		return self.get(block=False, max_items=max_items)

	def peek(self, block=True, timeout=None, max_items=1):
		if self.qsize():
			# XXX: Why doesn't this schedule an unlock like get() does?
			return self._peek(max_items=max_items)
		return self._Queue__get_or_peek(
			partial(self._peek, max_items=max_items),
			block, timeout)

	def peek_by_hash(self, hash_key, block=False, timeout=None):
		with self._lmdb.begin() as txn:
			payload = txn.get(hash_key, default=None, db=self._hashes_db)
			return self._unpack(payload) if payload else None

	def unqueue_by_hash(self, hash_key, block=False, timeout=None):
		def find_serial(hash_key):
			with self._lmdb.begin() as txn:
				with txn.cursor(db=self._queue_db) as cursor:
					for serial, hash_key_in_db in cursor.iternext():
						if hash_key == hash_key_in_db:
							return serial
		serial = find_serial(hash_key)
		self._sem.acquire()
		try:
			with self._lmdb.begin(write=True) as txn:
				result_del_hash_key = txn.delete(hash_key, db=self._hashes_db)
				result_del_serial = txn.delete(serial, db=self._queue_db)
				if not (result_del_hash_key and result_del_serial):
					txn.abort()
		except lmdb.BadValsizeError:
			if result_del_hash_key:
				self.logger.warn("Encountered a queue inconsistency!")
		self._sem.release()
		return result_del_hash_key and result_del_serial

	def drop(self):
		self._sem.acquire()
		with self._lmdb.begin(write=True) as txn:
			txn.drop(db=self._hashes_db, delete=False)
			txn.drop(db=self._queue_db, delete=False)
		self._sem.release()

	def peek_nowait(self, max_items=1):
		return self.peek(block=False, max_items=max_items)

	def stats(self):
		with self._lmdb.begin() as txn:
			return prettify({
				'Queue':txn.stat(self._queue_db),
				'Hashes':txn.stat(self._hashes_db)
			})
