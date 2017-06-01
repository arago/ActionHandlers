#!/usr/bin/env python
import gevent
from gevent import monkey; monkey.patch_all()
import gevent.hub
import sys, os
import signal
from docopt import docopt
import logging
import logging.config
import re
import subprocess as sp
import sys, xml.etree.ElementTree as et, datetime;
from arago.pyactionhandler.worker_collection import WorkerCollection
from arago.pyactionhandler.handler import SyncHandler
from arago.pyactionhandler.capability import Capability
from arago.common.configparser import ConfigParser
from configparser import NoSectionError, NoOptionError
from arago.common.daemon import daemon as Daemon
from arago.pyactionhandler.action import Action

import zeep, requests, ujson as json
from lxml import etree


class ActionHandlerError(Exception):
	def __init__(self, message):
		Exception.__init__(self, message)

class IDTransformator(object):
	def __init__(self):
		self.snow_regex = re.compile(r"")
		self.snow_fmt = "{}:{}"

		self.arago_regex = re.compile(r"^(?P<serial>[0-9]+)(?P<server>.+)$")
		self.arago_fmt = ""

		self.netcool_regex = re.compile(r"")
		self.netcool_fmt = ""

	def arago_in(self, arago_fmt):
		result = self.arago_regex.search(arago_fmt)
		if result:
			return (result.group('server'), result.group('serial'))

	def snow_out(self, data):
		if data:
			return self.snow_fmt.format(*data)

class SOAPLogger(zeep.Plugin):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.logger=logging.getLogger('root')

	def ingress(self, envelope, http_headers, operation):
		self.logger.debug("[TRACE] SOAP data received:\n" + etree.tostring(
			envelope, encoding='unicode', pretty_print=True))
		return envelope, http_headers

	def egress(self, envelope, http_headers, operation, binding_options):
		self.logger.debug(
			"[TRACE] SOAP data sent to {addr}:\n".format(
				addr=binding_options['address']) + etree.tostring(
					envelope, encoding='unicode', pretty_print=True))
		return envelope, http_headers

class SnowCreateIncidentAction(Action):
	def __init__(self, num, node, zmq_info, timeout, parameters, service_map):
		super().__init__(num, node, zmq_info, timeout, parameters)
		self.service_map = service_map
		self.id_transform = IDTransformator()

	def __str__(self):
		return "ServiceNow create incident action on node {node}".format(
			node=self.node)

	def get_issue_log(self):
		#elements = ['Log', 'VarDelete']
		elements = ['Log']
		timestamp_format = '%Y-%m-%d %H:%M:%S'
		element_format = "[{timestamp}] {name}: {message}"
		elements = ['Log', 'VarDelete']
		ns = "{https://graphit.co/schemas/v2/IssueSchema}"
		try:
			xml = sp.check_output(["aae_getissue", "-u", "tcp://localhost:7284", "-x",  self.parameters['IID']], universal_newlines=True)
			results = [element_format.format(
				timestamp=datetime.datetime.fromtimestamp(
					int(entry.attrib['Timestamp'])/1000
				).strftime(timestamp_format),
				name=entry.attrib['ElementName'].upper(),
				message=entry.attrib['ElementMessage'])
					   for entry in et.fromstring(xml).findall(
							   "./{ns}IssueHistory/{ns}HistoryEntry".format(ns=ns))
					   if entry.attrib['ElementName'] in elements]
			return "\n".join(results)
		except FileNotFoundError:
			self.logger.error("Could not get Issue history for {uuid}: aae_getissue not found!".format(
				uuid=self.parameters['IID']))
			self.error_output += "Could not get Issue history for {uuid}\n".format(
				uuid=self.parameters['IID'])
			return
		except sp.CalledProcessError as e:
			self.logger.error(("Could not get Issue history for {uuid}: '{cmd}' "
								  "returned non-zero exit status {rc}").format(
									  uuid=self.parameters['IID'],
									  cmd = " ".join(e.cmd),
									  rc = e.returncode))
			self.error_output += "Could not get Issue history for {uuid}\n".format(
				uuid=self.parameters['IID'])
			return
		except et.ParseError as e:
			self.logger.error("Could not get Issue history for {uuid}: {err}".format(
				uuid=self.parameters['IID'], err=e))
			self.error_output += "Could not get Issue history for {uuid}.\n".format(
				uuid=self.parameters['IID'])
			return
		except Exception as e:
			self.logger.error("Could not get Issue history for {uuid}: {err}".format(
				uuid=self.parameters['IID'], err=e))
			self.error_output += "Could not get Issue history for {uuid}.\n".format(
				uuid=self.parameters['IID'])
			return

	def __call__(self):
		try:
			args={'UBStable':"incident", 'UBSaction':"create"}
			try:
				args['system'] = self.parameters['System']
			except KeyError:
				raise ActionHandlerError("Cannot create incident ticket for issue {iid}, "
								  "System not specified".format(iid=self.parameters['IID']))
			try:
				args['summary'] = self.parameters['Summary']
			except KeyError:
				raise ActionHandlerError("Cannot create incident ticket for issue {iid}, "
								  "no Summary given".format(iid=self.parameters['IID']))
			try:
				env = self.parameters['Environment']
			except KeyError:
				raise ActionHandlerError("Required parameter 'Environment' missing")
			try:
				service = self.service_map[env]
			except KeyError:
				raise ActionHandlerError(("Unknown environment '{env}': Check your "
										  "snow-actionhandler-environments.conf").format(
											  env=self.parameters['Environment']))
			args['details']="Severity={sev}, Location={loc}, OwnerGID={gid}, Subclass={subc}, FirstOccurrence={fo}, LastOccurrence={lo}, Tally={t}".format(
				sev=self.parameters['Severity'] if 'Severity' in self.parameters else "",
				loc=self.parameters['Location'] if 'Location' in self.parameters else "", # Stamford ???
				gid=self.parameters['OwnerGID'] if 'OwnerGID' in self.parameters else "", # 1468 ???
				subc=self.parameters['Subclass'] if 'Subclass' in self.parameters else "", # "UNIX" ???
				fo=self.parameters['FirstOccurrence'] if 'FirstOccurrence' in self.parameters else "",
				lo="", t="")
			if 'NetcoolID' in self.parameters:
				args['netcool_id']=self.id_transform.snow_out(self.id_transform.arago_in(self.parameters['NetcoolID']))
			args['arago_id']=self.parameters['IID']
			if 'WorkNotes' in self.parameters:
				if self.parameters['WorkNotes'] == '__ISSUE_LOG__':
					args['notes'] = self.get_issue_log()
				elif self.parameters['WorkNotes'] == '__NONE__':
					args['notes'] = None
				else:
					args['notes']=self.parameters['WorkNotes']
			if 'ErrorCode' in self.parameters:
				args['error_code']=self.parameters['ErrorCode']
			result = service.snow_service.execute(**args)
			if result.UBSstatus == 'success' and result.inc_number:
				self.success = True
				self.output = result.inc_number
				self.system_rc = 0
			else:
				self.success = True
				self.system_rc = 5
				self.error_output += result.UBSerror_message if result.UBSerror_message else "Unknown error" + "\n"
		except (zeep.exceptions.TransportError, requests.exceptions.ConnectionError, ActionHandlerError) as e:
			self.success=False
			self.statusmsg = str(e)

