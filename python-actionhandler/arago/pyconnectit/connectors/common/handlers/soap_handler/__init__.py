import requests, zeep, os, logging
from arago.pyconnectit.connectors.common.handlers.base_handler import BaseHandler
from arago.pyconnectit.protocols.soap.plugins.soap_logger import SOAPLogger

class SOAPHandler(BaseHandler):
	def __init__(self, soap_interfaces_map):
		super().__init__()
		self.soap_interfaces_map=soap_interfaces_map

	@classmethod
	def from_config(cls, adapter_config, environments_config, prefix=''):
		def setup_soapclient(env):
			logger=logging.getLogger('root')
			plugins=[]
			if logger.getEffectiveLevel() <= logger.TRACE:
				plugins.append(SOAPLogger())
			try:
				session = requests.Session()
				session.auth = requests.auth.HTTPBasicAuth(
					environments_config[env][prefix + 'username'],
					environments_config[env][prefix + 'password'])
			except KeyError:
				soap_client = zeep.Client(
					'file://' + environments_config[env][prefix + 'wsdl_file'],
					plugins=plugins)
			else:
				soap_client = zeep.Client(
					'file://' + environments_config[env][prefix + 'wsdl_file'],
					transport=zeep.Transport(session=session),
					plugins=plugins)
			finally:
				logger.info(
					"Setting up SOAP client for {env} using {wsdl}".format(
						env=env,
						wsdl=os.path.basename(
							environments_config[env][prefix + 'wsdl_file'])))
				return soap_client

		soap_interfaces_map = {
			env: setup_soapclient(env)
			for env in environments_config.sections()
		}
		return cls(soap_interfaces_map)

	def __call__(self, data, env):
		raise NotImplementedError
