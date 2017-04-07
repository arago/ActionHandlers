#!/usr/bin/env python2
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

name = 'connectit-netcool-adapter'

distutils.core.setup(
	name=name,
	version='0.4',
	author="Marcus Klemm",
	author_email="mklemm@arago.de",
	url="https://arago.co",
	description="Provide an backsync interface for Netcool",
	long_description="Receive updates in SDF format from ConnectIT and forward them to NetCool via its SOAP API",
	scripts=['bin/connectit-netcool-adapter.py'],
	data_files=[
		(
			'connectit-netcool-adapter/wsdl',
			['share/connectit-netcool-adapter/wsdl/netcool.wsdl']
		),
		(
			'connectit-netcool-adapter/schemas',
			[
				'share/connectit-netcool-adapter/schemas/event.json',
				'share/connectit-netcool-adapter/schemas/event-comment-added.json',
				'share/connectit-netcool-adapter/schemas/event-status-change.json'
			]
		),
		(
			'/opt/autopilot/connectit/conf/',
			[
				'config/netcool-adapter/connectit-netcool-adapter.conf',
				'config/netcool-adapter/connectit-netcool-adapter-environments.conf'
			]
		),
		(
			'/etc/init.d/',
			[
				'etc/init.d/connectit-netcool-adapter'
			]
		)
	]
)
