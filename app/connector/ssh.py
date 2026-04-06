from __future__ import annotations

import io
import socket
from dataclasses import dataclass
from typing import Any
import paramiko

class SSHConnectionError(Exception):
    pass


@dataclass(frozen=True)
class SSHClientConfig:
    hostname: str
    username: str
    private_key: str
    port: int = 22
    timeout_seconds: int = 10


class SSHConnector:
    def __init__(self, config: SSHClientConfig):
        self.config = config

    def _parse_private_key(self) -> Any:
        key_value = self.config.private_key.strip()
        if not key_value:
            raise SSHConnectionError("Private key is required")

        key_parsers: list[Any] = [
            paramiko.RSAKey,
            paramiko.ECDSAKey,
            paramiko.Ed25519Key,
        ]

        dss_key = getattr(paramiko, "DSSKey", None)
        if dss_key is not None:
            key_parsers.append(dss_key)

        for parser in key_parsers:
            try:
                return parser.from_private_key(io.StringIO(key_value))
            except (paramiko.PasswordRequiredException, paramiko.SSHException, ValueError, TypeError):
                continue

        raise SSHConnectionError("Unsupported or invalid private key format")

    def connect(self):
        try:
            key = self._parse_private_key()
        except SSHConnectionError:
            raise
        except Exception as exc:
            raise SSHConnectionError(f"Failed to parse private key: {exc}") from exc

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=self.config.hostname,
                port=self.config.port,
                username=self.config.username,
                pkey=key,
                timeout=self.config.timeout_seconds,
                auth_timeout=self.config.timeout_seconds,
                banner_timeout=self.config.timeout_seconds,
                look_for_keys=False,
                allow_agent=False,
            )
            return client
        except (paramiko.AuthenticationException, paramiko.SSHException, OSError, socket.error) as exc:
            client.close()
            raise SSHConnectionError(f"Failed to connect to {self.config.hostname}:{self.config.port} as {self.config.username}: {exc}") from exc

    def execute(self, command: str) -> tuple[int, str, str]:
        try:
            with self.connected_client() as client:
                stdin, stdout, stderr = client.exec_command(command)
                _ = stdin
                exit_code = stdout.channel.recv_exit_status()
                output = stdout.read().decode("utf-8", errors="replace")
                error_output = stderr.read().decode("utf-8", errors="replace")
                return exit_code, output, error_output
        except SSHConnectionError:
            raise
        except Exception as exc:
            raise SSHConnectionError(f"Failed to execute command '{command}': {exc}") from exc

    def connected_client(self) -> "_ConnectedClientContext":
        return _ConnectedClientContext(self)


class _ConnectedClientContext:
    def __init__(self, connector: SSHConnector):
        self._connector = connector
        self._client: Any = None

    def __enter__(self):
        self._client = self._connector.connect()
        return self._client

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        if self._client is not None:
            self._client.close()
