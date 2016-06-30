import json
import falcon
import uuid
import redis
from ayehu_actionhandler.exceptions import AyehuAHError, ExitTwiceError, ResourceNotExistsError

class CommandCollection(object):
	def __init__(self, redis, baseurl):
		self.redis = redis
		self.baseurl = baseurl

	def register_command(self, command):
		self.command = command

	def format_entry(self, id):
		return {
			"id":id,
			"links":[{"rel":"self",
					  "href":"{baseurl}/commands/{id}".format(
						  id=id, baseurl=self.baseurl)}]}

	def get(self):
		return self.redis.keys("????????-????-????-????-????????????")

	def on_get(self, req, resp):
		data = self.get()
		data = [self.format_entry(entry) for entry in data]
		resp.body = json.dumps(data)
		resp.status = falcon.HTTP_200

	def post(self, data):
		id = str(uuid.uuid4())
		data["Parameters"] = json.dumps(data["Parameters"])
		self.redis.hmset(id, data)
		return id

	def on_post(self, req, resp):
		# TODO: input validation and sanitation
		data = json.loads(req.stream.read().decode("utf-8"))
		id = self.post(data)
		resp.body = json.dumps(id)
		resp.status = falcon.HTTP_201

class Command(object):
	def __init__(self, collection):
		self.collection=collection
		self.redis = collection.redis
		collection.register_command(self)
		self.outputs = []

	def exists(self, id):
		return self.redis.exists(id)

	def register_output(self, name):
		self.outputs.append(name)

	def get(self, id):
		if self.exists(id):
			data = self.redis.hgetall(id)
			try:
				data["Parameters"] = json.loads(data["Parameters"])
			except KeyError:
				pass
			return data
		else:
			raise ResourceNotExistsError("Command {id} does not exist".format(id=id))

	def on_get(self, req, resp, id):
		try:
			resp.body = json.dumps(self.get(id))
			resp.status = falcon.HTTP_200
		except ResourceNotExistsError:
			resp.status = falcon.HTTP_404

	def delete(self, id):
		self.redis.delete(id)
		[self.redis.delete("{id}-{name}".format(id=id, name=output))
		 for output in self.outputs]

	def on_delete(self, req, resp, id):
		self.delete(id)
		resp.status = falcon.HTTP_204

class Output(object):
	def __init__(self, command, name):
		command.register_output(name)
		self.command = command
		self.redis = command.redis
		self.name = name

	def exists(self, id):
		return self.redis.exists("{id}-{name}".format(
			id=id, name=self.name))

	def get(self, id):
		if self.exists(id):
			return self.redis.lrange("{id}-{name}".format(
				id=id, name=self.name), 0, -1)
		else:
			raise ResourceNotExistsError(
				"Output channel {channel} does not exist".format(
					channel=self.name))

	def on_get(self, req, resp, id):
		try:
			resp.body = json.dumps(self.get(id))
			resp.status = falcon.HTTP_200
		except ResourceNotExistsError:
			resp.status = falcon.HTTP_404

	def post(self, id, data):
		if self.command.exists(id):
			self.redis.rpush(
				"{id}-{name}".format(id=id, name=self.name), data)
		else:
			raise ResourceNotExistsError(
				"Output channel {channel} does not exist".format(
					channel=self.name))

	def on_post(self, req, resp, id):
		try:
			self.post(id, json.loads(req.stream.read().decode("utf-8")))
			resp.status=falcon.HTTP_205
		except ResourceNotExistsError:
			resp.status=falcon.HTTP_404
		except:
			resp.status=falcon.HTTP_500

class Property(object):
	def __init__(self, command):
		self.redis = command.redis

	def exists(self, id, name):
		return self.redis.hexists(id, name)

	def get(self, id, name):
		if self.exists(id, name):
			data = self.redis.hget(id, name)
			try:
				data = json.loads(data)
			except ValueError as e:
				pass
			return data
		else:
			raise ResourceNotExistsError('Property does not exist')

	def on_get(self, req, resp, id, name):
		try:
			data = self.get(id, name)
			resp.body = json.dumps(data)
			resp.status = falcon.HTTP_200
		except ResourceNotExistsError:
			resp.status = falcon.HTTP_404

class Exit(object):
	def __init__(self, command):
		self.redis = command.redis

	def exists(self, id):
		return self.redis.exists(id)

	def post(self, id, data):
		if self.exists(id):
			if not self.redis.hexists(id, "rc"):
				self.redis.publish(id, 'exit')
				self.redis.hset(id, "rc", data)
			else:
				raise ExitTwiceError(
					'Command can only be terminated once')
		else:
			raise ResourceNotExistsError('Command does not exist')

	def on_post(self, req, resp, id):
		try:
			self.post(id, json.loads(req.stream.read().decode("utf-8")))
			resp.status = falcon.HTTP_204
		except ExitTwiceError:
			resp.status = falcon.HTTP_410
		except ResourceNotExistsError:
			resp.status = falcon.HTTP_404q
