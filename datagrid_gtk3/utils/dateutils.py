"""Datetime utilities."""

import datetime
import logging

logger = logging.getLogger(__name__)
__all__ = ('supported_timestamp_formats', 'normalize_timestamp')

# Total seconds in a day
_SECONDS_IN_A_DAY = int(
    (datetime.datetime(1970, 1, 2) -
     datetime.datetime(1970, 1, 1)).total_seconds())

# iOS timestamps start from 2001-01-01
_APPLE_TIMESTAMP_OFFSET = int(
    (datetime.datetime(2001, 1, 1) -
     datetime.datetime(1970, 1, 1)).total_seconds())

# Webkit timestamps start at 1601-01-01
_WEBKIT_TIMESTAMP_OFFSET = int(
    (datetime.datetime(1970, 1, 1) -
     datetime.datetime(1601, 1, 1)).total_seconds())

# Unix epoch zero-point (1970-01-01) in Julian days
_UNIX_ZERO_POINT_IN_JULIAN_DAYS = 2440587.5


_base_norm = lambda v: v
_ms_norm = lambda v: v / 10 ** 3
_Ms_norm = lambda v: v / 10 ** 6
_apple_norm = lambda v: v + _APPLE_TIMESTAMP_OFFSET
_webkit_norm = lambda v: _Ms_norm(v) - _WEBKIT_TIMESTAMP_OFFSET
_julian_norm = lambda v: (
    (v - _UNIX_ZERO_POINT_IN_JULIAN_DAYS) * _SECONDS_IN_A_DAY)


_normalizations = dict(
    timestamp=_base_norm,
    timestamp_unix=_base_norm,
    timestamp_ms=_ms_norm,
    timestamp_unix_ms=_ms_norm,
    timestamp_Ms=_Ms_norm,
    timestamp_unix_Ms=_Ms_norm,
    timestamp_apple=_apple_norm,
    timestamp_ios=_apple_norm,
    timestamp_webkit=_webkit_norm,
    timestamp_julian=_julian_norm,
    timestamp_julian_date=_julian_norm,
)


def supported_timestamp_formats():
    """Get a list of supported timestamp formats.

    Those are the supported timestamp formats to be used on
    :func:`.normalize_timestamp`.

    :return: a list of supported timestamp formats
    :rtype: list of strings
    """
    return _normalizations.keys()


def normalize_timestamp(value, timestamp_format):
    """Normalize timestamp to unix.

    Receives a timestamp in any of the supported formats
    (e.g. 'timestamp_apple', 'timestamp_webkit', 'timestamp_julian', etc)
    and convert it to unix timestamp.

    :param long value: the timestamp
    :param str timestamp_format: the timestamp format
    :return: the timestamp normalized
    :rtype: long
    """
    if timestamp_format not in supported_timestamp_formats():
        logger.warning(
            'Timestamp format "%s" not supported.', timestamp_format)
        return value

    return _normalizations[timestamp_format](value)
