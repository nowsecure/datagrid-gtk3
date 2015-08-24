"""Data transformation utils."""

import datetime
import logging
import HTMLParser

from decimal import Decimal

import dateutil.parser
from gi.repository import Gtk

from datagrid_gtk3.utils import imageutils
from datagrid_gtk3.utils import dateutils
from datagrid_gtk3.utils import stringutils

logger = logging.getLogger(__name__)
_transformers = {}

__all__ = ('get_transformer', 'register_transformer')


def get_transformer(transformer_name):
    """Get transformation for the given name.

    :param str transformer_name: the name of the registered transformer
    :return: the transformer registered by transformer_name
    :rtype: callable
    """
    return _transformers.get(transformer_name, None)


def register_transformer(transformer_name, transformer):
    """Register a transformer.

    :param str transformer_name: the name to register the transformer
    :param callable transformer: the transformer to be registered
    """
    assert callable(transformer)
    _transformers[transformer_name] = transformer


def unregister_transformer(transformer_name):
    """Unregister a transformer.

    :param str transformer_name: the name to register the transformer
    :raise KeyError: if a transformer is not registered under the given name
    """
    del _transformers[transformer_name]


def transformer(transformer_name):
    """A decorator to easily register a decorator.

    Use this like::

        @transformer('transformer_name')
        def transformer_func(value):
            return do_something_with_value()

    :param str transformer_name: the name to register the transformer
    """
    def _wrapper(f):
        register_transformer(transformer_name, f)
        return f
    return _wrapper


###
# Default transformers
###


@transformer('string')
def string_transform(value, max_length=None, oneline=True,
                     decode_fallback=None):
    """String transformation.

    :param object value: the value that will be converted to
        a string
    :param int max_length: if not `None`, will be used to
        ellipsize the string if greater than that.
    :param bool oneline: if we should join all the lines together
        in one line
    :param callable decode_fallback: a callable to use
        to decode value in case it cannot be converted to unicode directly
    :return: the string representation of the value
    :rtype: str
    """
    if value is None:
        return '<NULL>'

    if isinstance(value, str):
        value = unicode(value, 'utf-8', 'replace')
    else:
        try:
            value = unicode(value)
        except UnicodeDecodeError:
            if decode_fallback is None:
                raise
            value = decode_fallback(value)

    # Replace non-printable characters on the string so the user will
    # know that there's something there even though it is not printable.
    value = stringutils.replace_non_printable(value)

    if oneline:
        value = u' '.join(v.strip() for v in value.splitlines() if v.strip())

    # Don't show more than max_length chars in treeview. Helps with performance
    if max_length is not None and len(value) > max_length:
        value = u'%s [...]' % (value[:max_length], )

    # At the end, if value is unicode, it needs to be converted to
    # an utf-8 encoded str or it won't be rendered in the treeview.
    return value.encode('utf-8')


@transformer('html')
def html_transform(value, max_length=None, oneline=True,
                   decode_fallback=None):
    """HTML transformation.

    :param object value: the escaped html that will be unescaped
    :param int max_length: if not `None`, will be used to
        ellipsize the string if greater than that.
    :param bool oneline: if we should join all the lines together
        in one line
    :param callable decode_fallback: a callable to use
        to decode value in case it cannot be converted to unicode directly
    :return: the html string unescaped
    :rtype: str
    """
    if value is None:
        return '<NULL>'

    html_parser = HTMLParser.HTMLParser()
    unescaped = html_parser.unescape(value)
    return string_transform(
        unescaped, max_length=max_length, oneline=oneline,
        decode_fallback=decode_fallback)


@transformer('boolean')
def boolean_transform(value):
    """Transform boolean values to a gtk stock image.

    :param bool value: the value to transform
    :return: a pixbuf representing the value's bool value
    :rtype: :class:`GdkPixbuf.Pixbuf`
    """
    img = Gtk.Image()
    # NOTE: should be STOCK_NO instead of STOCK_CANCEL but it looks
    # crappy in Lubuntu
    return img.render_icon(
        Gtk.STOCK_YES if value else Gtk.STOCK_CANCEL, Gtk.IconSize.MENU)


