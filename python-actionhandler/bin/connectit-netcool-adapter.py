#!/usr/bin/env python
"""connectit-netcool-adapter

Usage:
  connectit-netcool-adapter [options] (start|stop|restart)

Options:
  --nofork           do not fork into background
  --level=LEVEL      loglevel [default: DEBUG]
  --pidfile=PIDFILE  Specify pid file [default: /var/run/{progname}.pid]
  -h --help          Show this help screen
"""
import gevent
from gevent import monkey; monkey.patch_all(sys=True)
import logging, logging.config, sys, os, signal, gevent.hub, gevent.queue, gevent.pywsgi, requests, zeep, falcon
from configparser import ConfigParser
from docopt import docopt
from urllib.parse import urlparse, urlunparse

from arago.common.daemon import daemon as Daemon
from arago.common.logging.logger import Logger

from arago.pyconnectit.common.rest import Events, Queue, QueueObj

from arago.pyconnectit.connectors.common.trigger import FastTrigger
from arago.pyconnectit.connectors.common.handlers.log_status_change import LogStatusChange
from arago.pyconnectit.connectors.common.handlers.log_comments import LogComments
from arago.pyconnectit.connectors.common.handlers.watch_new import Watch, Unwatch
from arago.pyconnectit.connectors.netcool.handlers.sync_netcool_status import NetcoolBatchSyncer, SetStatus, ForwardStatus
from arago.pyconnectit.common.delta_store import DeltaStore
from arago.pyconnectit.common.lmdb_queue import LMDBTaskQueue
from arago.pyconnectit.common.rest.plugins.require_json import RequireJSON
from arago.pyconnectit.common.rest.plugins.rest_logger import RESTLogger
from arago.pyconnectit.common.rest.plugins.restrict_environment import RestrictEnvironment
from arago.pyconnectit.common.rest.plugins.json_translator import JSONTranslator
from arago.pyconnectit.common.rest.plugins.auth.basic import BasicAuthentication
from arago.pyconnectit.common.rest.plugins.store_deltas import StoreDeltas
from arago.pyconnectit.protocols.soap.plugins.soap_logger import SOAPLogger
from arago.pyconnectit.common.rest.plugins.rest_logger import RESTLogger

