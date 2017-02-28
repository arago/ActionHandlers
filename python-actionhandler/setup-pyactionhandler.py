#!/usr/bin/env python
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

name = 'arago-pyactionhandler'

distutils.core.setup(
	name = "arago-pyactionhandler",
	version = "2.0",
	author = "Marcus Klemm",
	author_email = "mklemm@arago.de",
	description = ("Python module for Arago HIRO ActionHandlers"),
	license = "MIT",
	url = "http://www.arago.de",
	long_description="""\
pyactionhandler is a python module to develop external
ActionHandlers for the arago HIRO automation engine.

An ActionHandler is used to access target systems in
order to execute commands. This is not limited to
shell commands but can be anything that provides some
kind of command line or API, e.g. SQL.
	""",
	classifiers=[
		"Development Status :: 5 - Production/Stable",
		"Topic :: Utilities",
		"License :: OSI Approved :: MIT License",
	],
	packages=['arago.pyactionhandler',
			  'arago.pyactionhandler.protobuf'
	],
	install_requires=['gevent', 'docopt', 'zmq', 'protobuf'],
	scripts=['bin/autopilot-counting-rhyme-actionhandler.py'],
	data_files=[
		(
			'/opt/autopilot/conf/external_actionhandlers/',
			[
				'config/counting-rhyme-actionhandler.conf',
				'config/counting-rhyme-actionhandler-log.conf'
			]
		),
		(
			'/opt/autopilot/conf/external_actionhandlers/capabilities/',
			[
				'config/capabilities/counting-rhyme-actionhandler.xml',
				'config/capabilities/counting-rhyme-actionhandler.yaml'
			]
		),
		(
			'/etc/init.d/', ['etc/init.d/autopilot-counting-rhyme-actionhandler']
		)
	]
)
