#!/usr/bin/env python3

import os, sys, re, base64, syslog, pathlib as pl

# Script to run on all ssh accesses to a git user on gateway host

gl_host_login = 'git@gitolite.host.local'
gl_proxy_path = '/usr/local/bin/gitolite-proxy'
gl_shell_path = '/usr/lib/gitolite/gitolite-shell'
gl_auth_opts = 'restrict' # disables all forwarding and such for git-only keys

gl_wrapper_script = f'''#!/bin/bash
set -e
read -r key cmd <<< "$SSH_ORIGINAL_COMMAND"
export SSH_ORIGINAL_COMMAND=$cmd
exec {gl_shell_path} "$key"
'''


# Journal can handle single mutli-line messages, but syslog can't, hence this
# Also, forwarding of such multi-line stuff to syslog can get funky

syslog.openlog('gitolite-proxy', syslog.LOG_PID, syslog.LOG_AUTH)
def log_line(line): syslog.syslog(syslog.LOG_WARNING, line)
def log_lines(lines):
	if isinstance(lines, str): lines = list(line.rstrip() for line in lines.rstrip().split('\n'))
	uid = base64.urlsafe_b64encode(os.urandom(3)).rstrip(b'=').decode()
	for line in lines: log_line(f'[{uid}] {line}')


def do_auth_update():
	ssh_dir = pl.Path('~/.ssh').expanduser()
	ssh_pubkey = (ssh_dir / 'id_ed25519.pub').read_text().strip()
	auth_base = (ssh_dir / 'authorized_keys.base').read_text()

	gl_keys_section, auth_gitolite = None, list()
	for line in sys.stdin.read().splitlines():
		if (line := line.strip()) == '# gitolite start': gl_keys_section = True; continue
		elif line == '# gitolite end': gl_keys_section = False; break
		elif not gl_keys_section: continue
		if m := re.search(
				# Two supported input-line formats here:
				#  - authorized_keys file with "command=... key" lines,
				#    for manual "ssh git@gw < ~/.ssh/authorized_keys" operation.
				#  - push-authkeys trigger output with "# gl-push-authkeys: ..." lines.
				r'^(command="\S+\s+(?P<id_ssh>[^"]+)".*?|# gl-push-authkeys: ##(?P<id_trigger>.*)##)'
				r'\s+(?P<key>(ssh-(rsa|dss)|(sk-)?ssh-ed25519|'
					r'(sk-)?ecdsa-sha2-nistp\d{3})(@openssh\.com)?\s+.*)$', line ):
			gl_key, ssh_key = m['id_ssh'] or m['id_trigger'], m['key']
			cmd = f'{gl_proxy_path} {gl_key}'.replace('\\', '\\\\').replace('"', r'\"')
			auth_opts = f',{gl_auth_opts}' if gl_auth_opts.strip() else ''
			auth_gitolite.append(f'command="{cmd}"{auth_opts} {ssh_key}')
		else: # not dumping line itself here to avoid having any keys in the logs
			log_line(f'Failed to match gitolite ssh-auth line {n}')
	auth_gitolite = '\n'.join(auth_gitolite)

	# Not done via tempfile to avoid needing rename() in ~/.ssh dir to this uid
	with (ssh_dir / 'authorized_keys').open('a+') as dst:
		dst.seek(0)
		with (ssh_dir / 'authorized_keys.old').open('w') as bak:
			bak.write(dst.read())
			bak.flush()
			os.fdatasync(bak.fileno())
		dst.seek(0)
		dst.truncate()
		dst.write(f'{auth_base}\n### Gitolite proxy commands\n{auth_gitolite}\n')

	# Used to update ssh command on the gitolite host, in case it might change here
	sys.stdout.write('\n'.join([ssh_pubkey, gl_wrapper_script]))


def main(args=None):
	sys_argv = sys.argv[1:] if args is None else args
	git_cmd = os.environ.get('SSH_ORIGINAL_COMMAND', '')

	if len(sys_argv) != 1:
		log_lines([
			'Invalid git-proxy command line'
				f' from gitolite authorized_keys file: {sys_argv!r}',
			f'Original ssh command: {git_cmd!r}' ])
		print('git access denied', file=sys.stderr) # sent to ssh connection
		return 1
	cmd, = sys_argv

	# Should only be done by gitolite-admin update hook via special key
	if cmd == '--auth-update':
		do_auth_update()
		return 0

	# Running actual proxy-command
	os.execlp('ssh', 'ssh', '-qT', gl_host_login, f'{cmd} {git_cmd}')

if __name__ == '__main__':
	try: code = main()
	except Exception as err:
		import traceback
		log_lines(
			['ERROR: Exception while handling ssh login']
			+ traceback.format_exc().splitlines() )
		code = 1
	sys.exit(code)
