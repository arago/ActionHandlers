#!/usr/bin/env python
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

distutils.core.setup(
	name = "arago-pyconnectit-connectors-snow",
	version = "0.3",
	author = "Marcus Klemm",
	author_email = "mklemm@arago.de",
	description = ("pyconnectit handlers for ServiceNow"),
	license = "MIT",
	url = "http://www.arago.de",
	long_description="pyconnectit handlers for ServiceNow",
	classifiers=[
		"Development Status :: 5 - Production/Stable",
		"Topic :: Utilities",
		"License :: OSI Approved :: MIT License",
	],
	packages=['arago.pyconnectit.connectors.snow.handlers.open_snow_ticket']
)
