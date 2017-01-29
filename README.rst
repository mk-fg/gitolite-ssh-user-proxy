=======================
gitolite-ssh-user-proxy
=======================

Custom shell+trigger to proxy ssh connection to `gitolite
<http://gitolite.com/>`_ user\@host through a proxy/bastion host securely and
transparently.

.. contents::
  :backlinks: none


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

- git\@gl (gitolite user on gl machine) has post-update hook enabled for
  gitolite-admin repository, which sends authorized_keys list that gitolite
  builds to gw host (via simple ``ssh git@gw < ~/.ssh/authorized_keys``).

- git\@gw builds authorized_keys in same exact way as gitolite does, only
  replacing command="gitolite-shell" there with command="gitolite-proxy".

  Also has one extra key for git\@gl that runs ``gitolite-proxy --auth-update`` command.

- Aforementioned gitolite-admin post-update hook also checks/adds one extra key
  for git\@gw, with a 3-liner "gw-proxy" script to run ``gitolite-shell <key-id>``,
  reading "key-id" from command passed by gitolite-proxy.

- Every access to git\@gw runs gitolite-proxy (in same exact was as
  gitolite-shell), which does straightforward ``os.execlp(ssh -qT gl_host_login
  key-id git-cmd...)``, which then runs "gw-proxy" 3-liner script above, which puts
  "git-cmd" into SSH_ORIGINAL_COMMAND and does ``exec gitolite-shell
  "$key-id"``, exactly same as direct ssh to gitolite host would do it.

Information about how to setup the thing in more of a step-by-step format can be
found in a blog entry at one of these URLs:

- http://blog.fraggod.net/2017/01/29/proxying-ssh-user-connections-to-gitolite-host-transparently.html
- https://github.com/mk-fg/blog/blob/master/content/2017-01-29.proxying_ssh_user_connections_to_gitolite_host.rst


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
