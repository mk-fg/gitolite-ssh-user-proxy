=======================
gitolite-ssh-user-proxy
=======================

Custom shell+trigger to proxy ssh connection to `gitolite
<http://gitolite.com/>`_ user\@host through a proxy/bastion host securely and
transparently.

.. contents::
  :backlinks: none

Repository URLs:

- https://github.com/mk-fg/gitolite-ssh-user-proxy
- https://codeberg.org/mk-fg/gitolite-ssh-user-proxy
- https://fraggod.net/code/git/gitolite-ssh-user-proxy


What it does
------------

In a setup like this one::

  +---------------+
  |               |   git@myhost.net:myrepo
  |  dev-machine  ---------------------------+
  |               |                          |
  +---------------+                          |
                                +------------v------+
        git@gitolite:myrepo     |                   |
    +----------------------------  myhost.net (gw)  |
    |                           |                   |
  +-v-------------------+       +-------------------+
  |                     |
  |    gitolite (gl)    |
  |  host/container/vm  |
  |                     |
  +---------------------+

...where "dev-machine" can't access "gl" (gitolite) host directly, allows
fully-transparent access to gitolite via specific user on a "gw" (myhost.net) host.

E.g. simply do ``git add remote origin git@myhost.net:myrepo`` and all the
things gitolite will work, without any extra ssh or forwarding configuration on
git client machine.


How it works
------------

- gitolite on gl machine has POST_COMPILE "push-authkeys" trigger installed, which
  sends public keys from gitolite-admin keydir to gw host (via simple ``ssh git@gw < keys``).

- git\@gw, upon receiving keys (to ``gitolite-proxy --auth-update`` command),
  builds authorized_keys in same exact way as gitolite's ssh-authkeys trigger
  does, only instead of command="gitolite-shell" it has command="gitolite-proxy"
  and authorized_keys file is built on gw host.

  Also has one extra key there for git\@gl that runs this
  ``gitolite-proxy --auth-update`` command.

- Aforementioned push-authkeys trigger (from first step), after sending keys to
  git\@gw, makes sure that git\@gw key is in ~/.ssh/authorized_keys (in addition
  to all gitolite-admin keys, if ssh-authkeys is enabled) with a 3-liner
  "gw-proxy" script to run ``gitolite-shell <key-id>`` (reading "key-id" from
  command passed by gitolite-proxy).

- Every access to git\@gw (using client key) then:

  - Runs gitolite-proxy with key-id argument for that specific key (same as
    gitolite-shell does).

  - Which does straightforward ``os.execlp(ssh -qT gl_host_login key-id git-cmd...)``.

  - Which then runs "gw-proxy" 3-liner script from above on gl host.

  - Which puts "git-cmd" into SSH_ORIGINAL_COMMAND and does
    ``exec gitolite-shell "$key-id"``, i.e. runs gitolite-shell in the same way
    as direct ssh to gitolite host would do it.

  - Which then does whatever gitolite is supposed to do for that key and git command.


Installation / setup
--------------------

- Install ``/usr/local/bin/gitolite-proxy`` on a gw host, updating gl_host_login
  line in there and ``useradd -m git`` there.

- Run ``ssh-keygen -t ed25519`` as both git\@gw and git\@gl, add each host to
  ~/.ssh/known_hosts on the other one.

- Put following line to ~git/.ssh/authorized_keys.base on gw host, replacing
  pubkey with ~/.ssh/id_ed25519.pub from git\@gl (split here for readability,
  must be one line)::

    command="/usr/local/bin/gitolite-proxy --auth-update",no-port-forwarding
      ,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAA...4u3FI git@gl

  Copy that file to authorized_keys and allow git\@gw write-access to it (will
  be updated with keys from git\@gl).

- As git\@gl, run ``ssh -qT git@gw < ~/.ssh/authorized_keys`` to push gitolite
  keys to git\@gw.

- Add this to ~git/.gitolite.rc on gl host right before ENABLE line::

    LOCAL_CODE => "$rc{GL_ADMIN_BASE}/local",
    POST_COMPILE => ['push-authkeys'],

- Commit/push push-authkeys.sh trigger into gitolite-admin repo as
  ``local/triggers/push-authkeys``, updating gw_proxy_login line in there.

- Done!

More info on the setup can found in a blog entry at one of these URLs:

- http://blog.fraggod.net/2017/01/29/proxying-ssh-user-connections-to-gitolite-host-transparently.html
- https://github.com/mk-fg/blog/blob/master/content/2017-01-29.proxying_ssh_user_connections_to_gitolite_host.rst


Notes
-----

- With this setup in place, "ssh-authkeys" trigger can be disabled in gitolite,
  which will make it only accessible through git\@gw host, and not directly.

- "push-authkeys" trigger can also be installed on gitolite host without the
  need to have it in gitolite-admin repo - see `docs on gitolite triggers
  <http://gitolite.com/gitolite/gitolite.html#triggers>`_ for more details.

- "gitolite-proxy --auth-update" can accept (to stdin) either ssh
  authorized_keys built by gitolite's "ssh-authkeys" or simplier format
  (just keys without ssh-specific cruft) that push-authkeys sends to it.

- gateway-proxy.py needs python3, push-authkeys.sh uses bash and gawk (GNU awk).
  Both also use ssh, of course.

- Paths and some other options can be tweaked in the vars at the top of the scripts.


Other options
-------------

Assuming setup from "What it does" section above:

- Use separate public host/IP for gitolite, e.g. git.myhost.net (!= myhost.net).

- TCP port forwarding or similar tricks.

  Forward ssh port connections in a "gw:22 -> gl:22" fashion, and have
  gw-specific sshd listen on some other port, if necessary.

  This can be fairly easy to use with something like this for odd-port sshd
  in ~/.ssh/config::

    Host myhost.net
      Port 1234
    Host git.myhost.net
      Port 1235

  Can also be configured in git via remote urls like
  ``ssh://git@myhost.net:1235/myrepo``.

- Use ssh port forwarding to essentially do same thing as above, but with
  resulting git port accessible on localhost.

- Configure ssh to use ProxyCommand, which will login to gw host and setup
  forwarding through it.

One advantage of such lower-level forwarding is that ssh authentication to
gitolite is only handled on gitolite host, gw host has no clue about that.
