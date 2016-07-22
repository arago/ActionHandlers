from configparser import ConfigParser, NoSectionError, NoOptionError

class FallbackConfigParser(ConfigParser):
	def get(self, *args, **kwargs):
		try:
			return super(FallbackConfigParser, self).get(*args, **kwargs)
		except (NoSectionError, NoOptionError):
			return super(FallbackConfigParser, self).get('default', args[1], **kwargs)
