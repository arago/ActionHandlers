from winrm.protocol import Protocol

p = Protocol(
    endpoint='https://srv3.adlab.loc:5986/wsman',
    transport='ssl',
    cert_pem='user.pem',
    cert_key_pem='user-key.pem',
    server_cert_validation='ignore'
)
shell_id = p.open_shell()
command_id = p.run_command(shell_id, "dir", ["c:\\windows"])
std_out, std_err, status_code = p.get_command_output(shell_id, command_id)
p.cleanup_command(shell_id, command_id)
p.close_shell(shell_id)
print std_out
