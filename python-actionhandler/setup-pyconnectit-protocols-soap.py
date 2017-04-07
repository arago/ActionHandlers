#!/usr/bin/env python
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

distutils.core.setup(
	name = "arago-pyconnectit-protocols-soap",
	version = "2.1",
	author = "Marcus Klemm",
	author_email = "mklemm@arago.de",
	description = ("pyconnectit plugins to work with SOAP"),
	license = "MIT",
	url = "http://www.arago.de",
	long_description="pyconnectit plugins to work with SOAP",
	classifiers=[
		"Development Status :: 5 - Production/Stable",
		"Topic :: Utilities",
		"License :: OSI Approved :: MIT License",
	],
	packages=['arago.pyconnectit.protocols.soap',
			  'arago.pyconnectit.protocols.soap.plugins.soap_logger'
	]
)
