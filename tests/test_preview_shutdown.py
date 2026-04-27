import unittest
from unittest.mock import patch

from takota_people_flow.preview import ShutdownController, _is_private_client


class PreviewShutdownTest(unittest.TestCase):
    def test_shutdown_controller_requires_command(self) -> None:
        controller = ShutdownController(enabled=True, command="")

        self.assertFalse(controller.enabled)

    def test_shutdown_controller_runs_fixed_command(self) -> None:
        controller = ShutdownController(enabled=True, command="sudo -n /usr/sbin/poweroff")

        with patch("takota_people_flow.preview.subprocess.Popen") as popen:
            controller._run_shutdown()

        popen.assert_called_once_with(["sudo", "-n", "/usr/sbin/poweroff"], start_new_session=True)

    def test_private_client_check_allows_lan_and_localhost(self) -> None:
        self.assertTrue(_is_private_client("127.0.0.1"))
        self.assertTrue(_is_private_client("192.168.1.10"))
        self.assertTrue(_is_private_client("172.20.10.2"))

    def test_private_client_check_rejects_public_addresses(self) -> None:
        self.assertFalse(_is_private_client("8.8.8.8"))
        self.assertFalse(_is_private_client("not-an-ip"))


if __name__ == "__main__":
    unittest.main()
