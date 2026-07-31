import unittest

from app.auth.rate_limit import LoginRateLimiter


class LoginRateLimiterTests(unittest.TestCase):
    def test_blocks_after_bounded_failures_and_reports_retry(self):
        limiter = LoginRateLimiter(max_failures=3, window_seconds=60)

        for second in (0, 1, 2):
            self.assertIsNone(limiter.register_attempt("client", now=second))

        self.assertEqual(limiter.register_attempt("client", now=3), 57)
        self.assertIsNone(limiter.register_attempt("client", now=61))

    def test_success_clear_removes_failures(self):
        limiter = LoginRateLimiter(max_failures=1, window_seconds=60)
        limiter.record_failure("client", now=0)
        self.assertEqual(limiter.retry_after("client", now=1), 59)

        limiter.clear("client")
        self.assertIsNone(limiter.retry_after("client", now=1))

    def test_key_storage_is_bounded(self):
        limiter = LoginRateLimiter(
            max_failures=2,
            window_seconds=60,
            max_keys=2,
        )
        limiter.record_failure("oldest", now=0)
        limiter.record_failure("newer", now=0)
        limiter.record_failure("newest", now=0)

        self.assertNotIn("oldest", limiter._failures)
        self.assertEqual(set(limiter._failures), {"newer", "newest"})


if __name__ == "__main__":
    unittest.main()
