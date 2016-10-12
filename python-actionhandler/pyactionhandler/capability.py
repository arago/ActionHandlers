class Capability(object):
	def __init__(self, action_class, **params):
		self.action_class=action_class
		self.params=params
