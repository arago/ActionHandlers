#!/usr/bin/env python
import zmq

pubkey, secretkey = zmq.curve_keypair()
print("""\
public  key: {pk}
private key: {sk} """.format(
	pk=pubkey.decode('ascii'),
	sk=secretkey.decode('ascii')
))
