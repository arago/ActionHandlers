### OpenSSL

When no Active Directory and no Windows Certification Authority are present, we can generate the certificates on the AutoPilot machine (or any other Unix/Linux server) using the OpenSSL command line utility, effectively creating our own certification authority.

Please make sure that OpenSSL is installed on your Linux server. If not, install it using the system's package manager (apt, yum, …)

OpenSSL can be used in a great number of ways, covering almost any scenario. Unfortunately, this means that configuring it can be a very complex task. Therefore in this guide, we will use our own, minimal configuration file. It can be obtained here: [openssl-ap.cnf](resources/openssl-ap.cnf).

First, create a new directory on your Linux machine, secure it and change your working directory to its path:

```bash
mkdir -m700 autopilot-ca; cd autopilot-ca
```

Download the openssl configuration file and put it into the same directory.

#### Creating the root certificate

To create the root certificate, first create a new private key:

```bash
touch root.key && chmod 600 root.key
openssl genrsa -aes256 -out root.key 2048
chmod 400 root.key
```

You will be prompted for a password. **This password will protect the private key of your root certificate, so choose a strong one and make sure it does not get lost.** If someone was able to obtain this private key, he could sign his own certificates in your name, basically enabling him to break into any system that trusts your root certificate. In our scenario, this would be all your servers. The password-protected key will be stored in the file *root.key* and the permissions of that file will set so that only you can read it.

After you have a private key for your root certificate, create the certificate itself. Replace `<country_code>`, `<state>`, `<city>`, `<company>` and `<department>` with the respective values (they may contain whitespace). You will be prompted for your private key's password.

```bash
touch root.crt && chmod 600 root.crt
openssl req -x509 -new -nodes -extensions v3_ca -key root.key -days 1024 -out root.crt -sha256 -subj "/C=<country_code>/ST=<state>/L=<city>/O=<company>/OU=<department>/CN=My AutoPilot root CA"
chmod 400 root.crt
```

The new certificate will be stored in the file *root.crt*. Again, the file will only be readable by yourself. At this point, you should **create one or several backups** of both your *root.key* and your *root.crt*.

#### Creating the server certificate(s)

In the next step, we have to create a server key and certificate for each target machine. Because they will basically all look the same, we will use a shell script to process a list of server names. First, create a file called *servers.txt* with one hostname per line. It should look like that:

```bash
server1.example.com
server2.example.com
…
```

Then create a new subdirectoy *servers* where we will store the created keys and certificates:

```bash
mkdir -m700 servers
```

Finally, download the script [create-server-certs.sh](resources/create-server-certs.sh), place it in your current working directory *autopilot-ca* and make it executable:

```bash
chmod 700 create-server-certs.sh
```

Then call the script with the list of servers and the directory to store the generated certificates. Because we will import these certificates on Windows machines, both the key and the certificate will be stored in the same *.pfx* file.

The script will prompt you for the pass phrase of the private root key and a new export password that will be used to protect the created certificates. You will need the export password when you import the files on Windows. To keep it simple, all generated server certificates will have the same password, as it is only needed to securely transmit them to their destination server.

```bash
./create-server-certs.sh -c openssl-ap.cnf -r root.crt -k root.key -d servers -u C=your_country_code -u ST='your_state' -u L='your location e.g. city' -u O='your organisation e.g. company name' -u OU='your organisational unit e.g. department' servers.txt
Enter pass phrase for root.key: *******
Enter export password for server certificates: ****
Verifying - Enter export password for server certificates: ****
certificate saved as servers/server1.example.com.pfx
certificate saved as servers/server2.example.com.pfx
…
all done
```

#### Importing the certificates on the Windows machines

Now the certificates need to be transferred to the Windows machines. **Each machines needs a pair of two certificates**:

1. The root certificate *root.crt*, without the private key.
2. The server certificate *servers/hostname.domain.pfx* with both the certificate and the private key, password–protected

## WinRM configuration

In order to setup Windows for secure remote access, the WinRM service needs to be enabled, a SSL listener has to be created and the client certificate we're going to use has to be mapped to a local user account.

### Importing the certificates

#### Open the Microsoft Management Console (mmc.exe) and add the certificates snap-in for the local machine:

Screencast:

[![Click to open the screencast](https://img.youtube.com/vi/luhwmfmTOYY/0.jpg)](https://www.youtube.com/watch?v=luhwmfmTOYY)

#### Import the root certificate into the 'Trusted Root Certification Authorities' store:

Screencast:

[![Click to open the screencast](https://img.youtube.com/vi/8RvIkygImlk/0.jpg)](https://www.youtube.com/watch?v=8RvIkygImlk)

#### Import the server certificate into the 'Personal' store:

You will need to enter the export password you chose earlier.

Screencast:

[![Click to open the screencast](https://img.youtube.com/vi/l2N9QMbL4ck/0.jpg)](https://www.youtube.com/watch?v=l2N9QMbL4ck)


### Enable and start the WinRM service

The commands in this and the following sections are mostly PowerShell commands. The only exception is the netsh command. It can be executed in a PowerShell window nonetheless.

```powershell
Set-Service winrm -StartupType Automatic -Status Running
```

### Creating a SSL listener for WinRM

Find the thumbprint of your server certificate:

```powershell
Get-ChildItem cert:\LocalMachine\My

Thumbprint                                Subject
----------                                -------
7E2E1055471FFC90DABCAEBE24C3196C15201983  CN=srv1.adlab.loc, OU=Sales, O=arago GmbH, L=Frankfurt am Main, S=Hessen, C=DE
```

Create the new HTTPS listener. Replace `<your_thumbprint>` by the actual thumbprint of your server certificate.


```powershell
New-WSManInstance winrm/config/Listener -SelectorSet @{Address="*";Transport="HTTPS"} -ValueSet @{CertificateThumbprint="<your_thumbprint>"}
```

### Add a firewall exception for port 5986

```bat
netsh advfirewall firewall add rule name="Windows remote management HTTPS inbound" protocol=TCP dir=in localport=5986 action=allow
```

### Register the configurations for PowerShell sessions


```powershell
Register-PSSessionConfiguration -Name Microsoft.PowerShell -Force
Register-PSSessionConfiguration -Name Microsoft.PowerShell.Workflow -Force
```

If you are on a 64 bit operating system (you most certainly are), also execute the following command:

```powershell
Register-PSSessionConfiguration Microsoft.Powershell32 -processorarchitecture x86 -force
```
