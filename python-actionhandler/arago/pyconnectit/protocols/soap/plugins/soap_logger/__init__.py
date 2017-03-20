import zeep, logging
from lxml import etree

class SOAPLogger(zeep.Plugin):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.logger=logging.getLogger('root')

	def ingress(self, envelope, http_headers, operation):
		self.logger.trace("SOAP data received:\n" + etree.tostring(
			envelope, encoding='unicode', pretty_print=True))
		return envelope, http_headers

	def egress(self, envelope, http_headers, operation, binding_options):
		self.logger.trace(
			"SOAP data sent to {addr}:\n".format(
				addr=binding_options['address']) + etree.tostring(
					envelope, encoding='unicode', pretty_print=True))
		return envelope, http_headers
