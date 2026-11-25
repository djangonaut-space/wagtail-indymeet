# Testing email locally with Mailpit

The application sends many emails. To see 
them during development without emailing anyone, the Docker setup runs
[Mailpit](https://mailpit.axllent.org/), a local mail catcher.

Mailpit webui is running on `http://localhost:8025`, you can also use `just mail` to open the web ui in your default browser.

### Why `EMAIL_ALLOW_ALL_RECIPIENTS` exists

`home.email.send` only delivers to addresses in `ALLOWED_EMAILS_FOR_TESTING`
when `ENVIRONMENT` is not `production`, so a staging site never emails real
users. The console backend skips that filter because nothing leaves the
machine. With SMTP the filter would apply, and almost nothing would reach
Mailpit.

`EMAIL_ALLOW_ALL_RECIPIENTS=true` skips the filter. It is off by default and
must only be set when the SMTP server is a local catcher. Never set it on
staging.
