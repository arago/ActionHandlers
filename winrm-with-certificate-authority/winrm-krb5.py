from winrm.protocol import Protocol

p = Protocol(
    endpoint='http://srv1.adlab.loc:5985/wsman',
    realm='ADLAB.LOC',
    transport='kerberos'
)
shell_id = p.open_shell()
command_id = p.run_command(shell_id, 'ipconfig', ['/all'])
std_out, std_err, status_code = p.get_command_output(shell_id, command_id)
p.cleanup_command(shell_id, command_id)
p.close_shell(shell_id)
print std_out
