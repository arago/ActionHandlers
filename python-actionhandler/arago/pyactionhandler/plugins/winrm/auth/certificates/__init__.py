

class certSession(Session):
	def __init__(self, endpoint, certificate, target=None, target_auth=None, validation='ignore'):
		self.protocol = winrm.Protocol(
			endpoint=endpoint,
			transport='certificate',
			server_cert_validation=validation,
			cert_pem=certificate,
			cert_key_pem=certificate
		)
		if target and target_auth:
			self.target = target
			self.target_auth = (target_auth.WindowsUserName, target_auth.passwd())
		else:
			self.target=None
			self.target_auth=None
