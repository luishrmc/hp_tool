"""Calculator file-system service built on top of existing host-command flows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from calculator import CalculatorClient, RPLCommandBuilder
from conn.packet import KermitPacket


@dataclass(frozen=True, slots=True)
class RemoteEntry:
    """Describe one calculator-side entry addressable by path."""

    path: str
    name: str
    entry_type: str


@dataclass(frozen=True, slots=True)
class RemoteFile(RemoteEntry):
    """Describe a remote file-like entry."""


@dataclass(frozen=True, slots=True)
class RemoteDirectory(RemoteEntry):
    """Describe a remote directory entry."""


@dataclass(frozen=True, slots=True)
class VariableSpec:
    """Describe a variable-like object that should be created remotely."""

    name: str
    value: str
    folder: str | None = None


class CalculatorFileSystem:
    """Higher-level file-system style operations for the calculator."""

    def __init__(self, client: CalculatorClient) -> None:
        """Bind the service to an existing calculator client."""
        self.client = client

    @staticmethod
    def _split_remote_path(path: str) -> tuple[str | None, str]:
        """Split a calculator path into parent folder and leaf name."""
        normalized = PurePosixPath(path)
        name = normalized.name
        if not name:
            raise ValueError(f"Remote path must include a final name: {path!r}")

        parent = str(normalized.parent)
        if parent in ("", "."):
            parent = None
        return parent, name

    @classmethod
    def _resolve_name_and_folder(cls, name: str, folder: str | None = None) -> tuple[str | None, str]:
        """Resolve a leaf name plus optional folder into a normalized pair."""
        parent, leaf = cls._split_remote_path(name)
        if parent is not None:
            if folder and folder != parent:
                raise ValueError(
                    f"Conflicting remote folders provided: name={name!r}, folder={folder!r}"
                )
            return parent, leaf
        return folder, leaf

    def create_dir(self, path: str) -> KermitPacket:
        """Create a directory on the calculator."""
        return self.client.run_rpl(RPLCommandBuilder.create_remote_dir(path))

    def remove_dir(self, path: str, purge: bool = False) -> KermitPacket:
        """Remove a directory, optionally purging non-empty contents first."""
        return self.client.run_rpl(RPLCommandBuilder.remove_remote_dir(path, purge=purge))

    def rename(self, old_path: str, new_path: str) -> KermitPacket:
        """Rename a remote object.

        This remains intentionally unimplemented in the first incremental step.
        The current host-command flow is good for side-effecting commands, but a
        safe rename primitive needs clearer object-kind handling and stronger
        directory-aware semantics than the project has today.
        """
        del old_path, new_path
        raise NotImplementedError(
            "Remote rename is not implemented yet; add an explicit RPL rename/move "
            "builder once object-kind semantics are defined."
        )

    def list_dir(self, path: str) -> list[RemoteEntry]:
        """List directory contents.

        The current session drains result transfers produced by host commands but
        does not expose their payload back to callers. This method is kept as the
        stable service entry point so a future session enhancement can populate
        ``RemoteEntry`` instances without changing the API surface.
        """
        del path
        raise NotImplementedError(
            "Directory listing requires exposing host-command result payloads from "
            "KermitSession before entries can be parsed here."
        )

    def save_file(self, local_path: str | Path, remote_path: str) -> None:
        """Upload a local file to a remote folder using the existing transfer flow."""
        local = Path(local_path)
        remote_dir, remote_name = self._split_remote_path(remote_path)
        if local.name != remote_name:
            raise ValueError(
                "Remote filename must currently match the local filename; "
                "renamed uploads require a follow-up remote rename primitive."
            )
        self.client.upload_file(local, remote_dir=remote_dir)

    def remove_file(self, path: str) -> KermitPacket:
        """Remove a file or variable-like object from the calculator."""
        return self.client.run_rpl(RPLCommandBuilder.remove_remote_object(path))

    def create_variable(self, name: str, value: str, folder: str | None = None) -> KermitPacket:
        """Create a generic remote variable by storing an RPL value expression."""
        resolved_folder, resolved_name = self._resolve_name_and_folder(name, folder=folder)
        return self.client.run_rpl(
            RPLCommandBuilder.store_variable(resolved_name, value, folder=resolved_folder)
        )

    def create_equation(self, name: str, expression: str, folder: str | None = None) -> KermitPacket:
        """Create a remote equation object stored under the requested name."""
        resolved_folder, resolved_name = self._resolve_name_and_folder(name, folder=folder)
        return self.client.run_rpl(
            RPLCommandBuilder.store_equation(resolved_name, expression, folder=resolved_folder)
        )

    def create_constant(self, name: str, value: str, folder: str | None = None) -> KermitPacket:
        """Create a remote constant-like value stored under the requested name."""
        resolved_folder, resolved_name = self._resolve_name_and_folder(name, folder=folder)
        return self.client.run_rpl(
            RPLCommandBuilder.store_constant(resolved_name, value, folder=resolved_folder)
        )
