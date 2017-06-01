#!/usr/bin/env python
"""ah-client: Small command line utility to trigger external ActionHandlers without the HIRO Engine

Usage:
  ah-client [options] [(-k <cl_pubkey> <cl_privkey> <srv_pubkey>)] [(--parameter PARAMETER = VALUE)...] NODEID

Options:
  -u <url>, --url=<url>                       ZMQ socket of the ActionHandler
  -c <capability>, --capability=<capability>  Capability to trigger [default: ExecuteCommand]
  -p, --parameter                             Additional parameters
  -t <timeout>, --timeout=<timeout>           Timeout in seconds [default: 120]

Switches:
  -h, --help                                  print help and exit
  -v, --version                               print version and exit
"""
import sys, zmq
from docopt import docopt
from arago.pyactionhandler.protobuf.ActionHandler_pb2 import ActionRequest, ActionResponse
from arago.pyactionhandler.protobuf.CommonTypes_pb2 import KeyValueMessage

def encode_rpc_call(*args):
	rpc_call = b''
	for arg in args:
		rpc_call += (b'\x02'
					 + len(arg).to_bytes(length=1, byteorder=sys.byteorder, signed=False)
					 + arg.encode("utf-8"))
	return rpc_call

if __name__ == '__main__':
	args = docopt(__doc__, version='ah-client 0.1')
	rpc_call = encode_rpc_call("ActionHandlerService", "Execute", "1.0", "")
	params = [KeyValueMessage(key="NodeID", value=args['NODEID'])]
	for par, val in zip(args['PARAMETER'], args['VALUE']):
		params.append(KeyValueMessage(key=par, value=val))
	req=ActionRequest(capability=args['--capability'], time_out = int(args['--timeout']))
	req.params_list.extend(params)
	socket = zmq.Context().socket(zmq.DEALER)
	if args['-k']:
		try:
			socket.curve_secretkey = args['<cl_privkey>'].encode('ascii')
			socket.curve_publickey = args['<cl_pubkey>'].encode('ascii')
			socket.curve_serverkey = args['<srv_pubkey>'].encode('ascii')
		except zmq.error.ZMQError:
			print("Encryption keys malformed")
			sys.exit(5)
	socket.connect(args['--url'])
	socket.send_multipart((b'ahc', rpc_call, req.SerializeToString()))
	id1, svc_call, payload = socket.recv_multipart()
	resp = ActionResponse()
	resp.ParseFromString(payload)
	if resp.success:
		print("Command execution successful:\n\nstdout:\n{stdout}\n\n{stderr}\n\nreturn code: {rc}".format(
			stdout=resp.output, stderr=resp.error_text, rc=resp.system_rc))
	else:
		print("Command execution failed:\n\n{status}".format(status=resp.statusmsg))
