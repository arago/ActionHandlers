#!/usr/bin/env python
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

distutils.core.setup(
	name = "arago-pyconnectit-common-rest",
	version = "2.2",
	author = "Marcus Klemm",
	author_email = "mklemm@arago.de",
	description = ("pyconnectit REST interface"),
	license = "MIT",
	url = "http://www.arago.de",
	long_description="pyconnectit REST interface",
	classifiers=[
		"Development Status :: 5 - Production/Stable",
		"Topic :: Utilities",
		"License :: OSI Approved :: MIT License",
	],
	packages=['arago.pyconnectit.common.rest']
)
