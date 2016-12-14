# pyactionhandler library
## Installation

Currently, the ActionHandlers implemented using this library must be installed on the HIRO Engine node (in a multi-node-installation). At this point, the installation process is manual. We're working on a setup script.

### Installation of required packages and python modules

The `pyactionhandler` library and the included sample ActionHandlers make heavy use of some python modules provided by third-parties. All of them are released under an open source license. Please refer to the modules' documentation to learn more about their respective licenses.

The `pyactionhandler` library itself and the included sample ActionHandlers are released under the MIT license (see topic *License for ActionHandlers (MIT)* at the end of this document).

#### Get packages and python modules from the internet

Please follow these steps in order to download and install all requirements from the internet. If you want to do an offline installation, please see section *Offline installation using the included packages* below.

##### System packages and python modules
1. Install the IUS repository by downloading and installing the appropriate package from https://ius.io/GettingStarted/
2. Install the following packages (and their dependencies):

  | Package       | will be fetched from  |
  | ------------- | --------------------- |
  | libxslt       | standard repositories |
  | python35u     | IUS repository        |
  | python35u-pip | IUS repository        |
  | redis32u      | IUS repository        |

  The `redis32u` package is needed by the included Ayehu Eyeshare ActionHandler. It is not needed in general.

3. Install the required python modules by executing: `pip3.5 install virtualenv wheel`

##### Additionally required python modules

The remaining python modules will not be installed on a system level but into a virtual python environment.

1. Create a new virtual python 3.5 environment: `virtualenv -p python3.5 /opt/autopilot/engine/python-actionhandler`
2. Switch to the newly created virtualenv: `source /opt/autopilot/engine/python-actionhandler/bin/activate`. Your command prompt will change, indicating the environment you're in. Additionally, while you're in this environment, you can execute `python3.5` by simply typing `python` and `pip3.5` by simply typing `pip`. To leave the environment, type `deactivate`.
3. Install the following python modules (and their dependencies) inside the virtualenv:

  | Module     | needed by                    | purpose                                           |
  | ---------- | ---------------------------- | ------------------------------------------------- |
  | setuptools | build process                | packaging                                         |
  | gevent     | pyactionhandler library      | pseudo-threads for memory efficent concurrency    |
  | zmq        | pyactionhandler library      | communication with the HIRO Engine                |
  | protobuf   | pyactionhandler library      | communication with the HIRO Engine                |
  | docopt     | ActionHandler executables    | parsing command line options                      |
  | requests   | pygraphit library            | making HTTP(S) calls to REST APIs                 |
  | zeep       | Ayehu Eyeshare ActionHandler | making SOAP calls to a WebService                 |
  | redis      | Ayehu Eyeshare ActionHandler | Independent key-value store                       |
  | falcon     | Ayehu Eyeshare ActionHandler | implement the REST API for the callback mechanism |
  | pywinrm    | WinRM ActionHandler          | executing commands remotely on Windows machines   |
  
  Install by executing: `pip install zeep redis pywinrm gevent requests falcon protobuf zmq docopt setuptools`

4. Download and Install the pyactionhandler module and sample ActionHandlers:

```
git clone https://github.com/arago/ActionHandlers.git
cd ActionHandlers/python-actionhandler
pip install .
```

### Installation of the init scripts for the sample ActionHandlers
1. Copy the init scripts to the system's `/etc/init.d` directory and make them executable:

   ```
   cp etc/init.d/autopilot-ayehu-actionhandler /etc/init.d/
   cp etc/init.d/autopilot-winrm-actionhandler /etc/init.d/
   cp etc/init.d/autopilot-counting-actionhandler /etc/init.d/
   chmod a+x /etc/init.d/autopilot-*-actionhandler
   ```
   
2. Add them to the usual runlevels so they start up automatically after a reboot:

   ```
   chkconfig --add autopilot-winrm-actionhandler
   chkconfig --add autopilot-ayehu-actionhandler
   chkconfig --add autopilot-counting-actionhandler
   ```
   
