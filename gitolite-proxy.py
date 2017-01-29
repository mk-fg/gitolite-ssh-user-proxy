#!/usr/bin/env python3

import itertools as it, operator as op, functools as ft
import os, sys, re, pathlib, base64, syslog


gl_host_login = 'git@gitolite.host.local'
gl_proxy_path = '/usr/local/bin/gitolite-proxy'
gl_shell_path = '/usr/lib/gitolite/gitolite-shell'
gl_wrapper_script = '''#!/bin/bash
set -e
read -r key cmd <<< "$SSH_ORIGINAL_COMMAND"
export SSH_ORIGINAL_COMMAND=$cmd
exec {gl_shell} "$key"
'''.format(gl_shell=gl_shell_path)


# Journal can handle single mutli-line messages, but syslog can't, hence this
# Also, forwarding of such multi-line stuff to syslog can get funky

def b64(data):
	return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def get_uid_token(chars=4):
	assert chars * 6 % 8 == 0, chars
	return b64(os.urandom(chars * 6 // 8))

def log_lines(log_func, lines, log_func_last=False, **log_func_kws):
	if isinstance(lines, str): lines = list(line.rstrip() for line in lines.rstrip().split('\n'))
	uid = get_uid_token()
	for n, line in enumerate(lines, 1):
		if not isinstance(line, str): line = line[0].format(*line[1:])
		line = '[{}] {}'.format(uid, line)
		if log_func_last and n == len(lines): log_func_last(line)
		else: log_func(line, **log_func_kws)

syslog.openlog('gitolite-proxy', syslog.LOG_PID, syslog.LOG_AUTH)
syslog_line = ft.partial(syslog.syslog, syslog.LOG_WARNING)
syslog_lines = ft.partial(log_lines, syslog_line)


def do_auth_update():
	ssh_dir = pathlib.Path('~/.ssh').expanduser()

	with (ssh_dir / 'id_ed25519.pub').open() as src: ssh_pubkey = src.read().strip()
	with (ssh_dir / 'authorized_keys.base').open() as src: auth_base = src.read()

	mark, auth_gitolite = None, list(map(str.strip, sys.stdin.read().splitlines()))
	for n, line in enumerate(auth_gitolite):
		if mark is None and line == '# gitolite start': mark, line = True, None
		elif line == '# gitolite end': mark, line = False, None
		if not mark: line = None
		if line:
			m = re.search( r'^command="\S+ ([^"]+)".*?'
				r' ((?:ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ssh-dss) .*)$', line )
			if not m:
				# Not dumping line itself here to avoid having pubkeys in the logs
				syslog_line('Failed to match gitolite ssh-auth line {}'.format(n))
				line = None
			else:
				gl_key, ssh_key = m.groups()
				line = ( 'command="{} {}",no-port-forwarding,no-X11-forwarding,'
					'no-agent-forwarding,no-pty {}' ).format(gl_proxy_path, gl_key, ssh_key)
		auth_gitolite[n] = line
	auth_gitolite = '\n'.join(filter(None, auth_gitolite))

	# Not done via tempfile to avoid allowing rename() in ~/.ssh dir to this uid
	with (ssh_dir / 'authorized_keys').open('a+') as dst:
		dst.seek(0)
		with (ssh_dir / 'authorized_keys.old').open('w') as bak:
			bak.write(dst.read())
			bak.flush()
			os.fdatasync(bak.fileno())
		dst.seek(0)
		dst.truncate()
		dst.write(auth_base)
		dst.write('\n### Gitolite proxy commands\n')
		dst.write(auth_gitolite)
		dst.write('\n')

	sys.stdout.write('\n'.join([ssh_pubkey, gl_wrapper_script]))


def main(args=None):
	sys_argv = sys.argv[1:] if args is None else args
	git_cmd = os.environ.get('SSH_ORIGINAL_COMMAND', '')

	if len(sys_argv) != 1:
		syslog_lines([
			( 'Invalid git-proxy command line'
				' from gitolite authorized_keys file: {!r}', sys_argv ),
			('Original ssh command: {!r}', git_cmd) ])
		print('git access denied', file=sys.stderr)
		return 1
	cmd, = sys_argv

	# Should only be done by gitolite-admin update hook via special key
	if cmd == '--auth-update':
		do_auth_update()
		return 0

	# Running actual proxy-command
	os.execlp('ssh', 'ssh', '-qT', gl_host_login, '{} {}'.format(cmd, git_cmd))

if __name__ == '__main__':
	try: code = main()
	except Exception as err:
		import traceback
		syslog_lines(
			['ERROR: Exception while handling ssh login']
			+ traceback.format_exc().splitlines() )
		code = 1
	sys.exit(code)
