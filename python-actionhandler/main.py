#!/usr/bin/env python
import gevent
from gevent import pywsgi
from gevent import monkey; monkey.patch_all()
import zeep
import redis
import redis.connection
import falcon
import sys
import gevent.hub
import signal
import time

from configparser import ConfigParser

from pyactionhandler import WorkerCollection, SyncHandler
from pyactionhandler.ayehu import AyehuAction, AyehuBackgroundAction
from pyactionhandler.winrm import WinRMCmdAction, WinRMPowershellAction
from pyactionhandler.ayehu.zeep_redis_cache import RedisCache

import pyactionhandler.ayehu.REST as rest

redis.connection.socket = gevent.socket

# Read config files
jumpserver_config = ConfigParser()
jumpserver_config.read('/opt/autopilot/conf/jumpserver.conf')

ayehu_config = ConfigParser()
ayehu_config.read('/opt/autopilot/conf/ayehu.conf')

pmp_config = ConfigParser()
pmp_config.read('/opt/autopilot/conf/pmp.conf')

# Set ZeroMQ socket
zmq_url="tcp://127.0.0.1:7289"

# Redis datastore for commands handed to Ayehu
commands_redis = redis.StrictRedis(
	host=ayehu_config.get('default', 'CommandsRedisHost'),
	port=ayehu_config.get('default', 'CommandsRedisPort'),
	db=ayehu_config.get('default', 'CommandsRedisDB'),
	charset = "utf-8",
	decode_responses = True)
commands_pubsub = commands_redis.pubsub(ignore_subscribe_messages=True)

# Redis datastore for zeep's cache
zeep_cache_redis = redis.StrictRedis(
	host=ayehu_config.get('default', 'ZeepCacheRedisHost'),
	port=ayehu_config.get('default', 'ZeepCacheRedisPort'),
	db=ayehu_config.get('default', 'ZeepCacheRedisDB'))
zeep_cache = RedisCache(timeout=3600, redis=zeep_cache_redis)
zeep_transport = zeep.transports.Transport(cache=zeep_cache)
zeep_client = zeep.Client(
	ayehu_config.get('default', 'URL'),transport=zeep_transport)

# Setup REST API for callback
rest_api = rest.RESTAPI(baseurl=ayehu_config.get('default', 'CallbackBaseURL'), redis=commands_redis, pubsub=commands_pubsub)

# Setup capabilities with their action class
capability_handlers={
	"ExecuteWorkflow":(AyehuAction, {
		'zeep_client':zeep_client,
		'redis':commands_redis,
		'ayehu_config':ayehu_config,
		'pmp_config':pmp_config,
		'rest_api':rest_api
	}),
	"ExecuteWorkflowInBackground":(AyehuBackgroundAction, {}),
	"ExecuteCommand":(WinRMCmdAction, {
		'pmp_config':pmp_config,
		'jumpserver_config':jumpserver_config
	}),
	"ExecutePowershell":(WinRMPowershellAction, {
		'pmp_config':pmp_config,
		'jumpserver_config':jumpserver_config
	})
}

worker_collection = WorkerCollection(size_per_worker=10,max_idle=300)
action_handler = SyncHandler(capability_handlers, worker_collection, zmq_url)

# Start
print("ready")
#gevent.joinall([gevent.spawn(action_handler.handle_requests)])

input_loop=gevent.spawn(action_handler.handle_requests)
output_loop=gevent.spawn(action_handler.handle_responses)

server = pywsgi.WSGIServer(
	('', 8080), rest_api.app)



def exit_gracefully():
	print("Starting shutdown at {time}".format(time=time.strftime("%H:%M:%S", time.localtime())))
	gevent.kill(input_loop)
	gevent.idle()
	worker_collection.shutdown_workers()
	print("waiting for all workers to shutdown...")
	while len(worker_collection.workers) > 0:
		print("{num} worker(s) still active".format(num=len(worker_collection.workers)))
		gevent.sleep(10)
	print("waiting for all responses to be delivered...")
	while action_handler.response_queue.unfinished_tasks > 0:
		print("{num} responses to be delivered".format(num=action_handler.response_queue.unfinished_tasks))
		gevent.sleep(10)
	gevent.kill(output_loop)
	gevent.idle()
	print("Finished shutdown at {time}".format(time=time.strftime("%H:%M:%S", time.localtime())))
	print("Exiting...")
	sys.exit()

gevent.hub.signal(signal.SIGINT, exit_gracefully)
gevent.hub.signal(signal.SIGTERM, exit_gracefully)

server.serve_forever()
