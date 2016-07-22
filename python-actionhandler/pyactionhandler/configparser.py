from configparser import ConfigParser, NoSectionError, NoOptionError

class FallbackConfigParser(ConfigParser):
	def get(self, *args, **kwargs):
		try:
			return super(FallbackConfigParser, self).get(*args, **kwargs)
		except (NoSectionError, NoOptionError):
			return super(FallbackConfigParser, self).get('default', args[1], **kwargs)

	def getint(self, *args, **kwargs):
		try:
			return super(FallbackConfigParser, self).getint(*args, **kwargs)
		except (NoSectionError, NoOptionError):
			return super(FallbackConfigParser, self).getint('default', args[1], **kwargs)
