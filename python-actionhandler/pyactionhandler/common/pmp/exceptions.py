class PMPError(Exception):
	def __init__(self, message):
		Exception.__init__(self, message)

class PMPConnectionError(PMPError):
	pass
