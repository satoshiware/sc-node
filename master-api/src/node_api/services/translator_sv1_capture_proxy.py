from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from node_api.services.translator_candidate_blocks_store import TranslatorCandidateBlocksStore
from node_api.services.translator_candidate_reconstruction import Sv1CandidateReconstructor
from node_api.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def channel_id_map_from_monitoring(settings: Settings) -> dict[str, int]:
    base_url = settings.translator_monitoring_base_url
    if not base_url:
        return {}
    request = Request(f"{base_url}/api/v1/server/channels", method="GET")
    try:
        with urlopen(request, timeout=settings.translator_monitoring_timeout_secs) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        logger.exception("Failed to read translator monitoring channel map")
        return {}

    rows: list[Any]
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        if isinstance(data, dict):
            rows = data.get("items") or data.get("channels") or []
        else:
            rows = data if isinstance(data, list) else []
    else:
        rows = payload if isinstance(payload, list) else []

    out: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        identity = row.get("user_identity") or row.get("worker_identity")
        channel_id = row.get("channel_id")
        if isinstance(identity, str) and isinstance(channel_id, int):
            out[identity] = channel_id
    return out


class TranslatorSv1CaptureProxy:
    def __init__(self, settings: Settings) -> None:
        if not settings.translator_capture_upstream_host:
            raise ValueError("TRANSLATOR_CAPTURE_UPSTREAM_HOST is required")
        if not settings.translator_capture_upstream_port:
            raise ValueError("TRANSLATOR_CAPTURE_UPSTREAM_PORT is required")
        self.settings = settings
        self.reconstructor = Sv1CandidateReconstructor()
        self.store = TranslatorCandidateBlocksStore.from_settings(settings)
        self._session_seq = 0

    async def serve_forever(self) -> None:
        server = await asyncio.start_server(
            self._handle_client,
            self.settings.translator_capture_listen_host,
            self.settings.translator_capture_listen_port,
        )
        async with server:
            await server.serve_forever()

    async def _handle_client(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        self._session_seq += 1
        session_id = f"sv1-{self._session_seq}"
        upstream_reader, upstream_writer = await asyncio.open_connection(
            self.settings.translator_capture_upstream_host,
            self.settings.translator_capture_upstream_port,
        )
        await asyncio.gather(
            self._pipe(
                session_id,
                client_reader,
                upstream_writer,
                parse_direction=True,
            ),
            self._pipe(
                session_id,
                upstream_reader,
                client_writer,
                parse_direction=True,
            ),
        )

    async def _pipe(
        self,
        session_id: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        parse_direction: bool,
    ) -> None:
        buffer = b""
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()
                if parse_direction:
                    buffer = self._parse_buffer(session_id, buffer + chunk)
        except Exception:
            logger.exception("SV1 capture proxy pipe failed")
        finally:
            writer.close()
            await writer.wait_closed()

    def _parse_buffer(self, session_id: str, buffer: bytes) -> bytes:
        *lines, tail = buffer.split(b"\n")
        for line in lines:
            self._parse_line(session_id, line)
        return tail

    def _parse_line(self, session_id: str, line: bytes) -> None:
        try:
            mapping = channel_id_map_from_monitoring(self.settings)
            session = self.reconstructor.sessions.get(session_id)
            channel_id = None
            if session is not None and session.worker_identity is not None:
                channel_id = mapping.get(session.worker_identity)
            candidate = self.reconstructor.process_line(
                session_id,
                line,
                received_time=int(time.time()),
                channel_id=channel_id,
            )
            if candidate is not None and candidate.is_block_found:
                self.store.insert_event(candidate.store_event())
        except Exception:
            logger.exception("SV1 capture proxy parse/reconstruction failed")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    proxy = TranslatorSv1CaptureProxy(get_settings())
    asyncio.run(proxy.serve_forever())


if __name__ == "__main__":
    main()
