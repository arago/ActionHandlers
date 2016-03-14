# WinRM ActionHandler with SSL encryption and Certificate Authentication

## Overview
This ActionHandler allows the remote execution of both cmd.exe and Powershell commands on Windows targets via the WinRM protocol. It uses SSL encryption and authentication is achieved by a SSL client certificate, so there is no need to store passwords or password hashes in AutoPilot.

There are various ways to distribute the necessary certificates to the target machines. In this guide, I will cover both the use of an Active Directory Certification infrastructure as well as the usage of OpenSSL.

## Certification infrastructure

To connect to a windows machine using WinRM with SSL encryption and client certificate authentication, two certificates need to be present on the target machine:

1. A server certificate that identifies the machine.
2. A trusted client certificate to identify the user account that will be used to connect.

Both certificates have to be in the same trust chain, i.e. be signed by the same root authority or by intermediate certification authories that themselves are both certified by the same root CA. The certificate of this root CA has also to be present in the list of trusted CAs.

### Active Directory and Windows Enterprise Certification Authority

**This part of the guide is not yet finished and will be updated soon.**

If present, an Active Directory Domain Service in conjuction with a Microsoft Windows Enterprise Certification Authority can be used to generate and distribute the necessary SSL certificates to the target machines. This way, even a large number of servers can be automatically configured by Active Directory group policies.

In a properly set up Windows domain with an Enterprise CA, all servers that are part of the domain automatically receive a server certificate and have the signing Enterprise CA in their list of trusted root CAs. All we need to do is to create the client certificate and distribute it via an additional group policy.

### OpenSSL

When no Active Directory and no Windows Certification Authority are present, we can generate the certificates on the AutoPilot machine (or any other Unix/Linux server) using the OpenSSL command line utility, effectively creating our own certification authority.

Please make sure that OpenSSL is installed on your Linux server. If not, install it using the system's package manager (apt, yum, …)

OpenSSL can be used in a great number of ways, covering almost any scenario. Unfortunately, this means that configuring it can be a very complex task. Therefore in this guide, we will use our own, minimal configuration file. It can be obtained here: [openssl-ap.cnf](conf/openssl-ap.cnf).

First, create a new directory on your Linux machine, secure it and change your working directory to its path:

```
mkdir -m700 autopilot-ca; cd autopilot-ca
```

Download the openssl configuration file and put it into the same directory.

#### Creating the root certificate

To create the root certificate, first create a new private key:

```
touch root.key; chmod 600 root.key
openssl genrsa -aes256 -out root.key 2048
chmod 400 root.key
```

You will be prompted for a password. **This password will protect the private key of your root certificate, so choose a strong one and make sure it does not get lost.** If someone was able to obtain this private key, he could sign his own certificates in your name, basically enabling him to break into any system that trusts your root certificate. In our scenario, this would be all your servers. The password-protected key will be stored in the file *root.key* and the permissions of that file will set so that only you can read it.

After you have a private key for your root certificate, create the certificate itself. You will be prompted for your private key's password and some additional information that will be stored in the certificate. Then asked for a 'Common Name', enter 'My AutoPilot root CA'.

```
touch root.crt; chmod 600 root.crt
openssl -config openssl-ap.cnf req -x509 -new -nodes -extensions v3_ca -key root.key -days 1024 -out root.crt -sha512
chmod 400 root.crt
```

The new certificate will be stored in the file *root.crt*. Again, the file will only be readable by yourself. At this point, you should **create one or several backups** of both your *root.key* and your *root.crt*.

#### Creating the server certificate(s)

In the next step, we have to create a server key and certificate for each target machine. Because they will basically all look the same, we will use a shell script to process a list of server names. First, create a file called *servers.txt* with one hostname per line. It should look like that:

```
server1.example.com
server2.example.com
…
```

Then create a new subdirectoy *servers* where we will store the created keys and certificates:

```
mkdir -m700 servers
```

Finally, download the script [create-server-certs.sh](scripts/create-server-certs.sh), place it in your current working directory *autopilot-ca* and make it executable:

```
chmod 700 create-server-certs.sh
```

Then call the script with the list of servers and the directory to store the generated certificates. Because we will import these certificates on Windows machines, both the key and the certificate will be stored in the same *.pfx* file.

The script will prompt you for the password of the private root key and a new password that will be used to protect the created certificates. You will need the second password when you import the files on Windows. To keep it simple, all generated server certificates will have the same password, as it is only needed to securely transmit them to their destination server.

```
./create-server-certs.sh -c openssl-ap.cnf -a root.crt -k root.key -i servers.txt -d servers/
Enter pass phrase for root.key: *****
Enter pass phrase for server certificates:
Verifying - Enter pass phrase for server certificates:
certificate saved as servers/server1.example.com.pfx
certificate saved as servers/server2.example.com.pfx
…
all done
```

#### Creating the client certificate

Last step is to create a client certificate for AutoPilot:

```
touch autopilot.key autopilot.pem; chmod 600 autopilot.key autopilot.pem
openssl -config openssl-ap.cnf genrsa -des3 -out autopilot.key 4096
chmod 400 autopilot.key
openssl -config openssl-ap.cnf req -new -key autopilot.key -out autopilot.csr
openssl -config openssl-ap.cnf x509 -req -days 365 -in autopilot.csr -CA root.crt -CAkey root.key -CAcreateserial -out autopilot.crt
chmod 400 autopilot.pem
```
This will create two files, *autopilot.key* and *autopilot.crt*. The *.crt* certificate file needs to be copied to each server. It does not need password protection as it only contains the (public) certificate part.

The *.key* file is more critical, as it contains the private key of the client certificate. Whoever gets hold of this file will be able to log into your servers, so be very careful.

#### Importing the certificates on the Windows machines

Now the certificates need to be transferred to the Windows machines. Each machines needs a set of three certificates:

1. The root certificate *root.crt*, without the private key.
2. The server certificate *servers/hostname.domain.pfx* with both the certificate and the private key, password–protected
3. The client certificate *autopilot.crt*, without the private key.

## WinRM configuration

### WinRM service

### SSL listener

### Certificate mapping

## AutoPilot ActionHandler configuration

## Usage in Knowledge Items