#!/bin/bash
set -e

gw_proxy_login=git@proxy.host.local
gw_script_path="$HOME"/.ssh/gw-proxy-script
gw_proxy=$(ssh -qT "$gw_proxy_login" < ~/.ssh/authorized_keys)

read -r gw_key <<< "$gw_proxy"
readarray -s1 gw_script <<< "$gw_proxy"
[[ "$gw_key" =~ ^ssh- && "${#gw_script[@]}" -gt 1 ]]\
	|| { echo >&2 "ERROR: failed to communicate with gateway-shell"; exit 1; }

exec 3>"$gw_script_path"
for line in "${gw_script[@]}"
do echo -n "$line" >&3
done
exec 3>&-
chmod +x "$gw_script_path"

grep -qF "$gw_key" ~/.ssh/authorized_keys || {
	exec 3>>~/.ssh/authorized_keys
	echo >&3 "### Gateway-proxy key, used for indirect access"
	echo >&3 "command=\"$gw_script_path\""`
		`",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty $gw_key"
	exec 3>&-
}
