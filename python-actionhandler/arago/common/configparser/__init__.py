from configparser import ConfigParser
from arago.common.meta import ExtendByDecoratorMetaABC
from arago.common.helper import fallback

class FallbackConfigParser(ConfigParser, metaclass=ExtendByDecoratorMetaABC, methodsToDecorate = {fallback:['get','getint', 'getfloat', 'getboolean']}, ignoreUnknownMethods = True):
	pass
