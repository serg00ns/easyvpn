from __future__ import annotations

from app.connector import SSHClientConfig, SSHConnectionError, SSHConnector


class VPNSetupTool:
    """Scaffold for future VPN setup orchestration over SSH."""

    def __init__(self, connector: SSHConnector):
        self.connector = connector

    @classmethod
    def from_server_credentials(
        cls,
        ip_address: str,
        username: str,
        private_key: str,
        port: int = 22,
        timeout_seconds: int = 10,
    ) -> "VPNSetupTool":
        config = SSHClientConfig(
            hostname=ip_address,
            username=username,
            private_key=private_key,
            port=port,
            timeout_seconds=timeout_seconds,
        )
        return cls(SSHConnector(config))

    def check_connectivity(self) -> tuple[bool, str]:
        try:
            with self.connector.connected_client():
                pass
            return True, "SSH connection successful"
        except SSHConnectionError as exc:
            return False, str(exc)
