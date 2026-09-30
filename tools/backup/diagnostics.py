"""Bounded in-memory tool errors mapped to fixed public diagnostic codes."""
import threading

LIMIT = 64 * 1024


class PrivateErrors:
    def __init__(self, stream):
        self.stream = stream
        self.captured = bytearray()
        self.thread = threading.Thread(target=self._drain, daemon=True)
        self.thread.start()

    def _drain(self):
        try:
            while block := self.stream.read(4096):
                remaining = LIMIT - len(self.captured)
                if remaining > 0:
                    self.captured.extend(block[:remaining])
        except (OSError, ValueError):
            pass

    def finish(self):
        self.thread.join(timeout=10)
        if self.thread.is_alive():
            self.stream.close()
            self.thread.join(timeout=1)

    def code(self, stage):
        message = bytes(self.captured).decode(errors='replace').lower()
        for needle, category in (
            ('permission denied', 'permission_denied'),
            ('row-level security', 'row_security_restricted'),
            ('certificate verify failed', 'certificate_failed'),
            ('could not open root certificate', 'certificate_bundle_unavailable'),
            ('password authentication failed', 'authentication_failed'),
            ('connection refused', 'connection_refused'),
            ('server version mismatch', 'version_mismatch'),
            ('could not translate host name', 'dns_failed'),
            ('timeout expired', 'connection_timeout'),
            ('channel binding', 'channel_binding_failed'),
            ('unrecognized configuration parameter', 'configuration_failed'),
            ('unrecognized option', 'option_invalid'),
            ('compression', 'compression_invalid'),
            ('no matching schemas', 'schema_not_found'),
            ('read-only transaction', 'transaction_read_only'),
            ('query failed', 'catalog_query_failed'),
            ('read-only file system', 'filesystem_read_only'),
            ('network is unreachable', 'network_unavailable'),
        ):
            if needle in message:
                return 'postgres_' + stage + '_' + category
        return 'postgres_' + stage + '_failed'

    def clues(self):
        # Fixed words only: never echo a provider line, query, name or value.
        message = bytes(self.captured).decode(errors='replace').lower()
        return [word for word in ('pg_dump:', 'docker:', 'error', 'query', 'option',
                'invalid', 'compression', 'version', 'connection', 'certificate',
                'file', 'directory', 'permission', 'transaction', 'read-only',
                'configuration', 'timeout', 'schema', 'network', 'failed') if word in message]
