import logging, falcon
from base64 import b64decode

class BasicAuthentication(object):
	def __init__(self, username, password):
		self.logger = logging.getLogger('root')
		self.username = username
		self.password = password

	@classmethod
	def from_config(cls, auth_config):
		logger = logging.getLogger('root')
		username = auth_config.get('username')
		password = auth_config.get('password')
		if not (username and password):
			raise KeyError
		logger.info("Setting up Basic Authentication for REST API")
		return cls(username, password)

	def process_request(self, req, resp):
		credentials = req.get_header('Authorization')

		challenges = ['Basic realm="connectit-netcool-adapter"']

		if credentials is None:
			description = ('Please provide authentication '
						   'credentials as part of the request.')
			raise falcon.HTTPUnauthorized(
				'Auth token required',
				description,
				challenges)
		if not self._credentials_are_valid(credentials):
			description = ('The provided credentials are not valid. '
						   'Please request a new token and try again.')
			raise falcon.HTTPUnauthorized(
				'Authentication required',
				description,
				challenges,
				href='http://docs.example.com/auth')

	def _credentials_are_valid(self, credentials):
		try:
			credentials = b64decode(
				credentials.encode('ascii')[6:]).decode('ascii')
			username, password = tuple(
				falcon.uri.decode(item)
				for item
				in credentials.split(':', 1))
			self.logger.debug(username + ":" + self.username)
			self.logger.debug(password + ":" + self.password)
		except Exception:
			self.logger.error(
				"Error decoding authentication credentials!")
			return False
		return username == self.username and password == self.password
