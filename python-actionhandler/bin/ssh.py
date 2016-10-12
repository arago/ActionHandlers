#!/bin/env python3
import base64
import getpass
import os
import socket
import sys
import traceback
from paramiko.py3compat import input

import paramiko
try:
	import interactive
except ImportError:
	from . import interactive

class IgnoreHK(paramiko.client.MissingHostKeyPolicy):
	def missing_host_key(self, client, hostname, key):
		return

hostname='lnxhop1.cognizant.dev'
port=22
username='vagrant'
password='vagrant'

try:
	with paramiko.SSHClient() as client:
		client.load_system_host_keys()
		client.set_missing_host_key_policy(IgnoreHK())
		client.connect(hostname, port, username, password)
		chan = client.invoke_shell()
		interactive.interactive_shell(chan)

except Exception as e:
	print('*** Caught exception: %s: %s' % (e.__class__, e))
	traceback.print_exc()
	try:
		client.close()
	except:
		pass
	sys.exit(1)

hoplist = [
	{
		'hostname':'lnxhop1',
		'protocol':'ssh'
	},
	{
		'hostname':'winhop1',
		'protocol':'winrm'
	}
]

class Hop(object):
	def __init__(self, hostname, auth, protocol, hop, first=False, last=False):
		self.hostname=hostname
		self.auth=auth
		self.protocol=protocol
		self.hop=hop
		self.first=first
		self.last=last
		self.intermediate = not (first or last)
		print(self)

	def __str__(self):
		return "Hop {hostname}".format(hostname=self.hostname)
