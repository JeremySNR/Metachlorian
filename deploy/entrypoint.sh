#!/bin/sh
set -e
# First start: fetch the default local models unless told not to.
if [ "${METACHLORIAN_FETCH_MODELS:-1}" = "1" ]; then
  metachlorian models fetch || echo "Model download failed; analysers that need them will report 'unavailable'."
fi
# Create the first admin from the environment if none exists.
if [ -n "$METACHLORIAN_ADMIN_USER" ] && [ -n "$METACHLORIAN_ADMIN_PASSWORD" ]; then
  metachlorian user list | grep -q "'$METACHLORIAN_ADMIN_USER'" || \
    metachlorian user add "$METACHLORIAN_ADMIN_USER" --role admin --password "$METACHLORIAN_ADMIN_PASSWORD"
fi
if [ "$1" = "serve" ]; then
  shift
  ADD=""
  [ -d /footage ] && ADD="--add /footage"
  exec metachlorian serve --host 0.0.0.0 --port 8765 $ADD "$@"
fi
exec metachlorian "$@"
