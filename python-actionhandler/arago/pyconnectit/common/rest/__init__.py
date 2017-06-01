import logging, falcon, sys, hashlib
from urllib.parse import urlparse
from configparser import NoSectionError, NoOptionError
from arago.pyconnectit.common.rest.plugins.require_json import RequireJSON
from arago.pyconnectit.common.rest.plugins.rest_logger import RESTLogger
from arago.pyconnectit.common.rest.plugins.restrict_environment import RestrictEnvironment
from arago.pyconnectit.common.rest.plugins.json_translator import JSONTranslator
from arago.pyconnectit.common.rest.plugins.auth.basic import BasicAuthentication
from arago.pyconnectit.common.rest.plugins.store_deltas import StoreDeltas
from arago.pyconnectit.common.lmdb_queue import Empty
from arago.pyconnectit.connectors.netcool.handlers.sync_netcool_status import QueuingError

class Queue(object):
	def __init__(self, queue_map):
		self.queue_map=queue_map
		self.logger = logging.getLogger('root')

	def on_delete(self, req, resp, env):
		self.logger.info("Dropping queue for {env}!".format(env=env))
		self.queue_map[env].drop()
		resp.status = falcon.HTTP_204

	def on_get(self, req, resp, env):
		if req.get_param('info') == 'true':
			resp.context['result'] = {
				"queueName":env,
				"queuePath":self.queue_map[env].path,
				"maxDiskSize":self.queue_map[env].disksize,
				"compression":self.queue_map[env].compression,
				"entries":self.queue_map[env].qsize()
			}
			resp.status = falcon.HTTP_200
			return
		if req.get_param('count') == 'true':
			resp.context['result'] = self.queue_map[env].qsize()
			resp.status = falcon.HTTP_200
			return
		try:
			with self.queue_map[env].peek(block=False, max_items=None) as events:
				resp.context['result'] = [
					{
						"eventId":event.event_id,
						"eventName":event.status['mand']['eventName'],
						"status":event.status['free']['eventNormalizedStatus'][-1]['value'] if 'free' in event.status and 'eventNormalizedStatus' in event.status['free'] else None,
						"links": [
							{
								"rel":"self",
								"href":req.relative_uri + "/{id}".format(id=event.event_id)
							}
						]
					}
					for event
					in events
				]
			resp.status = falcon.HTTP_200
			return
		except Empty:
			resp.context['result'] = []
			resp.status = falcon.HTTP_200
			return

class QueueObj(object):
	def __init__(self, queue_map):
		self.queue_map=queue_map
		self.logger = logging.getLogger('root')

	def on_get(self, req, resp, env, event_id):
		hash_key = hashlib.sha1(event_id.encode('utf-8')).digest()
		data = self.queue_map[env].peek_by_hash(hash_key)
		if data:
			resp.context['result'] = data
			resp.status = falcon.HTTP_200
			return
		else:
			resp.status = falcon.HTTP_404
			return

	def on_delete(self, req, resp, env, event_id):
		hash_key = hashlib.sha1(event_id.encode('utf-8')).digest()
		result = self.queue_map[env].unqueue_by_hash(hash_key)
		if result:
			resp.status = falcon.HTTP_204
			return
		else:
			resp.status = falcon.HTTP_404
			return

class Events(object):
	def __init__(self, triggers, delta_store_map):
		self.logger = logging.getLogger('root')
		self.triggers = triggers
		self.delta_store_map=delta_store_map

	def on_post(self, req, resp, env):
		self.logger.debug("New message for environment: {env}".format(
			env=env))
		try:
			for trigger in self.triggers:
				trigger(req.context['doc'], env)
		except QueuingError as e:
			self.logger.critical(e)
			raise falcon.HTTPInsufficientStorage(
				title="Queue full",
				description=("The status update could not be enqueued "
							 "because the underlying on-disk-database "
							 "has reached its maximum size"))
		resp.status = falcon.HTTP_200

	def on_get(self, req, resp, env):
		try:
			event_id=req.get_param('id')
			if event_id:
				resp.context['result'] = self.delta_store_map[env].get_merged(
					event_id)
				resp.status = falcon.HTTP_200
			else:
				resp.context['result'] = self.delta_store_map[env].get_all()
				resp.status = falcon.HTTP_200
		except Exception as e:
			self.logger.debug(e)
			raise

	def on_delete(self, req, resp, env):
		try:
			max_age = int(req.get_param('max_age'))
			self.delta_store_map[env].cleanup(max_age)
			resp.status = falcon.HTTP_200
		except TypeError as e:
			self.logger.warning(e)
			raise falcon.HTTPBadRequest(
				'Required parameter missing',
				'This operation requires the max_age parameter to be set')
		except ValueError as e:
			self.logger.warning(e)
			raise falcon.HTTPBadRequest(
				'Wrong data',
				'Parameter max_age must be a number (of seconds)')
