import sys
import base64
import winrm
import xml.etree.ElementTree as ET
import codecs
import re
from docopt import docopt
from schema import Schema, Or, And, Optional, Use
import schema

def psesc(string):
    return string.replace('@\'', '@`\'').replace('\'@', '`\'@')

class Session(winrm.Session):

    def run_ps(self, script):
        """base64 encodes a Powershell script and executes the powershell encoded script command"""

        # must use utf16 little endian on windows
        base64_script = base64.b64encode(script.encode("utf_16_le"))
        rs = self.run_cmd("mode con: cols=1024 & powershell -encodedcommand %s" % (base64_script))
        print rs.std_err
        #if len(rs.std_err):
            # if there was an error message, clean it it up and make it human readable
            #rs.std_err = self.clean_error_msg(rs.std_err)
        return rs
    
class certSession(Session):
    def __init__(self, endpoint, auth, validation='ignore'):
        cert, key = auth
        self.protocol = winrm.Protocol(
            endpoint=endpoint,
            transport='ssl',
            cert_pem=cert,
            cert_key_pem=key,
            server_cert_validation=validation
        )
class basicSession(Session):
    def __init__(self, endpoint, auth, transport='ssl', validation='ignore'):
        username, password = auth
        self.protocol = winrm.Protocol(
            endpoint=endpoint,
            transport=transport,
            username=username,
            password=password,
            server_cert_validation=validation
        )


class Script(object):
    psWrapper=unicode("""\
$OutputEncoding=[console]::OutputEncoding=[console]::InputEncoding=[system.text.encoding]::GetEncoding([System.Text.Encoding]::Default.CodePage)
@'
{script}'@ | powershell - 2>&1 | %{{$e=@("psout","pserr")[[byte]($_.GetType().Name -eq "ErrorRecord")];return "<$e><![CDATA[$(([string]$_).TrimEnd(" `r`n"))]]></$e>"}}
exit $LastExitCode
""")
    cmdWrapper=unicode("""\
$t = [IO.Path]::GetTempFileName() | ren -NewName {{ $_ -replace 'tmp$', 'bat' }} -PassThru
@'
{script}'@ | out-file -encoding "OEM" $t
& cmd.exe /q /c $t 2>&1 | %{{$e=@("psout","pserr")[[byte]($_.GetType().Name -eq "ErrorRecord")];return "<$e><![CDATA[$(([string]$_).TrimEnd(" `r`n"))]]></$e>"}}
rm $t
exit $LastExitCode
""")
    def __init__(self, script, interpreter):
        self.interpreter=interpreter
        if interpreter=='cmd': self.wrapper=self.cmdWrapper
        elif interpreter=='ps': self.wrapper=self.psWrapper
        else: pass
        self.script = script if script[-1] == "\n" else script + "\n"
        self.result=None
            
    def run(self, Session):
        self.rs=Session.run_ps(
            self.wrapper.format(
                script=psesc(self.script
                    )))
        
    def print_output(self):
        xml = "<root>\n" + self.rs.std_out.decode('cp850') + "</root>"
        root = ET.fromstring(xml.encode('utf8'))
        nodes = root.findall("./*")
        for s in nodes:
            if s.tag == 'pserr':
                print >>sys.stderr, s.text or ''
            elif s.tag == 'psout':
                print >>sys.stdout, s.text or ''

### MAIN ###

sys.stdout = codecs.getwriter('utf8')(sys.stdout)
hostnameRegex = '(?=^.{1,253}$)(^(((?!-)[a-zA-Z0-9-]{1,63}(?<!-))|((?!-)[a-zA-Z0-9-]{1,63}(?<!-)\.)+[a-zA-Z]{2,63})$)'
ipv4Regex = '(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)'
portnumRegex = '^[0-9]+$'

