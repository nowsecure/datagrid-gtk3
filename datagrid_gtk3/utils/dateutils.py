"""Datetime utilities."""

import datetime
import logging

import dateutil.parser

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
_ms_norm_inv = lambda v: v * 10 ** 3

_Ms_norm = lambda v: v / 10 ** 6
_Ms_norm_inv = lambda v: v * 10 ** 6

_apple_norm = lambda v: v + _APPLE_TIMESTAMP_OFFSET
_apple_norm_inv = lambda v: v - _APPLE_TIMESTAMP_OFFSET

_webkit_norm = lambda v: _Ms_norm(v) - _WEBKIT_TIMESTAMP_OFFSET
_webkit_norm_inv = lambda v: _Ms_norm_inv(v + _WEBKIT_TIMESTAMP_OFFSET)

_julian_norm = lambda v: (
    (v - _UNIX_ZERO_POINT_IN_JULIAN_DAYS) * _SECONDS_IN_A_DAY)
_julian_norm_inv = lambda v: (
    (v / _SECONDS_IN_A_DAY) + _UNIX_ZERO_POINT_IN_JULIAN_DAYS)


(_NORM_POS,
 _NORM_INV_POS) = range(2)
_normalizations = dict(
    timestamp=(_base_norm, _base_norm),
    timestamp_unix=(_base_norm, _base_norm),
    timestamp_ms=(_ms_norm, _ms_norm_inv),
    timestamp_unix_ms=(_ms_norm, _ms_norm_inv),
    timestamp_Ms=(_Ms_norm, _Ms_norm_inv),
    timestamp_unix_Ms=(_Ms_norm, _Ms_norm_inv),
    timestamp_apple=(_apple_norm, _apple_norm_inv),
    timestamp_ios=(_apple_norm, _apple_norm_inv),
    timestamp_webkit=(_webkit_norm, _webkit_norm_inv),
    timestamp_julian=(_julian_norm, _julian_norm_inv),
    timestamp_julian_date=(_julian_norm, _julian_norm_inv),
)


class InvalidDateFormat(Exception):

    """Invalid date format exception."""


def supported_timestamp_formats():
    """Get a list of supported timestamp formats.

    Those are the supported timestamp formats to be used on
    :func:`.normalize_timestamp`.

    :return: a list of supported timestamp formats
    :rtype: list of strings
    """
    return _normalizations.keys()


def normalize_timestamp(value, timestamp_format, inverse=False):
    """Normalize timestamp to unix.

    Receives a timestamp in any of the supported formats
    (e.g. 'timestamp_apple', 'timestamp_webkit', 'timestamp_julian', etc)
    and convert it to unix timestamp.

    :param long value: the timestamp
    :param str timestamp_format: the timestamp format
    :param bool inverse: if we should calculate the inverse of the
        normalization, that is, value is already a timestamp and we
        want it in the given timestamp_format.
    :return: the timestamp normalized
    :rtype: long
    """
    if timestamp_format not in supported_timestamp_formats():
        logger.warning(
            'Timestamp format "%s" not supported.', timestamp_format)
        return value

    pos = _NORM_INV_POS if inverse else _NORM_POS
    return _normalizations[timestamp_format][pos](value)


def parse_string(string):
    """Parse the string to a datetime object.

    :param str string: The string to parse
    :rtype: `datetime.datetime`
    :raises: :exc:`InvalidDateFormat` when date format is invalid
    """
    try:
        # Try to parse string as a date
        value = dateutil.parser.parse(string)
    except (OverflowError, TypeError, ValueError):
        raise InvalidDateFormat("Invalid date format %r" % (string, ))

    return value
