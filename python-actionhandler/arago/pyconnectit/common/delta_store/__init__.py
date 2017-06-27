import gevent
import logging, lmdb, jsonmerge, itertools, sys, time
import ujson as json
from arago.common.helper import prettify
from lz4 import compress, uncompress


class DeltaStoreFull(Exception):
	def __init__(self, message):
		Exception.__init__(self, message)

class DeltaStore(object):
	def __init__(self, db_path, max_size, schemafile):
		self.db_path=db_path
		self.logger = logging.getLogger('root')
		self._sem = gevent.lock.BoundedSemaphore()
		self.lmdb = lmdb.open(
			db_path,
			map_size=max_size,
			subdir=False,
			max_dbs=5,
			writemap=True,
			# metasync=False,
			# sync=False,
			map_async=True,
			max_readers=16,
			max_spare_txns=10)
		self.index_name = 'index'.encode('utf-8')
		self.deltas_name = 'deltas'.encode('utf-8')
		self.mtimes_name = 'mtimes'.encode('utf-8')
		with self._sem:
			with self.lmdb.begin(write=True) as txn:
				self.lmdb.open_db(
					key=self.index_name, txn=txn, dupsort=True)
				self.lmdb.open_db(
					key=self.mtimes_name, txn=txn)
				self.lmdb.open_db(
					key=self.deltas_name, txn=txn)
		self.delta_idx = self.get_delta_idx()
		self.merger = jsonmerge.Merger(json.load(schemafile))

	def __str__(self):
		return "DeltaStore at {path}".format(path=self.db_path)

	def get_delta_idx(self):
		with self.lmdb.begin() as txn:
			deltas_db = self.lmdb.open_db(
				key=self.deltas_name, txn=txn)
			with txn.cursor(db=deltas_db) as cursor:
				return itertools.count(
					start=int.from_bytes(
						cursor.key(),
						byteorder='big',
						signed=False)  + 1,
						step=1
				) if cursor.last() else itertools.count(
					start=1, step=1)
	def delete(self, eventId):
		with self._sem:
			with self.lmdb.begin(write=True) as txn:
				index_db = self.lmdb.open_db(
					key=self.index_name, txn=txn, dupsort=True)
				mtimes_db = self.lmdb.open_db(
					key=self.mtimes_name, txn=txn)
				deltas_db = self.lmdb.open_db(
					key=self.deltas_name, txn=txn)
				self.logger.debug(("Removing Event {ev} from the "
								   "database").format(ev=eventId))
				with txn.cursor(db=index_db) as cursor:
					cursor.set_key(eventId.encode('utf-8'))
					self.logger.debug("Found {n} deltas".format(
						n = cursor.count()))
					for delta_key in cursor.iternext_dup(keys=False):
						if self.logger.isEnabledFor(self.logger.TRACE):
							data = txn.get(delta_key, db=deltas_db)
							self.logger.trace(
								"Deleting delta {id}\n".format(
									id=int.from_bytes(
										delta_key, byteorder='big',
										signed=False))
								+ prettify(uncompress(data)))
						txn.delete(delta_key, db=deltas_db)
				self.logger.debug("Deleting MTIME")
				txn.delete(eventId.encode('utf-8'), db=mtimes_db)
				self.logger.debug("Deleting index entry")
				txn.delete(eventId.encode('utf-8'), db=index_db)

	def get_untouched(self, max_age):
		untouched = []
		with self.lmdb.begin() as txn:
			mtimes_db = self.lmdb.open_db(
				key=self.mtimes_name, txn=txn)
			with txn.cursor(db=mtimes_db) as cursor:
				if cursor.first():
					for eventId, timestamp in cursor.iternext(
							keys=True, values=True):
						age = int(time.time() * 1000) - int.from_bytes(
							timestamp,
							byteorder=sys.byteorder,
							signed=False)
						eventId = eventId.decode('utf-8')
						self.logger.debug(
							("Event {ev} was last updated {s} "
							 "milliseconds ago.").format(
								 ev = eventId, s = age))
						if age >= max_age * 1000:
							untouched.append(self.get_merged(eventId))
		return untouched

	def cleanup(self, max_age):
		with self.lmdb.begin() as txn:
			mtimes_db = self.lmdb.open_db(
				key=self.mtimes_name, txn=txn)
			with txn.cursor(db=mtimes_db) as cursor:
				if cursor.first():
					for eventId, timestamp in cursor.iternext(
							keys=True, values=True):
						age = int(time.time() * 1000) - int.from_bytes(
							timestamp,
							byteorder=sys.byteorder,
							signed=False)
						eventId = eventId.decode('utf-8')
						self.logger.debug(
							("Event {ev} was last updated {s} "
							 "milliseconds ago.").format(
								 ev = eventId, s = age))
						if age >= max_age * 1000:
							self.delete(eventId)

	def append(self, eventId, data):
		try:
			with self._sem:
				with self.lmdb.begin(write=True) as txn:
					eventId = eventId.encode('utf-8')
					data = compress(json.dumps(data))
					mtime = int(time.time() * 1000).to_bytes(
						length=6,
						byteorder=sys.byteorder,
						signed=False)
					delta_idx = next(self.delta_idx).to_bytes(
						length=511,
						byteorder='big',
						signed=False)
					index_db = self.lmdb.open_db(
						key=self.index_name, txn=txn, dupsort=True)
					mtimes_db = self.lmdb.open_db(
						key=self.mtimes_name, txn=txn)
					deltas_db = self.lmdb.open_db(
						key=self.deltas_name, txn=txn)
					txn.put(delta_idx, data, append=True, db=deltas_db)
					txn.put(eventId, delta_idx, dupdata=True, db=index_db)
					txn.put(eventId, mtime, overwrite=True, db=mtimes_db)
		except lmdb.MapFullError:
			raise DeltaStoreFull("Database file at {path} has reached its maximum size!".format(path=self.db_path))
	def get_merged(self, eventId):
		self.logger.debug("Merging event: " + eventId)
		with self.lmdb.begin() as txn:
			eventId = eventId.encode('utf-8')
			index_db = self.lmdb.open_db(
				key=self.index_name, txn=txn, dupsort=True)
			deltas_db = self.lmdb.open_db(
				key=self.deltas_name, txn=txn)
			with txn.cursor(db=index_db) as cursor:
				result = {}
				if cursor.set_key(eventId):
					for delta in cursor.iternext_dup():
						result = self.merger.merge(
							result,
							json.loads(uncompress(txn.get(
								delta, db=deltas_db))),
							meta={
								'timestamp': str(int(time.time()*1000))}
						)
				self.logger.trace(
					"Merged event data for {id}:\n".format(
						id=eventId.decode('utf-8'))
					+ prettify(result))
				return result
	def get_all(self):
		with self.lmdb.begin() as txn:
			index_db = self.lmdb.open_db(
				key=self.index_name, txn=txn, dupsort=True)
			with txn.cursor(db=index_db) as cursor:
				if cursor.first():
					result = [self.get_merged(eventId.decode('utf-8'))
							for eventId
							in cursor.iternext_nodup(values=False)]
					return result
