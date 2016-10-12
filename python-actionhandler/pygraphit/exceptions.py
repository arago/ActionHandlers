class GraphitError(Exception):
	"""Error when talking to GraphIT"""
	def __init__(self, session, error):
		self.message="{sess} returned an error: {err}".format(
			sess=session,
			err=error)

	def __str__(self):
		return self.message

class WSO2Error(Exception):
	"""Error when talking to GraphIT"""
	def __init__(self, message):
		self.message=message

	def __str__(self):
		return self.message

class WSO2TokenRenewalError(WSO2Error):
	def __init__(self, message="Failed to get new token."):
		self.message=message
