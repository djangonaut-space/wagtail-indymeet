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
