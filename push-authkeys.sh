#!/bin/bash
set -e -o pipefail
umask 0077

gw_proxy_login=git@gateway.host.local
gw_script_path="$HOME"/.ssh/gw-proxy-script

[[ "$GL_REPO" = gitolite-admin ]] || exit 0

# Buffering here is to ensure that whole keydir
#  was processed without errors before sending any keys.
# Simple "set -e" doesn't work for "readarray < <(...)", hence sentinel value.
clean_exit_mark='-- done --'
readarray -t keys < <(
	find "$GL_ADMIN_BASE"/keydir/ -xdev -type f -name "*.pub" -print0 | sort -z |
	xargs -0 gawk 'match($1,/^(ssh-|ecdsa-|sk-ssh-)/) && $2 {
		fn=gensub(/.*\/(.*)\.pub$/, "\\1", 1, FILENAME)
		printf("# gl-push-authkeys: ##%s## %s %s\n", fn, $1, $2)}'
	echo "$clean_exit_mark" )
[[ "${keys[${#keys[@]}-1]}" = "$clean_exit_mark" ]]\
	|| { echo >&2 'ERROR: failed to process gitolite-admin keydir'; exit 1; }
unset 'keys[${#keys[@]}-1]'

gw_proxy=$(
	ssh -qT "$gw_proxy_login" < <(
		echo '# gitolite start'
		for key in "${keys[@]}"; do echo -E "$key"; done
		echo '# gitolite end' ) )

read -r gw_key <<< "$gw_proxy"
readarray -s1 gw_script <<< "$gw_proxy"
[[ "$gw_key" =~ ^ssh- && "${#gw_script[@]}" -gt 1 ]]\
	|| { echo >&2 "ERROR: failed to communicate with gateway-shell"; exit 1; }

exec 3>"$gw_script_path"
for line in "${gw_script[@]}"
do echo -nE "$line" >&3
done
exec 3>&-
chmod +x "$gw_script_path"

grep -sqF "$gw_key" ~/.ssh/authorized_keys || {
	exec 3>>~/.ssh/authorized_keys
	echo >&3 "### Gateway-proxy key, used for indirect access"
	echo >&3 "command=\"$gw_script_path\""`
		`",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty $gw_key"
	exec 3>&-
}