usage="""
Usage:
  winrm-client [options] (cmd|ps|wql) <target> --certs <certificate> <keyfile> <script>
  winrm-client [options] (cmd|ps|wql) <target> --creds <username> <password> [--nossl] <script>
  winrm-client [options] (cmd|ps|wql) <target> --kinit <realm> <keytab> [--nossl] <script>
  winrm-client --help

Commands:
  cmd                      Execute DOS command or batch file
  ps                       Execute Powershell command or script
  wql                      Execute SQL for WMI query (not yet implemented)

Authentication:
  -c --certs               Authenticate using SSL certificates
  -u --creds               Authenticate using username and password
  -k --kinit               Authenticate using Kerberos / Active Directory (not yet implemented)

Arguments:
  <certificate>            Path to the certificate file
  <keyfile>                Path to the certificate's keyfile
  <username>               account name of a local user account on the target machine
  <password>               password of the local user account
  <realm>                  Name of the Kerberos realm / Active Directory domain
  <keytab>                 Path of the Kerberos keytab
  <target>                 DNS name or IP address of the target machine
  <script>                 Path to the file containing the commands

Options:
  -p <port> --port=<port>  The network port to use [default: 5986]
  -n --nossl               Don't use SSL encryption (not possible if using SSL certificate
                           authentication)
  -h --help                Print this help message and exit
"""

if __name__ == '__main__':
    s = Schema({"<target>":     And(str, Or(lambda hn: re.compile(hostnameRegex).match(hn),
                                              lambda ip: re.compile(ipv4Regex).match(ip)),
                                      error='<target> has to be a valid hostname, FQDN or IPv4 address'),
                "<certificate>":  Or(None, Use(open), error='<certificate> has to be a readable file'),
                "<keyfile>":      Or(None, Use(open), error='<keyfile> has to be a readable file'),
                "<username>":     Or(None, str),
                "<password>":     Or(None, str),
                "<realm>":        Or(None, str),
                "<keytab>":       Or(None, Use(open), error='<keytab> has to be a readable file'),
                "<script>":       Or('-', Use(open), error='<script> has to be a readable file'),
                "--port":         Or(None, And(str, lambda prt: re.compile(portnumRegex).match(prt)),
                                     error='<port> must be numeric'),
                Optional(object): object # suppress validation errors for additional elements
    })
    
    try:
        args = s.validate(docopt(usage))
    except schema.SchemaError as e:
        print >>sys.stderr, usage
        print >>sys.stderr, e
        sys.exit(255)

    if args['--certs']:
        """Authenticate using a client certificate, transport is always ssl."""
        mySession = certSession(
            endpoint="https://{hostname}:{port}/wsman".format(hostname=args['<target>'],
                                                              port=args['--port']),
            auth=(args['<certificate>'].name, args['<keyfile>'].name))
        
    elif args['--creds']:
        """Authenticate using credentials, default is to use ssl transport but this can be overridden."""
        mySession = basicSession(
            endpoint="{proto}://{hostname}:{port}/wsman".format(proto = 'http' if args['--nossl'] else 'https',
                                                                hostname=args['<target>'],
                                                                port=args['--port']),
            transport = 'plaintext' if args['--nossl'] else 'ssl',
            auth=(args['<username>'], args['<password>']))

    elif args['--kinit']:
        """Athenticate using Kerberos, not yet implemented!"""
        print >>sys.stderr, "Kerberos authentication is not yet implemented"
        sys.exit(255)
        
    try:
        """Execute script on target machine, get results and print them to their respective channels."""
        myScript=Script(script=args['<script>'].read().decode('utf-8'),
                        interpreter = 'cmd' if args['cmd']
                                 else 'ps'  if args['ps']
                                 else 'wql' if args['wql']
                                 else None
        )
        myScript.run(mySession)
        myScript.print_output()
        sys.exit(myScript.rs.status_code or 0)
    except (winrm.exceptions.WinRMWebServiceError,
            winrm.exceptions.WinRMAuthorizationError,
            winrm.exceptions.WinRMWSManFault,
            winrm.exceptions.WinRMTransportError) as e:
        """If anything went wrong, print error message and exit"""
        print >>sys.stderr, e
        sys.exit(255)
