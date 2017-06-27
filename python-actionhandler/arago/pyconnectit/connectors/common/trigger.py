import logging, fastjsonschema, jsonschema, os
import ujson as json
import gevent

class Trigger(object):
	def __init__(self, schemafile, handlers=[]):
		self.logger = logging.getLogger('root')
		self.logger.info("Setting up new trigger for schema {schema} with handlers {handlers}".format(
			schema=os.path.basename(schemafile.name),
			handlers=[str(handler) for handler in handlers]))
		self.logger.verbose("Loading schema {schema} from {path}.".format(
			schema=os.path.basename(schemafile.name),
			path=schemafile.name))
		self.schemafile=schemafile
		schemafile.seek(0)
		self.schema = json.load(schemafile)
		self.handlers = handlers

	def validate(self, data):
		jsonschema.validate(data, self.schema)

	def __call__(self, data, env):
		try:
			self.validate(data)
			self.logger.debug((
				"Schema {s} validated, "
				"calling Handlers: {handlers}").format(
					s=os.path.basename(self.schemafile.name),
					handlers=[str(handler) for handler in self.handlers]))
			results = [gevent.spawn(handler, data, env) for handler in self.handlers]
			[result.get() for result in results]
		except (jsonschema.ValidationError, fastjsonschema.JsonSchemaException):
			self.logger.debug((
				"Schema {s} could not be validated, "
				"ignoring event.").format(
					s=os.path.basename(self.schemafile.name)))

class FastTrigger(Trigger):
	def __init__(self, schemafile, handlers=[]):
		super().__init__(schemafile, handlers)
		self.validator = fastjsonschema.compile(self.schema)

	def validate(self, data):
		self.validator(data)
