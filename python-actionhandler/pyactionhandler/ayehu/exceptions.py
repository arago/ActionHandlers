class AyehuAHError(Exception):
	def __init__(self, message):
		Exception.__init__(self, message)

class ExitTwiceError(AyehuAHError):
	pass

class ResourceNotExistsError(AyehuAHError):
	pass

class IssueUpdateError(AyehuAHError):
	pass

