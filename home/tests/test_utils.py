from django.test import RequestFactory, TestCase

from home.utils import get_client_ip


class GetClientIpTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_uses_remote_addr_when_no_forwarded_header(self):
        request = self.factory.get("/", REMOTE_ADDR="198.51.100.1")
        self.assertEqual(get_client_ip(request), "198.51.100.1")

    def test_prefers_leftmost_forwarded_for_address(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.5, 10.0.0.1",
        )
        self.assertEqual(get_client_ip(request), "203.0.113.5")

    def test_returns_none_when_neither_header_present(self):
        request = self.factory.get("/")
        del request.META["REMOTE_ADDR"]
        self.assertIsNone(get_client_ip(request))
