# Load Tests

This utilizes [k6](https://github.com/grafana/k6) to test our application
under a defined amount of load. You can
[install k6 here](https://grafana.com/docs/k6/latest/get-started/installation/).

These tests aren't promised to work out of the box. You may need
to tweak things future-djangonaut.

To run a test:

```shell
k6 run test_blog.js
```

## Testing the application flow

There is a load test that covers signing up, logging in, setting availability then submitting an application. The following are the instructions on how to run it.

1. SSH into server (see [deployment docs](../docs/deployment.md))
   ```bash
   ssh root@djangonaut.space
   ```
2. Enable load testing configuration
   ```bash
   dokku config:set staging LOAD_TESTING=True
   ```
3. Monitor logs and [Sentry performance](https://djangonaut-space.sentry.io/explore/profiling/?project=4506747129626624&statsPeriod=1h)
   ```bash
   dokku logs staging -t
   ```
4. On local machine, run tests
   ```bash
   k6 run test_application.js
   ```
5. Undo loading configuration
   ```bash
   dokku config:unset staging LOAD_TESTING
   ```
6. Delete [load test users](https://staging.djangonaut.space/django-admin/accounts/customuser/?q=load_test)
