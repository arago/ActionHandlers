import os
from setuptools import setup

# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "pyactionhandler",
    version = "0.9",
    author = "Marcus Klemm",
    author_email = "mklemm@arago.de",
    description = ("An demonstration of how to create, document, and publish "
                                   "to the cheese shop a5 pypi.org."),
    license = "MIT",
    keywords = "actionhandler autopilot",
    url = "http://www.arago.de",
    packages=['pyactionhandler',
			  'pyactionhandler.ayehu',
			  'pyactionhandler.common',
			  'pyactionhandler.common.pmp',
			  'pyactionhandler.protobuf',
			  'pyactionhandler.winrm'],
	install_requires=['gevent', 'zeep==0.5.0', 'pywinrm', 'redis', 'falcon', 'docopt', 'zmq', 'protobuf<=3.0.0'],
	scripts=['bin/autopilot-ayehu-actionhandler.py',
			 'bin/autopilot-winrm-actionhandler.py'],
    long_description=read('README'),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Topic :: Utilities",
        "License :: OSI Approved :: MIT License",
    ],
)
