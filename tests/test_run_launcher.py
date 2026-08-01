import socket
import unittest

import run


class RunLauncherTests(unittest.TestCase):
    def test_free_loopback_port_is_accepted(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        run.ensure_port_available("127.0.0.1", port)

    def test_occupied_loopback_port_has_an_actionable_error(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]

            with self.assertRaisesRegex(
                SystemExit,
                "close the other application or choose a free port with --port",
            ):
                run.ensure_port_available("127.0.0.1", port)

    def test_invalid_port_has_an_actionable_error(self):
        with self.assertRaisesRegex(SystemExit, "The port is unavailable"):
            run.ensure_port_available("127.0.0.1", 70000)


if __name__ == "__main__":
    unittest.main()
