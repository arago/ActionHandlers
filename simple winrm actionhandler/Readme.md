# Simple ActionHandler to execute commands on Windows machines using WinRM

## Important:

This ActionHandler used to utilize the WinRM client written in the Go language that can be found here: [github.com/masterzen/winrm/tree/master/winrm](https://github.com/masterzen/winrm/tree/master/winrm). Now that our Python client has all the features the Go client had, this has been deprecated. If, for some reason, you want to continue using the Go client, the respective documentation can be found in the winrm-legacy branch.

## Disclaimer

Do not use this in production! The configuration shown here puts both username and password unencrypted into the AutoPilot config file. This is okay when you're in a lab environment and want to do some quick tests. For production, use the config from "winrm--with-certificate-authority", which uses SSL certificates.

## Preparing the target system(s)

On the target Windows machines, open a cmd.exe command line using "Run as Administrator" and execute the following commands:

```nohighlight
winrm quickconfig
winrm set winrm/config/service/Auth @{Basic="true"}
winrm set winrm/config/service @{AllowUnencrypted="true"}
winrm set winrm/config/winrs @{MaxMemoryPerShellMB="1024"}
```

Your network connection has to be a "work" network.

## Installing python >= 2.7.9

CentOS 6.7 comes with python 2.6.6 pre-installed but the pywinrm library used by this ActionHandler requires python >= 2.7.9. The [IUS Community Project](https://ius.io) provides a repository with the latest release. You can find more information on their [Getting Started](https://ius.io/GettingStarted/) page.

On the AutoPilot machine, download and install the repository. Afterwards, install python 2.7 and some additional python modules:

```bash
curl -L 'https://centos6.iuscommunity.org/ius-release.rpm' >ius-release.rpm
yum -y localinstall ius-release.rpm
yum -y install python27 python27-pip
pip2.7 install isodate xmltodict pytest pytest-cov pytest-pep8 mock pywinrm==0.1.1 docopt schema
```

## Installing the Actionhandler

Download the WinRM client [winrm-client.py](../winrm-with-certificate-authority/resources/winrm-client.py) and put it into `/opt/autopilot/bin/` on the AutoPilot engine node.

**It is important to really *download* the file, not copy'n'paste it's content. So please click on on "Raw" and save the page.**

## Testing the remote access

On the AutoPilot machine, the next command should succeed and you should get a listing of the Windows user’s home directory:

```bash
python2.7 /opt/autopilot/bin/winrm-client.py cmd <dns_name_of_windows_machine> --creds <a_local_windows_user> <password> --nossl -p 5985 <(echo 'dir')
```

To test the execution of PowerShell commands, execute the following:

```bash
python2.7 /opt/autopilot/bin/winrm-client.py ps <dns_name_of_windows_machine> --creds <a_local_windows_user> <password> --nossl -p 5985 <(echo 'Get-ChildItem')
```

## Configuring the Generic ActionHandler:

Add the following to your `/opt/autopilot/conf/aae.yaml` in the GenericHandler section:

```yaml
- Applicability:
    Priority: 60
    ModelFilter:
      Var:
        Name: NodeType
        Mode: string
        Value: Machine
      Var:
        Name: MachineClass
        Mode: string
        Value: Windows
  Capability:
  - Name: ExecuteCommand
    Description: "execute cmd.exe command on remote host"
    Interpreter: python2.7 /opt/autopilot/bin/winrm-client.py cmd ${Hostname} --creds ${User} ${Password} --nossl -p 5985 ${TEMPFILE}
    Command: ${Command}
    Parameter:
    - Name: Command
      Description: "DOS command to execute"
      Mandatory: true
    - Name: Hostname
      Description: "host to execute command on"
      Mandatory: true
    - Name: User
      Description: "target user"
      Default: <default_windows_user>
    - Name: Password
      Description: "target user's password"
      Default: <password_of_default_windows_user>
  - Name: ExecutePowershell
    Description: "execute cmd.exe command on remote host"
    Interpreter: python2.7 /opt/autopilot/bin/winrm-client.py ps ${Hostname} --creds ${User} ${Password} --nossl -p 5985 ${TEMPFILE}
    Command: ${Command}
    Parameter:
    - Name: Command
      Description: "PowerShell command to execute"
      Mandatory: true
    - Name: Hostname
      Description: "host to execute command on"
      Mandatory: true
    - Name: User
      Description: "target user"
      Default: <default_windows_user>
    - Name: Password
      Description: "target user's password"
      Default: <password_of_default_windows_user>
```

Restart the AutoPilot Engine: `sudo /etc/init.d/autopilot-engine restart`

After that, your KIs should be able to execute DOS commands on the Windows targets using `<Action Capability="ExecuteCommand">` and Powershell commands using `<Action Capability="ExecutePowershell">`
