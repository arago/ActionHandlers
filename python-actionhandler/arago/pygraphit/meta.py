from abc import ABCMeta

class ExtendByDecoratorMeta(type):
	def __new__(cls, name, bases, d, methodsToDecorate, ignoreUnknownMethods=False):

		def not_implemented(*args, **kwargs):
			raise NotImplementedError('You called a function that is not'
			                          ' implemented!')

		# find method in base classes
		def find_method(m):
			for base in bases:
				try:
					return getattr(base, m)
				except AttributeError:
					pass
				if ignoreUnknownMethods:
					return not_implemented
				else:
					raise AttributeError(
						"No bases have method '{}'".format(m))

		# decorate specified methods with given decorator
		for decorator in methodsToDecorate:
			for method in methodsToDecorate[decorator]:
				d[method] = decorator(find_method(method))
		return type(name, bases, d)

class ExtendByDecoratorMetaABC(ExtendByDecoratorMeta, ABCMeta):
	pass
