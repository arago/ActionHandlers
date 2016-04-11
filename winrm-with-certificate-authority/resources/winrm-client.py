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
        if len(rs.std_err):
            # if there was an error message, clean it it up and make it human readable
            rs.std_err = self.clean_error_msg(rs.std_err)
        return rs
    
class certSession(Session):
    def __init__(self, endpoint, transport, cert, key, validation='ignore'):
        self.protocol = winrm.Protocol(
            endpoint=endpoint,
            transport=transport,
            cert_pem=cert,
            cert_key_pem=key,
            server_cert_validation=validation
        )
class basicSession(Session):
    def __init__(self, endpoint, transport, auth, validation='ignore'):
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
{script}'@ | powershell - 2>&1 | %{{$e=@("psout","pserr")[[byte]($_.GetType().Name -eq "ErrorRecord")];return "<$e><![CDATA[$_]]></$e>"}}
exit $LastExitCode
""")
    cmdWrapper=unicode("""\
$t = [IO.Path]::GetTempFileName() | ren -NewName {{ $_ -replace 'tmp$', 'bat' }} -PassThru
@'
{script}'@ | out-file -encoding "OEM" $t
& cmd.exe /q /c $t 2>&1 | %{{$e=@("psout","pserr")[[byte]($_.GetType().Name -eq "ErrorRecord")];return "<$e><![CDATA[$_]]></$e>"}}
#rm $t
exit $LastExitCode
""")
    def __init__(self, script, interpreter):
        self.interpreter=interpreter
        if interpreter=='cmd': self.wrapper=self.cmdWrapper
        elif interpreter=='powershell': self.wrapper=self.psWrapper
        else: pass
        self.script=script
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
            if s.text: s.text = s.text.rstrip("\n ")
            else: s.text = ''
            if s.tag == 'pserr':
                print >>sys.stderr, s.text
            elif s.tag == 'psout':
                print >>sys.stdout, s.text

### MAIN ###

sys.stdout = codecs.getwriter('utf8')(sys.stdout)
hostnameRegex = '(?=^.{1,253}$)(^(((?!-)[a-zA-Z0-9-]{1,63}(?<!-))|((?!-)[a-zA-Z0-9-]{1,63}(?<!-)\.)+[a-zA-Z]{2,63})$)'
ipv4Regex = '(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)'

usage="""
Usage:
  winrm-client [options] -H <hostname> ( -c <cert> -k <key> | -u <user> -p <passwd> ) <script> [-]

Options:
  -h --help                               Print this help message
  -P <port> --port=<port>                 The network port to use [default: 5986]
  -T <transport> --transport=<transport>  The transport protocol to use for user/password
                                          connections, ssl or plaintext [default: ssl]
  -i <name> --interpreter=<name>          cmd or powershell [default: powershell]

In order to use a insecure connection, you have to specify both -T plaintext and -P 5985
(or whatever port you configured on Windows).
"""

if __name__ == '__main__':
    s = Schema({"<hostname>":     And(str, Or(lambda hn: re.compile(hostnameRegex).match(hn),
                                              lambda ip: re.compile(ipv4Regex).match(ip)),
                                      error='<hostname> has to be a valid hostname, FQDN or IPv4 address'),
                "<cert>":         Or(None, Use(open), error='<cert> has to be a readable file'),
                "<key>":          Or(None, Use(open), error='<key> has to be a readable file'),
                "<user>":         Or(None, str),
                "<passwd>":       Or(None, str),
                "<script>":       Or('-', Use(open), error='<script> has to be a readable file'),
                "--help":         bool,
                "--port":         Or(None, str),
                "--interpreter":  Or(None, "cmd", "powershell",
                                     error='<name> has to be either cmd or powershell'),
                Optional(object): object # suppress validation errors for additional elements
    })
    
    try:
        args = s.validate(docopt(usage))
    except schema.SchemaError as e:
        print >>sys.stderr, usage
        print >>sys.stderr, e
        sys.exit(255)

    if args['-c'] and args['-k']:
        """Authenticate using a client certificate, transport is always ssl."""
        mySession = certSession(
            endpoint="https://{hostname}:{port}/wsman".format(hostname=args['<hostname>'],
                                                              port=args['--port']),
            transport='ssl',
            cert=args['<cert>'].name,
            key=args['<key>'].name,
            validation='ignore')
    elif args['-u'] and args['-p']:
        """Authenticate using credentials, default is to use ssl transport but this can be overridden."""
        if args['--transport'] == 'ssl': proto='https'
        else: proto='http'
        mySession = basicSession(
            endpoint="{proto}://{hostname}:{port}/wsman".format(proto=proto,
                                                                hostname=args['<hostname>'],
                                                                port=args['--port']),
            transport='ssl',
            auth=(args['<user>'], args['<passwd>']))

#    try:
        """Execute script on target machine, get results and print them to their respective channels."""
        myScript=Script(script=args['<script>'].read().decode('utf-8'),
                        interpreter=args['--interpreter'])
        myScript.run(mySession)
        myScript.print_output()
        sys.exit(myScript.rs.status_code or 0)
#    except Exception as e:
        """If anything went wrong, print error message and exit"""
        print >>sys.stderr, e
        sys.exit(255)
