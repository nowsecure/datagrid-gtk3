"""Data transformation utils."""

import datetime
import logging
import HTMLParser

import dateutil.parser
from gi.repository import (
    GdkPixbuf,
    Gtk,
)
from PIL import Image

from datagrid_gtk3.utils import imageutils

logger = logging.getLogger(__name__)
_transformers = {}

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
        # FIXME GTK3: On gtk2, set_text would raise TypeError when
        # trying to set_text with a string containing a null (\x00)
        # character. gtk3 will allow that, but if the null character is
        # at the beginning of it, it will be set as empty.
        if value.startswith('\x00'):
            value = repr(value)[1:-1]

        value = unicode(value, 'utf-8', 'replace')
    else:
        try:
            value = unicode(value)
        except UnicodeDecodeError:
            if decode_fallback is None:
                raise
            value = decode_fallback(value)

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

    return value.isoformat()


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
        dt = dt.date()

    return dt.isoformat()


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

    return timestamp_transform(value / 10 ** 3)


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

    return timestamp_transform(value / 10 ** 6)


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

    return timestamp_transform(value + _APPLE_TIMESTAMP_OFFSET)


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

    return timestamp_transform(value / 10 ** 6 - _WEBKIT_TIMESTAMP_OFFSET)


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
        (value - _UNIX_ZERO_POINT_IN_JULIAN_DAYS) * _SECONDS_IN_A_DAY,
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
                    border_size=6, shadow_size=6, shadow_offset=2):
    """Render path into a pixbuf.

    :param str path: the image path or `None` to use a fallback image
    :param int size: the size to resize the image. It will be resized
        to fit a square of (size, size)
    :param bool fill_image: if we should fill the image with a transparent
        background to make a smaller image be at least a square of
        (size, size), with the real image at the center.
    :param bool draw_border: if we should add a border on the image
    :param border_size: the size of the border (if drawing border)
    :param shadow_size: the size of the drop shadow (if drawing border)
    :param shadow_offset: the offset of the drop shadow (if drawing border)
    :returns: the resized pixbuf
    :rtype: :class:`GdkPixbuf.Pixbuf`
    """
    path = path or ''
    try:
        image = Image.open(path)
        image.load()
    except IOError:
        # Size will always be rounded to the next value. After 48, the next is
        # 256 and we don't want something that big here.
        fallback_size = min(size, 48)
        # If the image is damaged for some reason, use fallback for
        # its mimetype. Maybe the image is not really an image
        # (it could be a video, a plain text file, etc)
        fallback = imageutils.get_icon_for_file(path, fallback_size)
        image = Image.open(fallback)

    image.thumbnail((size, size), Image.BICUBIC)

    if draw_border:
        image = imageutils.add_border(image, border_size=border_size)
        image = imageutils.add_drop_shadow(
            image, border_size=shadow_size,
            offset=(shadow_offset, shadow_offset))

        size += border_size * 2
        size += shadow_size * 2
        size += shadow_offset
    else:
        # FIXME: There's a bug on PIL where image.thumbnail modifications will
        # be lost for some images when saving it the way we do on image2pixbuf
        # (even image.copy().size != image.size when it was resized).
        # Adding a border of size 0 will make it at least be pasted to a new
        # image (which didn't have its thumbnail method called), working around
        # this issue.
        image = imageutils.add_border(image, 0)

    pixbuf = imageutils.image2pixbuf(image)
    width = pixbuf.get_width()
    height = pixbuf.get_height()

    if not fill_image:
        return pixbuf

    # Make sure the image is on the center of the image_max_size
    square_pic = GdkPixbuf.Pixbuf.new(
        GdkPixbuf.Colorspace.RGB, True, pixbuf.get_bits_per_sample(),
        size, size)
    # Fill with transparent white
    square_pic.fill(0xffffff00)

    dest_x = (size - width) / 2
    dest_y = (size - height) / 2
    pixbuf.copy_area(0, 0, width, height, square_pic, dest_x, dest_y)

    return square_pic
