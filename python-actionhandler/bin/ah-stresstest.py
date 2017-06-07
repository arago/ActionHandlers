#!/usr/bin/env python
"""\
Usage: stresstest [options] [(--parameter PARAMETER = VALUE)...]

Options:
  -m <model_size>   Size of the simulated MARS [default: 10000]
  -s <subset_size>  Subset to run commands on [default: 1000]
  -o <offset>       Offset when selecting subset [default: 0]
  -r                Choose subset randomly (renders -o obsolete)
  -n <prefix>       nodeid prefix [default: "test:test:test:test_{0}"]
  -a <actions>      Number of actions to perform [default: 1000]
  -u <url>          ZMQ socket of the ActionHandler [default: tcp://localhost:7291]
  -c <capability>   Capability to trigger [default: Rhyme]
  -p, --parameter   Additional parameters
  -t <timeout>      Timeout in seconds [default: 120]
  
"""
import gevent
from gevent import monkey; monkey.patch_all(sys=True)
from gevent.pool import Pool
from docopt import docopt
import sys, random
import signal
import zmq.green as zmq
from docopt import docopt
from arago.pyactionhandler.protobuf.ActionHandler_pb2 import ActionRequest, ActionResponse
from arago.pyactionhandler.protobuf.CommonTypes_pb2 import KeyValueMessage
import itertools

def encode_rpc_call(*args):
	rpc_call = b''
	for arg in args:
		rpc_call += (b'\x02'
					 + len(arg).to_bytes(length=1, byteorder=sys.byteorder, signed=False)
					 + arg.encode("utf-8"))
	return rpc_call

def send(socket, i):
	if i % 1000 == 999:
		print("Sending Action {n}".format(n=i+1))
	#params = [KeyValueMessage(key="NodeID", value=random.choice(nodes))]
	params = [
		KeyValueMessage(
			key="NodeID",
			value=working_set[i % len(working_set)] if type(working_set) is type(list()) else next(working_set)
		)
	]
	for par, val in zip(args['PARAMETER'], args['VALUE']):
		params.append(KeyValueMessage(key=par, value=val))
	req=ActionRequest(capability=args['-c'], time_out = int(args['-t']))
	req.params_list.extend(params)
	rpc_call = encode_rpc_call("ActionHandlerService", "Execute", "1.0", "")
	myid=i.to_bytes(3, byteorder=sys.byteorder, signed=False)
	socket.send_multipart((myid, rpc_call, req.SerializeToString()))
	sent[i]=True

def receive(socket):
	for i in range(total):
		id1, svc_call, payload = socket.recv_multipart()
		#print("Received Answer {n}".format(n=i+1))
		x = int.from_bytes(id1, byteorder=sys.byteorder, signed=False)
		del sent[x]

args=docopt(__doc__)
#print(args)


total = int(args['-a'])
nums=itertools.count(start=1, step=1)
nodes=[args['-n'].format(num) for num in range(1, int(args['-m'])+1)]
if args['-r']:
	working_set = (random.choice(nodes) for n in nums)
else:
	offset = int(args['-o'])
	length = int(args['-s'])
	working_set = nodes[offset:offset+length]
	if offset+length > len(nodes):
		working_set += nodes[0:offset+length-len(nodes)]
sent={}

def sendall():
	for i in range(total):
		send(socket, i)

socket = zmq.Context().socket(zmq.DEALER)
socket.connect('tcp://localhost:7291')
x = gevent.spawn(receive, socket)
y = gevent.spawn(sendall)


def exit_gracefully():
	print("kill")
	x.kill()
	y.kill()

gevent.hub.signal(signal.SIGINT, exit_gracefully)
gevent.hub.signal(signal.SIGTERM, exit_gracefully)

y.join()
x.join()
for k in sent.keys():
	print("Action {n} not returned".format(n=k))
