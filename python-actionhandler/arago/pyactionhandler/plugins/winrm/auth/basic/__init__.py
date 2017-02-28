

class basicSession(Session):
	def __init__(self, endpoint, auth, target=None, target_auth=None, transport='ssl', validation='ignore'):
		username, password = auth
		self.protocol = winrm.Protocol(
			endpoint=endpoint,
			transport=transport,
			username=username,
			password=password,
			server_cert_validation=validation
		)
		self.target = target
		self.target_auth = target_auth
