Title:   A simple WinRM-based ActionHandler for Windows nodes
Author:  Marcus Klemm
Date:    December 7, 2015  

# Simple ActionHandler to execute commands on Windows machines using WinRM

In this example I will show you how to configure the Generic ActionHandler to access Microsoft Windows machines using the WinRM protocol. To achieve this, I will utilize a WinRM client written in the Go language. It can be found here: [github.com/masterzen/winrm/tree/master/winrm](https://github.com/masterzen/winrm/tree/master/winrm)

Parts of this guide are about building everything from scratch. The winrm and winrm-powershell binaries are also included in the downloads folder, if you don't want to build them on your own, just skip this step.

## Disclaimer

Do not use this in production! The client I use allows only unencrypted traffic and I will put the password in the AutoPilot config file. This is only a quick hack to use in a test lab.

## Building the winrm client and the winrm-powershell wrapper

If you have an all-in-one installation of AutoPilot, log into the AutoPilot machine. In a multi-node-setup, log into the engine node.

First, install the EPEL repository and git: `sudo yum install epel-release git`

Then, install the Go compiler: `sudo yum install golang`

Create a directory for the Go environment: `mkdir golang`

Setup the GOPATH environment variable and add its bin subdirectory to your path:

```nohighlight
export GOPATH=~/golang
export PATH=$PATH:${GOPATH//://bin:}/bin
```

Download and build the "gox" Go cross-compiler: `go get github.com/mitchellh/gox`

Download and build the winrm client: `go get github.com/masterzen/winrm`

Download and build the winrm-powershell wrapper: `go get github.com/mefellows/winrm-powershell`

Finally, copy the winrm and winrm-powershell binaries to your `/usr/bin` directory (or somewhere else in the user arago's `$PATH`):

```nohighlight
sudo cp -ax golang/bin/winrm /usr/bin/
sudo cp -ax golang/bin/winrm-powershell /usr/bin/
```

## Preparing the target system(s)

On the target Windows machines, open a cmd.exe command line using "Run as Administrator" and execute the following commands:

```nohighlight
winrm quickconfig
winrm set winrm/config/service/Auth @{Basic="true"}
winrm set winrm/config/service @{AllowUnencrypted="true"}
winrm set winrm/config/winrs @{MaxMemoryPerShellMB="1024"}
```

Your network connection has to be a "work" network.

## Testing the remote access

On the AutoPilot machine, the next command should succeed and you should get a listing of the Windows user’s home directory:

```nohighlight
winrm -hostname <dns_name_of_windows_machine> -username <a_local_windows_user> -password <password> dir
```

To test the winrm-powershell wrapper, execute the following:

```nohighlight
winrm-powershell -hostname <dns_name_of_windows_machine> -username <a_local_windows_user> -password <password> Get-Date
```

## Configuring the Generic ActionHandler:

Add the following to your `/opt/autopilot/conf/aae.yaml` in the GenericHandler section:

```yaml
# winrm based remote execution
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
    Description: "execute command on remote host"
    Interpreter: winrm -hostname ${Hostname} -username ${User} -password ${Password} "$(<${TEMPFILE})" | sed '1 s/\xEF\xBB\xBF//' | dos2unix
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
    Description: "execute command on remote host"
    Interpreter: winrm-powershell -hostname ${Hostname} -username ${User} -password ${Password} "$(<${TEMPFILE})" | sed '1 s/\xEF\xBB\xBF//' | dos2unix
	Command: ${Command}
    Parameter:
    - Name: Command
      Description: "Powershell command to execute"
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

##Executables 

If you are looking for the mentioned 3rd party executables and files required to set this up, please contact us at autopilot-support@arago.de .
