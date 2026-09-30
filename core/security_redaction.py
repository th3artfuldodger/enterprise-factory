"""Central secret redaction for logs and admin-safe configuration views."""
from __future__ import annotations

import logging
import re
import traceback
from typing import Any

_REDACTED = '<redacted>'
_SECRET_NAME = re.compile(r'(?:api[_-]?key|secret|token|password|passwd|private[_-]?key|signing[_-]?key|credential|authorization|cookie|session|database[_-]?url|dsn)', re.I)
_PATTERNS = [
    re.compile(r'(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+'),
    re.compile(r'\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b'),
    re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{10,}\b'),
    re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    re.compile(r'\bAIzaSy[0-9A-Za-z_-]{33}\b'),
    re.compile(r'\bsk-[A-Za-z0-9_-]{16,}\b'),
    re.compile(r'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b'),
    re.compile(r'(?i)([?&](?:token|api_key|key|secret|password|access_token)=)[^&\s]+'),
    re.compile(r'(?i)(\b(?:token|api_key|secret|password|access_token|private_key|database_url|dsn)\s*[:=]\s*)[^\s,;]+'),
    re.compile(r'(?i)([a-z][a-z0-9+.-]*://[^:/\s]+:)[^@/\s]+(?=@)'),
]


def redact_text(value: Any) -> str:
    text = str(value)
    for rx in _PATTERNS:
        if rx.groups:
            text = rx.sub(lambda m: f'{m.group(1)}{_REDACTED}', text)
        else:
            text = rx.sub(_REDACTED, text)
    return text


def redact_structure(value: Any, *, key_name: str = '') -> Any:
    if key_name and _SECRET_NAME.search(str(key_name)):
        if value in (None, '', False):
            return value
        return '<configured>'
    if isinstance(value, dict):
        return {str(k): redact_structure(v, key_name=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_structure(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_structure(v) for v in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


def _redact_log_arg(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_log_arg(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_log_arg(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact_log_arg(v) for v in value)
    return value


def _redact_record(record: logging.LogRecord) -> None:
    # Uvicorn's AccessFormatter does not format record.msg normally: it unpacks
    # record.args into (client_addr, method, full_path, http_version, status_code).
    # Clearing args after eager rendering breaks every access-log line. Preserve
    # that structured tuple while still redacting each value, especially query
    # strings that may contain tokens.
    if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) >= 5:
        try:
            record.msg = redact_text(record.msg)
            record.args = _redact_log_arg(record.args)
        except Exception:
            pass
    else:
        try:
            rendered = record.getMessage()
            record.msg = redact_text(rendered)
            record.args = ()
        except Exception:
            try:
                record.msg = redact_text(record.msg)
                if record.args:
                    record.args = _redact_log_arg(record.args)
            except Exception:
                pass
    if record.exc_info:
        try:
            # Format once, redact the exception text, then clear exc_info so a later
            # formatter cannot append the original secret-bearing exception string.
            record.exc_text = redact_text(''.join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        except Exception:
            pass


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        _redact_record(record)
        return True


_installed = False


def install_secret_redaction() -> None:
    global _installed
    if _installed:
        return
    old_factory = logging.getLogRecordFactory()

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = old_factory(*args, **kwargs)
        _redact_record(record)
        return record

    logging.setLogRecordFactory(factory)
    _installed = True