@transformer('bytes')
def bytes_transform(value):
    """Transform bytes into a human-readable value.

    :param int value: bytes to be humanized
    :returns: the humanized bytes
    :rtype: str
    """
    if value is None:
        return ''

    for suffix, factor in [
            ('PB', 1 << 50),
            ('TB', 1 << 40),
            ('GB', 1 << 30),
            ('MB', 1 << 20),
            ('kB', 1 << 10),
            ('B', 0)]:
        if value >= factor:
            value = '%.*f %s' % (1, float(value) / max(factor, 1), suffix)
            break
    else:
        raise ValueError('Unexpected value: %s' % (value, ))

    return value


@transformer('datetime')
def datetime_transform(value):
    """Transform datetime to ISO 8601 date format.

    :param value: the datatime object
    :type value: datetime.datetime
    :return: the datetime represented in ISO 8601 format
    :rtype: str
    """
    if value is None:
        return ''

    if isinstance(value, basestring):
        try:
            # Try to parse string as a date
            value = dateutil.parser.parse(value)
        except (OverflowError, TypeError, ValueError):
            pass

    # FIXME: Fix all places using 'datetime' for timestamp
    # (either as an int/long or as a convertable str)
    try:
        long_value = long(value)
    except (TypeError, ValueError):
        pass
    else:
        return timestamp_transform(long_value)

    if not isinstance(value, datetime.datetime):
        # Convert value to string even if it cannot be parsed as a datetime
        logger.warning('Not a datetime: %s', value)
        return str(value)

    return value.isoformat(' ')


@transformer('timestamp')
@transformer('timestamp_unix')
def timestamp_transform(value, date_only=False):
    """Transform timestamp to ISO 8601 date format.

    :param int value: Unix timestamp
    :param bool date_only: if we should format only the date part,
         ignoring the time
    :return: the datetime represented in ISO 8601 format
    :rtype: str
    """
    if value is None:
        return ''

    try:
        dt = datetime.datetime.utcfromtimestamp(value)
    except (TypeError, ValueError):
        # Convert value to string even if it cannot be parsed as a timestamp
        logger.warning('Not a timestamp: %s', value)
        return str(value)

    if date_only:
        return dt.date().isoformat()
    else:
        return dt.isoformat(' ')


@transformer('timestamp_ms')
@transformer('timestamp_unix_ms')
def timestamp_ms_transform(value):
    """Transform timestamp in milliseconds to ISO 8601 date format.

    :param int value: Unix timestamp in milliseconds
    :return: the datetime represented in ISO 8601 format
    :rtype: str
    """
    if value is None:
        return ''

    return timestamp_transform(
        dateutils.normalize_timestamp(value, 'timestamp_unix_ms'))


@transformer('timestamp_Ms')
@transformer('timestamp_unix_Ms')
def timestamp_Ms_transform(value):
    """Transform timestamp in microseconds to ISO 8601 date format.

    :param int value: Unix timestamp in microseconds
    :return: the datetime represented in ISO 8601 format
    :rtype: str
    """
    if value is None:
        return ''

    return timestamp_transform(
        dateutils.normalize_timestamp(value, 'timestamp_unix_Ms'))


@transformer('timestamp_ios')
@transformer('timestamp_apple')
def timestamp_apple_transform(value):
    """Transform apple timestamp to ISO 8601 date format.

    Apple timestamps (e.g. those used on iOS) start at 2001-01-01.

    :param int value: apple timestamp
    :return: the datetime represented in ISO 8601 format
    :rtype: str
    """
    if value is None:
        return ''

    return timestamp_transform(
        dateutils.normalize_timestamp(value, 'timestamp_apple'))


@transformer('timestamp_webkit')
def timestamp_webkit_transform(value):
    """Transform WebKit timestamp to ISO 8601 date format.

    WebKit timestamps are expressed in microseconds and
    start at 1601-01-01.

    :param int value: WebKit timestamp
    :return: the datetime represented in ISO 8601 format
    :rtype: str
    """
    if value is None:
        return ''

    return timestamp_transform(
        dateutils.normalize_timestamp(value, 'timestamp_webkit'))


