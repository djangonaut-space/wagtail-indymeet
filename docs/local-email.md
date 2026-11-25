# Testing email locally with Mailpit

The application sends many emails (application confirmations, acceptance and
rejection notices, session reminders, account and two-factor emails). To see
them during development without emailing anyone, the Docker setup runs
[Mailpit](https://mailpit.axllent.org/), a local mail catcher.

## How it works

```
django / worker / scheduler ──SMTP (mailpit:1025)──▶ mailpit ──▶ web UI (localhost:8025)
```

- `docker compose up` starts the `mailpit` service alongside Django.
- Django sends with the SMTP backend to `mailpit:1025` over the Docker network.
  This port is not published to the host.
- Mailpit stores every message and shows it at http://localhost:8025, with the
  HTML and plain-text parts, headers, attachments and a link checker.
  `just mail` opens it.
- Messages are kept in memory and are cleared when the container restarts.

## Configuration

These environment variables (set in `.env.docker`) turn it on:

```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mailpit
EMAIL_PORT=1025
EMAIL_ALLOW_ALL_RECIPIENTS=true
```

### Why `EMAIL_ALLOW_ALL_RECIPIENTS` exists

`home.email.send` only delivers to addresses in `ALLOWED_EMAILS_FOR_TESTING`
when `ENVIRONMENT` is not `production`, so a staging site never emails real
users. The console backend skips that filter because nothing leaves the
machine. With SMTP the filter would apply, and almost nothing would reach
Mailpit.

`EMAIL_ALLOW_ALL_RECIPIENTS=true` skips the filter. It is off by default and
must only be set when the SMTP server is a local catcher. Never set it on
staging.

## Switching back to the console

To print emails to the Docker logs instead, set this in your `.env` (which
overrides `.env.docker`):

```
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

## Tests

Tests are unaffected. They use the locmem backend, and assertions read from
`django.core.mail.outbox`.
