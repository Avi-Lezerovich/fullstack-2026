#!/bin/sh
# Render nginx.conf, then hand the process over to nginx.
#
# The stock nginx image has an envsubst step of its own, but it only runs when
# the container starts as root - and this one deliberately does not. So the
# rendering happens here, into /tmp, which is the one place an unprivileged
# nginx can write.
#
# The variable list is explicit: without it envsubst would also eat nginx's own
# $host, $remote_addr and $uri.
set -eu

: "${API_UPSTREAM:=server:5002}"
export API_UPSTREAM

envsubst '${API_UPSTREAM}' < /etc/nginx/nginx.conf.template > /tmp/nginx.conf

# exec, so nginx becomes PID 1 and `docker stop` reaches it directly.
exec nginx -c /tmp/nginx.conf -g 'daemon off;' "$@"
