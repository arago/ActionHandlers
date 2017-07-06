#!/usr/bin/env python2
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

name = 'connectit-netcool-adapter'

distutils.core.setup(
	name=name,
	version='0.9.0',
	author="Marcus Klemm",
	author_email="mklemm@arago.de",
	url="https://arago.co",
	description="Provide an backsync interface for Netcool",
	long_description="Receive updates in SDF format from ConnectIT and forward them to NetCool via its SOAP API",
	scripts=['bin/connectit-netcool-adapter.py', 'bin/netcool-control.py'],
	data_files=[
		(
			'connectit-netcool-adapter/wsdl',
			['share/connectit-netcool-adapter/wsdl/netcool.wsdl', 'share/connectit-netcool-adapter/wsdl/snow.wsdl']
		),
		(
			'connectit-netcool-adapter/schemas',
			[
				'share/connectit-netcool-adapter/schemas/event.json',
				'share/connectit-netcool-adapter/schemas/event-comment-added.json',
				'share/connectit-netcool-adapter/schemas/event-status-ejected.json',
				'share/connectit-netcool-adapter/schemas/event-status-change.json',
				'share/connectit-netcool-adapter/schemas/event-comment-issue-created.json',
				'share/connectit-netcool-adapter/schemas/event-resolved-external.json',
				'share/connectit-netcool-adapter/schemas/event-handover-clear.json',
				'share/connectit-netcool-adapter/schemas/event-new.json',
				'share/connectit-netcool-adapter/schemas/event-resolved.json'
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
		),
		(
			'/usr/bin/',
			[
				'bin/netcool-control'
			]
		)
	]
)
