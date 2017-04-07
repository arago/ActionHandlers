import logging, falcon
import ujson as json

class JSONTranslator(object):
	def __init__(self):
		self.logger = logging.getLogger('root')

	def process_request(self, req, resp):
		if req.content_length in (None, 0): return

		body = req.stream.read()
		if not body:
			raise falcon.HTTPBadRequest(
				'Empty request body',
				'A valid JSON document is required.')
		try:
			req.context['doc'] = json.loads(body.decode('utf-8'))
		except ValueError:
			self.logger.trace(
				"Malformed data received "
				"via {op} ar {uri}:\n".format(
					op=req.method,uri=req.relative_uri)
				+ body.decode('utf-8')
			)
			raise falcon.HTTPError(
				falcon.HTTP_753,
				'Malformed JSON',
				'Could not decode the request body.')
		except UnicodeDecodeError:
			self.logger.trace(
				"Malformed data received "
				"via {op} ar {uri}:\n".format(
					op=req.method,uri=req.relative_uri)
				+ str(body)
			)
			raise falcon.HTTPError(
				falcon.HTTP_753,
				'Encoding error',
				'Could not decode payload as UTF-8')

	def process_response(self, req, resp, resource):
		if 'result' not in resp.context:
			return

		resp.body = json.dumps(resp.context['result'])
