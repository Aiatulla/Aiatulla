#!/bin/sh
# Apply migrations, then start whatever command was given.
#
# Migrations run here rather than in a separate deploy step so a container can
# never come up against a schema it does not match. Alembic is idempotent: a
# second instance starting concurrently finds nothing to do.
set -eu

echo "Applying database migrations..."
alembic upgrade head

echo "Starting: $*"
exec "$@"
