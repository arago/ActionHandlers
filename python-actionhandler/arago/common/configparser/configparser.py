from configparser import ConfigParser
from pyactionhandler.meta import ExtendByDecoratorMetaABC
from pyactionhandler.helper import fallback

class FallbackConfigParser(ConfigParser, metaclass=ExtendByDecoratorMetaABC, methodsToDecorate = {fallback:['get','getint', 'getfloat', 'getboolean']}, ignoreUnknownMethods = True):
	pass
