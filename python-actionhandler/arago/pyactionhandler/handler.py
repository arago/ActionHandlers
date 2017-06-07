import gevent, sys
import zmq.green as zmq
from zmq.error import ZMQError
from greenlet import GreenletExit
import greenlet
from arago.pyactionhandler.exceptions import DecodeRPCError
from arago.pyactionhandler.protobuf.ActionHandler_pb2 import ActionRequest, ActionResponse
import itertools
import logging

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

class SyncHandler(object):
	def __init__(self, worker_collection, zmq_url, auth=None):
		self.logger = logging.getLogger('root')
		self.worker_collection=worker_collection
		self.zmq_url=zmq_url
		self.zmq_ctx = zmq.Context()
		self.zmq_socket = self.zmq_ctx.socket(zmq.ROUTER)
		if auth:
			try:
				self.logger.info("Using CURVE encryption for HIRO engine interface")
				self.zmq_socket.curve_publickey, self.zmq_socket.curve_secretkey = auth
				self.zmq_socket.curve_server = True
			except ZMQError:
				self.logger.critical("CURVE keys malformed, please check your config file!")
				sys.exit(5)
		else:
			self.logger.warn("HIRO engine interface is not encrypted!")
		self.zmq_socket.bind(self.zmq_url)
		self.response_queue=gevent.queue.JoinableQueue(maxsize=0)
		self.worker_collection.register_response_queue(
			self.response_queue)

	def run(self):
		self.input_loop=gevent.spawn(self.handle_requests)
		self.worker_loop=gevent.spawn(self.worker_collection.handle_requests_per_worker)
		self.output_loop=gevent.spawn(self.handle_responses)
		self.counter=itertools.count(start=1, step=1)
		return self.output_loop

	def shutdown(self):
		gevent.kill(self.input_loop)
		gevent.idle()
		self.logger.info("Waiting for all responses to be delivered...")
		self.response_queue.join()
		self.worker_collection.shutdown_workers()
		self.logger.info("Waiting for all workers to shutdown...")
		while len(self.worker_collection.workers) > 0:
			self.logger.debug("{num} worker(s) still active".format(num=len(self.worker_collection.workers)))
			gevent.sleep(1)
		gevent.kill(self.output_loop)
		self.logger.info("ActionHandler shut down, {num} actions processed".format(num=next(self.counter)-1))

	def next_request(self):
		id1, id2, svc_call, params = self.zmq_socket.recv_multipart()
		try:
			anum=next(self.counter)
			service, method = decode_rpc_call(svc_call)
			req=ActionRequest()
			req.ParseFromString(params)
			params_dict = {param.key: param.value for param in req.params_list}
			self.logger.debug("[{anum}] Decoded RPC message".format(anum=anum))
			return (
				anum, req.capability, req.time_out,
				params_dict, (id1, id2, svc_call))
		except (DecodeRPCError)  as e:
			self.logger.error("Could not decode RPC message")
			raise

	def handle_requests(self):
		try:
			self.logger.info("Started handling requests")
			while True:
				if self.worker_collection.task_queue.unfinished_tasks >= self.worker_collection.parallel_tasks:
					gevent.sleep(0.001)
					continue
				try:
					anum, capability, timeout, params, zmq_info = self.next_request()
				except (DecodeRPCError):
					continue
				self.worker_collection.task_queue.put(
					(anum, capability, timeout, params, zmq_info))
				self.logger.debug(
					"[{anum}] Put Action on ActionHandler request queue".format(anum=anum))
		except GreenletExit as e:
			## Block all further incoming messages
			self.logger.info("Stopped handling requests")
			self.worker_collection.task_queue.join()

	def handle_responses(self):
		try:
			self.logger.info("Started handling responses")
			while True:
				action=self.response_queue.get()
				id1, id2, svc_call = action.zmq_info
				resp=ActionResponse()
				resp.output = action.output
				resp.error_text = action.error_output
				resp.system_rc = action.system_rc
				resp.statusmsg = action.statusmsg
				resp.success = action.success
				self.zmq_socket.send_multipart((id1, id2, svc_call, resp.SerializeToString()))
				#self.worker_collection.task_queue.task_done()
				del id1, id2, svc_call, resp
				self.response_queue.task_done()
				self.logger.debug("[{anum}] Removed Action from ActionHandler response queue".format(
					anum=action.num))
		except GreenletExit as e:
			self.logger.info("Stopped handling responses")

