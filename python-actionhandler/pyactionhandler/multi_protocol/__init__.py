class Route(object):
	def __init__(self):
		self.hops = []

	def add_hop(self, hop):
		self.hops.append(hop)

	def execute(self):
		pass


class Hop(object):
	def __init__(self, command, session):
		pass

	def wrap(self):
		pass

	def execute(self):
		pass

class Command(object):
	def __init__(self):
		pass

class Session(object):
	def __init__(self, protocol, auth):
		pass

class Protocol(object):
	def __init__(self):
		pass

class Auth(object):
	def __init__(self):
		pass