@transformer('timestamp_julian')
def timestamp_julian_transform(value, date_only=False):
    """Transform Julian timestamp to ISO 8601 date format.

    Julian timestamps are the number of days that has passed since
    noon Universal Time on January 1, 4713 BCE.

    :param int value: Julian timestamp in days
    :param bool date_only: if we should format only the date part,
         ignoring the time
    :return: the datetime represented in ISO 8601 format
    :rtype: str
    """
    if value is None:
        return ''

    return timestamp_transform(
        dateutils.normalize_timestamp(value, 'timestamp_julian'),
        date_only=date_only)


@transformer('timestamp_julian_date')
def timestamp_julian_date_transform(value):
    """Transform julian timestamp to ISO 8601 date format.

    Julian timestamps are the number of days that has passed since
    noon Universal Time on January 1, 4713 BCE.

    :param int value: Julian timestamp
    :return: the date represented in ISO 8601 format
    :rtype: str
    """
    if value is None:
        return ''

    return timestamp_julian_transform(value, date_only=True)


@transformer('timestamp_midnight')
def timestamp_midnight_transform(value):
    """Transform midnight timestamp to ISO 8601 time format.

    Midnight timestamp is the count in seconds of the time that
    has passed since midnight.

    :param int value: midnight timestamp in seconds
    :return: the time represented in ISO 8601 format
    :rtype: str
    """
    if value is None:
        return ''

    dt = datetime.datetime.min + datetime.timedelta(0, value)
    return dt.time().isoformat()


@transformer('timestamp_midnight_ms')
def timestamp_midnight_ms_transform(value):
    """Transform midnight timestamp in milliseconds to ISO 8601 time format.

    Midnight timestamp is the count in seconds of the time that
    has passed since midnight.

    :param int value: midnight timestamp in milliseconds
    :return: the time represented in ISO 8601 format
    :rtype: str
    """
    if value is None:
        return ''

    return timestamp_midnight_transform(value / 10 ** 3)


@transformer('timestamp_midnight_Ms')
def timestamp_midnight_Ms_transform(value):
    """Transform midnight timestamp in microsecond to ISO 8601 time format.

    Midnight timestamp is the count in seconds of the time that
    has passed since midnight.

    :param int value: midnight timestamp in microseconds
    :return: the time represented in ISO 8601 format
    :rtype: str
    """
    if value is None:
        return ''

    return timestamp_midnight_transform(value / 10 ** 6)


@transformer('image')
def image_transform(path, size=24, fill_image=True, draw_border=False,
                    draft=False, load_on_thread=False):
    """Render path into a pixbuf.

    :param str path: the image path or `None` to use a fallback image
    :param int size: the size to resize the image. It will be resized
        to fit a square of (size, size)
    :param bool fill_image: if we should fill the image with a transparent
        background to make a smaller image be at least a square of
        (size, size), with the real image at the center.
    :param bool draw_border: if we should add a border on the image
    :param bool draft: if we should load the image as a draft. This
        trades a little quality for a much higher performance.
    :param bool load_on_thread: if we should load the image on another
        thread. This will make a placeholder be returned the first
        time this method is called.
    :returns: the resized pixbuf
    :rtype: :class:`GdkPixbuf.Pixbuf`
    """
    cm = imageutils.ImageCacheManager.get_default()
    return cm.get_image(path, size, fill_image, draw_border,
                        draft, load_on_thread)


@transformer('degree_decimal_str')
def degree_decimal_str_transform(value, length=8):
    """Transform degree decimal string to a numeric value.

    The string is expected to have <length> digits, if less digits are found,
    it will be prefixed with zeroes as needed.

    :param value: Degrees encoded as a string with digits
    :type value: str
    :param length: Maximum expected string length
    :type length: int

    """
    assert isinstance(value, basestring), 'String value expected'
    assert value.isdigit(), 'All characters expected to be digits'
    assert len(value) <= length, \
        'String length expected to be {} or less'.format(length)
    value = value.zfill(length)

    # Add decimal point at the expected location
    value = '{}.{}'.format(value[:2], value[2:])

    # Remove non-significant leading zeroes
    value = Decimal(value)
    return str(value)