class SnowStubAction(Action):
	def __init__(self, num, node, zmq_info, timeout, parameters, service):
		super().__init__(num, node, zmq_info, timeout, parameters)
		self.service = service

	def __str__(self):
		return "This should never happen on node {node}".format(node=self.node)

	def __call__(self):
		raise NotImplementedError

class ActionHandlerDaemon(Daemon):
	def run(self):

		# Open config files
		actionhandler_config=ConfigParser()
		actionhandler_config.read('/opt/autopilot/conf/external_actionhandlers/snow-actionhandler.conf')

		environments_config=ConfigParser()
		environments_config.read('/opt/autopilot/conf/external_actionhandlers/snow-actionhandler-environments.conf')

		# Setup logging in normal operation
		try:
			logging.config.fileConfig('/opt/autopilot/conf/external_actionhandlers/snow-actionhandler-log.conf')
			logger = logging.getLogger('root')
		except FileNotFoundError as e:
			print(e, file=sys.stderr)
			sys.exit(5)

		# Setup debug logging (see commandline interface at the end of the file)
		if self.debug:
			logger.setLevel(logging.DEBUG)
			ch = logging.StreamHandler()
			ch.setLevel(logging.DEBUG)
			formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s","%Y-%m-%d %H:%M:%S")
			ch.setFormatter(formatter)
			logger.addHandler(ch)
			logger.info("Logging to console and logfile")

		def setup_soapclient(env, prefix, verify=False):
			plugins=[]
			# if logger.getEffectiveLevel() <= logger.TRACE:
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

		snow_interfaces_map = {
			env: setup_soapclient(env, 'snow_')
			for env in environments_config.sections()
		}

		capabilities = {
			"SnowCreateTicket":Capability(SnowCreateIncidentAction, service_map=snow_interfaces_map)
		}

		worker_collection = WorkerCollection(
			capabilities,
			parallel_tasks = 10,
			parallel_tasks_per_worker = 3,
			worker_max_idle = 300,
		)

		try:
			if not actionhandler_config.getboolean('Encryption', 'enabled'):
				raise ValueError
			zmq_auth = (
				actionhandler_config.get('Encryption', 'server-public-key', raw=True).encode('ascii'),
				actionhandler_config.get('Encryption', 'server-private-key', raw=True).encode('ascii')
			)
		except (ValueError, NoSectionError, NoOptionError):
			zmq_auth = None

		snow_handler = SyncHandler(
			worker_collection,
			zmq_url = actionhandler_config.get('ActionHandler', 'ZMQ_URL'),
			auth = zmq_auth
		)

		action_handlers = [snow_handler]

		# Function to shutdown gracefully by letting all current commands finish
		def exit_gracefully():
			logger.info("Starting shutdown")
			for action_handler in action_handlers:
				action_handler.shutdown()
				logger.info("Finished shutdown")

		# Graceful shutdown can be triggered by SIGINT and SIGTERM
		gevent.hub.signal(signal.SIGINT, exit_gracefully)
		gevent.hub.signal(signal.SIGTERM, exit_gracefully)


		# Start main gevent loop
		greenlets=[action_handler.run() for action_handler in action_handlers]
		gevent.idle()
		gevent.joinall(greenlets)
		sys.exit(0)


# Command line interface
if __name__ == "__main__":
	usage="""Usage:
  {progname} [options] (start|stop|restart)

Options:
  --debug            do not run as daemon and log to stderr
  --pidfile=PIDFILE  Specify pid file [default: /var/run/{progname}.pid]
  -h --help          Show this help screen
""".format(progname='hiro-snow-actionhandler')

	args=docopt(usage)

	daemon = ActionHandlerDaemon(args['--pidfile'], debug=args['--debug'])

	if args['start']: daemon.start()
	elif args['stop']: daemon.stop()
	elif args['restart']: daemon.restart()

	sys.exit(0)
