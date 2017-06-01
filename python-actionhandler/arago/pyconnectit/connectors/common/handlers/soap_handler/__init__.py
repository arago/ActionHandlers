import requests, zeep, os, logging
from arago.pyconnectit.connectors.common.handlers.base_handler import BaseHandler
from arago.pyconnectit.protocols.soap.plugins.soap_logger import SOAPLogger

class SOAPHandler(BaseHandler):
	def __init__(self, soap_interfaces_map):
		super().__init__()
		self.soap_interfaces_map=soap_interfaces_map

	def __call__(self, data, env):
		raise NotImplementedError
