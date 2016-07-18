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
