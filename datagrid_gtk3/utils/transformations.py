"""Data transformation utils."""

import datetime
import os

from gi.repository import (
    GdkPixbuf,
    Gtk,
)
from PIL import Image

from datagrid_gtk3.utils import imageutils

_transformers = {}
_MEDIA_FILES = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), os.pardir, "data", "media")

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
def string_transform(value, max_length=None, decode_fallback=None):
    """String transformation.

    :param object value: the value that will be converted to
        a string
    :param int max_length: if not `None`, will be used to
        ellipsize the string if greater than that.
    :param str encoding_hint: the encode to use on the string
    :param callable decode_fallback: a callable to use
        to decode value in case it cannot be converted to unicode directly
    :return: the string representation of the value (
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

    value = u' '.join(value.splitlines())
    # Don't show more than max_length chars in treeview. Helps with performance
    if max_length is not None and len(value) > max_length:
        value = u'%s [...]' % (value[:max_length], )

    # At the end, if value is unicode, it needs to be converted to
    # an utf-8 encoded str or it won't be rendered in the treeview.
    return value.encode('utf-8')


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
    """Transform timestamps to ISO 8601 date format.

    :param int value: Unix timestamp
    :return: the newly created datetime object
    :rtype: datetime.datetime
    """
    try:
        dt = datetime.datetime.utcfromtimestamp(value)
    except ValueError:
        return value

    return dt.isoformat()


@transformer('image')
def image_transform(path, size=24, draw_border=False,
                    border_size=6, shadow_size=6, shadow_offset=2):
    """Render path into a pixbuf.

    :param str path: the image path or `None` to use a fallback image
    :param int size: the size to resize the image. It will be resized
        to fit a square of (size, size)
    :param bool draw_border: if we should add a border on the image
    :param border_size: the size of the border (if drawing border)
    :param shadow_size: the size of the drop shadow (if drawing border)
    :param shadow_offset: the offset of the drop shadow (if drawing border)
    :returns: the resized pixbuf
    :rtype: :class:`GdkPixbuf.Pixbuf`
    """
    fallback = os.path.join(_MEDIA_FILES, ('icons/image.png'))
    path = path or fallback

    try:
        image = Image.open(path)
        image.load()
    except IOError:
        # If the image is damaged for some reason, use fallback
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

    pixbuf = imageutils.image2pixbuf(image)
    width = pixbuf.get_width()
    height = pixbuf.get_height()

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