3. The Ayehu Eyeshare ActionHandler needs the redis datastore to be running. Copy over the included config file and start redis as well:

   ```
   cp -f etc/redis.conf /etc/
   chkconfig redis on
   service redis start
   service redis status
   ```

### Configuration of the ActionHandlers
1. Copy the included config files to /opt/autopilot/conf/pyactionhandler:

   ```
   mkdir /opt/autopilot/conf/pyactionhandler
   cp config/* /opt/autopilot/conf/pyactionhandler/
   chown -R arago:arago /opt/autopilot/conf/pyactionhandler
   ```
   
   **Without this step, the ActionHandlers will not start up, properly!**
   
2. Edit the config files to set the required parameters.

   **This section will be expanded, soon. If you just want to try the sample 'CountingRhyme' ActionHandler, you don't need to change anything.**

3. The "background mode" of the Ayehu Eyeshare ActionHandler updates AutomationIssues by calling the GraphIT REST API. In order to do that, it has to request an authentication token from the WSO2 identity server. Additionally, a new security policy has to be imported into WSO2 that allows the ActionHandler to write to the graph database. The documentation for these steps is not finished, yet. In the meantime, please refer to the temporary howto in the "WSO2 config" folder for details.

   **Without this step, the background mode of the Ayehu Eyeshare ActionHandler will not work!**

### Configuration of the HIRO Engine
#### For HIRO versions 5.2 – 5.3.1

Add the following sections to your /opt/autopilot/aae.yaml for all the ActionHandlers you want to use:

```
ActionHandlers:
  ActionHandler:
  - URL: tcp://127.0.0.1:7289
    SubscribeURL: ''
    CapabilityXML: /opt/autopilot/conf/pyactionhandler/WinRMActionHandler.xml
    RequestTimeout: 60
  - URL: tcp://127.0.0.1:7290
    SubscribeURL: ''
    CapabilityXML: /opt/autopilot/conf/pyactionhandler/AyehuActionHandler.xml
    RequestTimeout: 60
  - URL: tcp://127.0.0.1:7291
    SubscribeURL: ''
    CapabilityXML: /opt/autopilot/conf/pyactionhandler/CountingRhymeActionHandler.xml
    RequestTimeout: 60
```

To apply the new setting, restart the HIRO Engine: `service autopilot-engine restart`

#### For HIRO version 5.4 and up

With HIRO version 5.4, the format of the Capability description file changed from XML to YAML:

```
ActionHandlers:
  ActionHandler:
  - URL: tcp://127.0.0.1:7289
    SubscribeURL: ''
    CapabilityYAML: /opt/autopilot/conf/pyactionhandler/WinRMActionHandler.yaml
    RequestTimeout: 60
  - URL: tcp://127.0.0.1:7290
    SubscribeURL: ''
    CapabilityYAML: /opt/autopilot/conf/pyactionhandler/AyehuActionHandler.yaml
    RequestTimeout: 60
  - URL: tcp://127.0.0.1:7291
    SubscribeURL: ''
    CapabilityYAML: /opt/autopilot/conf/pyactionhandler/CountingRhymeActionHandler.yaml
    RequestTimeout: 60
```

To apply the new setting, restart the HIRO Engine: `service autopilot-engine restart`

### Starting the ActionHandlers

The ActionHandler will run as Unix daemons and log to `/var/log/autopilot/engine/`

```
service autopilot-winrm-actionhandler start
service autopilot-winrm-actionhandler status

service autopilot-ayehu-actionhandler start
service autopilot-ayehu-actionhandler status

service autopilot-counting-actionhandler start
service autopilot-counting-actionhandler status
```

## Developing your own Actionhandler

A complete documentation is still missing. For the time being, please have a look at `bin/autopilot-counting-rhyme-actionhandler.py`. The whole, documented python code for this sample ActionHandler is in this single file.

## License for Action Handlers (MIT)

Copyright (c) 2016 arago GmbH

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
