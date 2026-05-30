# Contributing

Thanks for helping improve LogForge Unicron.

## Ground Rules

- Keep pull requests scoped to one feature, cleanup, or fix.
- Prefer existing project patterns and keep changes easy to review.
- Do not commit real secrets, local `.env` files, generated runtime state,
  dependency directories, caches, or local certificates.
- Update public-facing instructions when a change affects setup, operation, or
  contributor workflow.
- Include the validation you ran, and call out checks that could not run.

## Local Checks

Run the focused checks for the area you changed. Common checks are:

```sh
docker compose -f deploy/standalone/docker-compose.yml config
npm --prefix central/unicron/frontend run typecheck
TMPDIR=/tmp npm --prefix central/unicron/frontend test
npm --prefix central/auth run typecheck
make test-central-auth
(cd ops/appliance/manager && go test ./...)
(cd edge/go-streamer && go test ./...)
(cd central/unicron/backend && poetry run python -m unittest tests.test_security_hardening tests.test_origin_policy tests.test_appliance_update)
```

## Pull Requests

- Explain the user-visible behavior or maintenance goal.
- Note any compatibility, deployment, or data considerations.
- Describe validation that passed and any checks that could not run.
- Keep unrelated refactors out of the same PR.
