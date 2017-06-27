#!/usr/bin/env python
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

distutils.core.setup(
	name = "arago-pyconnectit-connectors-common-base",
	version = "2.2",
	author = "Marcus Klemm",
	author_email = "mklemm@arago.de",
	description = ("common pyconnectit handlers"),
	license = "MIT",
	url = "http://www.arago.de",
	long_description="common pyconnectit handlers",
	classifiers=[
		"Development Status :: 5 - Production/Stable",
		"Topic :: Utilities",
		"License :: OSI Approved :: MIT License",
	],
	packages=['arago.pyconnectit.connectors.common',
			  'arago.pyconnectit.connectors.common.handlers.base_handler',
			  'arago.pyconnectit.connectors.common.handlers.soap_handler',
			  'arago.pyconnectit.connectors.common.handlers.log_comments',
			  'arago.pyconnectit.connectors.common.handlers.log_status_change',
			  'arago.pyconnectit.connectors.common.handlers.watch_new',
			  'arago.pyconnectit.connectors.common.no_issue_watcher'
	]
)
