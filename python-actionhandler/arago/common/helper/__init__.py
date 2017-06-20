import ujson as json
from itertools import islice, chain

def chunks(iterable, size=10):
	iterator = iter(iterable)
	for first in iterator: yield chain([first], islice(iterator, size - 1))

def decode_rpc_call(message):
	def parse_protobuf(message):
		bitmask = 0b00000111
		index = 0
		rpc_call = []
		while True:
			try:
				field_type = message[index] & bitmask
				if field_type != 2:
					raise NotImplementedError
				field_length = message[index + 1]
				field_data = message[index+2:field_length+index+2].decode("utf-8")
			except IndexError:
				break
			rpc_call.append(field_data)
			index += field_length +2
		return rpc_call

	try:
		service, method, version, empty = parse_protobuf(message)
	except NotImplementedError:
		raise DecodeRPCError("Message does not contain a method call")
	return service, method


def encode_rpc_call(*args):
	rpc_call = b''
	for num in range(len(args)):
		rpc_call += (((num+1 << 3) + 2).to_bytes(length=1, byteorder='big', signed=False) + len(args[num]).to_bytes(length=1, byteorder='big', signed=False) + args[num].encode("utf-8"))
	rpc_call += ((num+1 << 3) + 3).to_bytes(length=2, byteorder='big', signed=False)
	return rpc_call

def addBaseURL(function):
	def wrapper(self, *args, **kwargs):
		if args:
			args = (self._baseurl + args[0],) + args[1:]
		if 'url' in kwargs:
			kwargs['url'] = self._baseurl + kwargs['url']
		return function(self, *args, **kwargs)
	return wrapper

def fallback(function):
	def wrapper(self, *args, **kwargs):
		try:
			return function(self, *args, **kwargs)
		except (NoSectionError):
			self.add_section(args[0])
			return function(self, *args, **kwargs)
	return wrapper

def prettify(data):
	try:
		data = data.decode('utf-8')
	except:
		pass
	try:
		data=json.loads(data)
	except:
		pass
	return json.dumps(
		data,
		sort_keys=True,
		indent=4)
