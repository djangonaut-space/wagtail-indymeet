# Testing email locally with Mailpit

The application sends many emails. To see
them during development without emailing anyone, the Docker setup runs
[Mailpit](https://mailpit.axllent.org/), a local mail catcher.

Mailpit webui is running on `http://localhost:8025`, you can also use `just mail` to open the web ui in your default browser.