class ConnectitDaemon(Daemon):
	def run(self):
		config_path = '/opt/autopilot/connectit/conf/'
		main_config_file = os.path.join(
			config_path, 'connectit-netcool-adapter.conf')
		environments_config_file = os.path.join(
			config_path, 'connectit-netcool-adapter-environments.conf')
		share_dir = os.path.join(
			os.getenv('PYTHON_DATADIR'), 'connectit-netcool-adapter')

		# Read config files

		#logger.info("Reading config file {file}".format(file=main_config_file))
		adapter_config=ConfigParser()
		adapter_config.read(main_config_file)

		#logger.info("Reading config file {file}".format(file=environments_config_file))
		environments_config=ConfigParser()
		environments_config.read(environments_config_file)

		# Setup logging in normal operation

		logging.setLoggerClass(Logger)
		logger = logging.getLogger('root')
		level = getattr(
			logger, adapter_config.get(
				'Logging', 'loglevel',
				fallback='VERBOSE'))
		logfile = adapter_config.get(
			'Logging', 'logfile',
			fallback=os.path.join(
				'/var/log/autopilot/connectit/',
				'netcool-adapter.log'))
		debuglevel = self.debuglevel
		logger.setLevel(level)

		logfile_formatter = logging.Formatter(
			"%(asctime)s [%(levelname)s] %(message)s",
			"%Y-%m-%d %H:%M:%S")
		try:
			logfile_handler = logging.FileHandler(logfile)
		except PermissionError as e:
			print(e, file=sys.stderr, flush=True)
			sys.exit(5)
		logfile_handler.setFormatter(logfile_formatter)
		logfile_handler.setLevel(level)
		logger.addHandler(logfile_handler)

		# Setup debug logging
		if self.debug or self.nofork:
			stream_handler = logging.StreamHandler()
			stream_handler.setLevel(debuglevel)
			debug_formatter = logging.Formatter(
				"[%(levelname)s] %(message)s")
			stream_handler.setFormatter(debug_formatter)
			logger.setLevel(debuglevel)

			logger.addHandler(stream_handler)
			logger.info("DEBUG MODE: Logging to console and logfile")

		# Configure DeltaStore
		try:
			os.makedirs(adapter_config['DeltaStore']['data_dir'], mode=0o700, exist_ok=True)
			os.makedirs(adapter_config['Watchlist']['data_dir'], mode=0o700, exist_ok=True)
		except OSError as e:
			logger.critical("Can't create data directory: " + e)
			sys.exit(5)
		delta_store_map= {
			env:DeltaStore(
				db_path = os.path.join(adapter_config['DeltaStore']['data_dir'], env),
				max_size = 1024 * 1024 * adapter_config.getint('DeltaStore', 'max_size_in_mb', fallback=1024),
				schemafile = open(environments_config[env]['event_schema']))
			for env in environments_config.sections()
		}
		watchlist_map= {
			env:DeltaStore(
				db_path = os.path.join(adapter_config['Watchlist']['data_dir'], env),
				max_size = 1024 * 1024 * adapter_config.getint('Watchlist', 'max_size_in_mb', fallback=1024),
				schemafile = open(environments_config[env]['event_schema']))
			for env in environments_config.sections()
		}

		# Configure LMDBQueue
		queue_path = adapter_config['Queue']['data_dir']
		try:
			os.makedirs(queue_path, mode=0o700, exist_ok=True)
		except OSError as e:
			logger.critical("Can't create data directory: " + e)
			sys.exit(5)

		def setup_soapclient(env, prefix, verify=False):
			plugins=[]
			if logger.getEffectiveLevel() <= logger.TRACE:
				plugins.append(SOAPLogger())
			session = requests.Session()
			session.verify = verify
			try:
				session.auth = requests.auth.HTTPBasicAuth(
					environments_config[env][prefix + 'username'],
					environments_config[env][prefix + 'password'])
			except KeyError:
				logger.warning("No authentication data given for {env} using {wsdl}".format(
						env=env,
						wsdl=os.path.basename(
							environments_config[env][prefix + 'wsdl_file'])))
			finally:
				soap_client = zeep.Client(
					'file://' + environments_config[env][prefix + 'wsdl_file'],
					transport=zeep.Transport(session=session),
					plugins=plugins)
				setattr(soap_client, prefix + "service", soap_client.create_service(
					environments_config[env][prefix + 'service_binding'],
					environments_config[env][prefix + 'endpoint']))
				logger.info(
					"Setting up SOAP client for {env} using {wsdl}".format(
						env=env,
						wsdl=os.path.basename(
							environments_config[env][prefix + 'wsdl_file'])))
				return soap_client

		# Configure Triggers and Handlers

		log_status_handler = LogStatusChange()
		log_comment_handler = LogComments()

		netcool_queue_map = {env:LMDBTaskQueue(
			os.path.join(adapter_config['Queue']['data_dir'], env),
			disksize = 1024 * 1024 * adapter_config.getint(
				'Queue', 'max_size_in_mb', fallback=200))
					 for env
					 in environments_config.sections()}

		netcool_syncer = [NetcoolBatchSyncer(
			env,
			setup_soapclient(env, 'netcool_'),
			status_map={
				status.replace('netcool_' + 'status_', '', 1).capitalize():code
				for status, code in environments_config[env].items()
				if status.startswith('netcool_status_')},
			queue=netcool_queue_map[env],
			max_items=environments_config.getint(
				env, 'netcool_' + 'sync_amount',
				fallback=100),
			interval=environments_config.getint(
				env, 'netcool_' + 'sync_interval_in_seconds',
				fallback=60)
		) for env in environments_config.sections()]

		forward_status_netcool_handler = ForwardStatus(
			delta_store_map=delta_store_map,
			queue_map=netcool_queue_map
		)

		new_event_schema = open(os.path.join(share_dir, "schemas/event-new.json"))
		status_change_schema = open(os.path.join(share_dir, "schemas/event-status-change.json"))
		comment_added_schema = open(os.path.join(share_dir, "schemas/event-comment-added.json"))
		status_ejected_schema = open(os.path.join(share_dir, "schemas/event-status-ejected.json"))
		issue_created_schema = open(os.path.join(share_dir, "schemas/event-comment-issue-created.json"))
		handover_clear_schema = open(os.path.join(share_dir, "schemas/event-handover-clear.json"))
		resolved_schema = open(os.path.join(share_dir, "schemas/event-resolved.json"))

		set_issue_created_status_netcool_handler = SetStatus(
			"Issue_created",
			delta_store_map=delta_store_map,
			queue_map=netcool_queue_map
		)

		set_resolved_status_netcool_handler = SetStatus(
			"Resolved",
			delta_store_map=delta_store_map,
			queue_map=netcool_queue_map,
			end_state_schemas=[handover_clear_schema]
		)

		set_resolved_external_status_netcool_handler = SetStatus(
			"Resolved_external",
		set_handover_clear_status_netcool_handler = SetStatus(
			"Handover_clear",
			delta_store_map=delta_store_map,
			queue_map=netcool_queue_map
		)

		resolved_external_schema = open(os.path.join(share_dir, "schemas/event-resolved-external.json"))
		watch_new_event = Watch(watchlist_map)
		unwatch_event = Unwatch(watchlist_map)

		triggers= [
			FastTrigger(new_event_schema, [watch_new_event]),
			FastTrigger(status_change_schema, [log_status_handler, forward_status_netcool_handler]),
			FastTrigger(comment_added_schema, [log_comment_handler]),
			FastTrigger(resolved_external_schema, [set_resolved_external_status_netcool_handler]),
			FastTrigger(issue_created_schema, [unwatch_event, set_issue_created_status_netcool_handler]),
			FastTrigger(resolved_schema, [set_resolved_status_netcool_handler]),
			FastTrigger(handover_clear_schema, [set_handover_clear_status_netcool_handler])
		]

		# Setup HTTP server for REST API

		events=Events(triggers, delta_store_map)
		netcool_queue =Queue(netcool_queue_map)
		netcool_queue_slot = QueueObj(netcool_queue_map)
		middleware = [
			RestrictEnvironment(environments_config.sections()),
			RequireJSON(),
			JSONTranslator(),
			StoreDeltas([events], delta_store_map)
		]
		try:
			if adapter_config.getboolean('Authentication', 'enabled'):
				middleware.append(BasicAuthentication.from_config(adapter_config['Authentication']))
			else:
				logger.warn("REST API does not require any authentication")
		except (NoSectionError, NoOptionError) as e:
			logger.warn("REST API does not require any authentication")
		except KeyError:
			logger.critical("Authentication enabled but no credentials set")
			sys.exit(5)
		if logger.getEffectiveLevel() <= logger.TRACE:
			middleware.append(RESTLogger())
		baseurl=urlparse(adapter_config['RESTInterface']['base_url'])
		rest_api=falcon.API(middleware=middleware)
		rest_api.add_route(baseurl.path + '/{env}/events/', events)
		rest_api.add_route(baseurl.path + '/{env}/netcool-queue/', netcool_queue)
		rest_api.add_route(baseurl.path + '/{env}/netcool-queue/{event_id}', netcool_queue_slot)

		server = gevent.pywsgi.WSGIServer(
			(baseurl.hostname, baseurl.port),
			rest_api,
			log=None,
			error_log=logger)

		# Handle graceful shutdown

		def exit_gracefully():
			logger.info("Shutting down ...")
			server.stop()
			logger.debug("Shutdown complete!")
			gevent.idle()
			sys.exit(0)

		gevent.hub.signal(signal.SIGINT, exit_gracefully)
		gevent.hub.signal(signal.SIGTERM, exit_gracefully)

		# Start

		logger.info("Starting REST service at {url}".format(
			url=urlunparse(baseurl)))
		for proc in netcool_syncer:
			proc.start()
		server.serve_forever()


if __name__ == "__main__":
	args=docopt(__doc__, version='connectit-netcool-adapter 0.2')
	daemon = ConnectitDaemon(args['--pidfile'], nofork=args['--nofork'], debuglevel=args['--level'])
	if   args['start']:
		daemon.start()
	elif args['stop']:
		daemon.stop()
	elif args['restart']:
		daemon.restart()
	sys.exit(0)
