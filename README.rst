=======================
gitolite-ssh-user-proxy
=======================

Custom shell+trigger to proxy ssh connection to gitolite_
user\@host through a proxy/bastion host securely and
transparently.

.. _gitolite: https://gitolite.com/

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
fully-transparent access to gitolite via specific ssh user on a "gw" host
("git\@myhost.net" in this example).

E.g. simply do ``git add remote origin git@myhost.net:myrepo`` and all the
things gitolite will work, without any extra ssh or forwarding configuration
for custom ports and such on a dev machine (git client).


How it works
------------

- gitolite on gl machine has POST_COMPILE "push-authkeys" trigger installed, which
  sends public keys from gitolite-admin keydir to gw host (via simple ``ssh git@gw < keys``).

- git\@gw, upon receiving keys (to ``gitolite-proxy --auth-update`` command),
  builds authorized_keys in same exact way as gitolite's ssh-authkeys trigger
  does, only instead of command="gitolite-shell <key-id>" it has
  command="gitolite-proxy <key-id>", allowing for same gitolite ssh auth to
  happen on gw host instead.

  Also has one extra key there for access from git\@gl hook, that runs this
  ``gitolite-proxy --auth-update`` command.

- Aforementioned push-authkeys trigger (from first step), after sending keys to
  git\@gw, makes sure that git\@gw key is in ~/.ssh/authorized_keys, which will
  be used for all proxied connections.

  (in addition to all gitolite-admin keys, if ssh-authkeys is enabled)

  git\@gw -> git\@gl access a forces 3-liner command="gw-proxy" script,
  which will then run ``gitolite-shell <key-id>`` (reading "key-id" for it
  from command passed by gitolite-proxy), same as gitolite will do normally
  with direct access.

So every access to git\@gw (using client key) then ends up working like this:

- Runs gitolite-proxy with key-id argument for that specific key - same key-id
  arg as gitolite-shell normally gets from command= (when accessed directly).

- Which does straightforward ``os.execlp(ssh -qT gl_host_login key-id git-cmd...)``.

- Which then runs "gw-proxy" 3-liner script from above on gl host.

- Which puts "git-cmd" into SSH_ORIGINAL_COMMAND and does
  ``exec gitolite-shell key-id``, i.e. runs gitolite-shell in the same way
  as direct ssh to gitolite host would do it.

- Which then does whatever gitolite is supposed to do for that key and git command.


Installation / setup
--------------------

- Install/setup gitolite on git\@gl destination as usual.

- Install `gitolite-proxy.py`_ to ``/usr/local/bin/gitolite-proxy`` on a gw host,
  updating gl_host_login line in there, run ``useradd -m git`` to create git\@gw
  user account for sshd.

- Run ``ssh-keygen -t ed25519`` as both git\@gw and git\@gl, add each host to
  ~/.ssh/known_hosts on the other one.

- Put following line to ~git/.ssh/authorized_keys.base on gw host, replacing
  pubkey with ~/.ssh/id_ed25519.pub from git\@gl::

    command="/usr/local/bin/gitolite-proxy --auth-update",restrict ssh-ed25519 AAA...4u3FI git@gl

  Copy that file to a normal ``authorized_keys`` file as well, allow write
  access for git\@gw to it and ``authorized_keys.old`` backup-file next to it
  (--auth-update from git\@gl will be updating them). Write-access is only
  needed to those two files.

- As git\@gl, run ``ssh -qT git@gw < ~/.ssh/authorized_keys`` to do an initial
  push of gitolite authorized-keys list to git\@gw, and test that gitolite-proxy
  script and all required access permissions work.

- Add this to ~git/.gitolite.rc on gl host right before ENABLE line::

    LOCAL_CODE => "$rc{GL_ADMIN_BASE}/local",
    POST_COMPILE => ['push-authkeys'],

- Commit/push `push-authkeys.sh`_ trigger into gitolite-admin repo as
  ``local/triggers/push-authkeys``, updating gw_proxy_login line in there.

- Done!

Bit more info on the setup can found in an old blog entry at one of these URLs:

- http://blog.fraggod.net/2017/01/29/proxying-ssh-user-connections-to-gitolite-host-transparently.html
- https://github.com/mk-fg/blog/blob/master/content/2017-01-29.proxying_ssh_user_connections_to_gitolite_host.rst

.. _gitolite-proxy.py: gitolite-proxy
.. _push-authkeys.sh: push-authkeys.sh


Notes
-----

- With this setup in place, "ssh-authkeys" trigger can be disabled in gitolite,
  which will make it only accessible through git\@gw host, and not directly.

- "push-authkeys" trigger can also be installed on gitolite host, without the
  need to have it in gitolite-admin repo - see `docs on gitolite triggers
  <http://gitolite.com/gitolite/gitolite.html#triggers>`_ for more details.

- "gitolite-proxy --auth-update" can accept (to stdin) either ssh
  authorized_keys built by gitolite's "ssh-authkeys" or simpler format
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

One advantage of using lower-level port-forwarding is that ssh authentication
to gitolite is only handled on gitolite host/container/vm itself, all in one place,
instead of exposing it in on/to a gw host, adding one extra place where it
can potentially be vulnerable, broken, monitored, or tampered with.
