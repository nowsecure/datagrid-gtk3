"""Image utilities

Some general image utilities using PIL.
"""

import Queue
import collections
import io
import mimetypes
import os
import struct
import threading

from gi.repository import (
    GLib,
    GObject,
    GdkPixbuf,
    Gtk,
    Gdk,
)
from PIL import Image, ImageFilter

mimetypes.init()
# Generating a drop shadow is an expensive operation. Keep a cache
# of already generated drop shadows so they can be reutilized
_drop_shadows_cache = {}

_icon_theme = Gtk.IconTheme.get_default()
_icon_filename_cache = {}


def get_icon_filename(choose_list, size):
    """Get a theme icon filename.

    :param list choose_list: the list of icon names to choose from.
        The first existing icon will be returned.
    :param int size: size of the icon, to be passed to
        :class:`Gtk.IconTheme.choose_icon`
    :return: the path to the icon
    :rtype: str
    """
    icon = _icon_theme.choose_icon(choose_list, size,
                                   Gtk.IconLookupFlags.NO_SVG)
    return icon and icon.get_filename()


def get_icon_for_file(filename, size):
    """Get icon for filename mimetype.

    Analyze filename to get its mimetype and return the path of an
    icon representing it.

    :param str filename: path of the file to be alalyzed
    :param int size: size of the icon, to be passed to
        :class:`Gtk.IconTheme.choose_icon`
    :return: the path to the icon
    :rtype: str
    """
    if os.path.isdir(filename):
        # mimetypes.guess_type doesn't work for folders
        guessed_mime = 'folder/folder'
    else:
        # Fallback to unknown if mimetypes wasn't able to guess it
        guessed_mime = mimetypes.guess_type(filename)[0] or 'unknown/unknown'

    if guessed_mime in _icon_filename_cache:
        return _icon_filename_cache[guessed_mime]

    # Is there any value returned by guess_type that would have no /?
    mimetype, details = guessed_mime.split('/')

    # FIXME: guess_type mimetype is formatted differently from what
    # Gtk.IconTheme expects. We are trying to improve matching here.
    # Is there a better way for doing this?
    icon_list = ['%s-%s' % (mimetype, details), details, mimetype]
    if mimetype == 'application':
        icon_list.append('application-x-%s' % (details, ))
    icon_list.append('%s-x-generic' % (mimetype, ))
    icon_list.append('unknown')

    icon_filename = get_icon_filename(icon_list, size)
    _icon_filename_cache[guessed_mime] = icon_filename
    return icon_filename


def image2pixbuf(image):
    """Convert a PIL image to a pixbuf.

    :param image: the image to convert
    :type image: `PIL.Image`
    :returns: the newly created pixbuf
    :rtype: `GdkPixbuf.Pixbuf`
    """
    with io.BytesIO() as f:
        image.save(f, 'png')
        loader = GdkPixbuf.PixbufLoader.new_with_type('png')
        loader.write(f.getvalue())
        pixbuf = loader.get_pixbuf()
        loader.close()

    return pixbuf


def add_border(image, border_size=5,
               background_color=(0xff, 0xff, 0xff, 0xff)):
    """Add a border on the image.

    :param image: the image to add the border
    :type image: `PIL.Image`
    :param int border_size: the size of the border
    :param tuple background_color: the color of the border as a
        tuple containing (r, g, b, a) information
    :returns: the new image with the border
    :rtype: `PIL.Image`
    """
    width = image.size[0] + border_size * 2
    height = image.size[1] + border_size * 2

    try:
        image.convert("RGBA")
        image_parts = image.split()
        mask = image_parts[3] if len(image_parts) == 4 else None
    except IOError:
        mask = None

    border = Image.new("RGBA", (width, height), background_color)
    border.paste(image, (border_size, border_size), mask=mask)

    return border


def add_drop_shadow(image, iterations=3, border_size=2, offset=(2, 2),
                    shadow_color=(0x00, 0x00, 0x00, 0xff)):
    """Add a border on the image.

    Based on this receipe::

        http://en.wikibooks.org/wiki/Python_Imaging_Library/Drop_Shadows

    :param image: the image to add the drop shadow
    :type image: `PIL.Image`
    :param int iterations: number of times to apply the blur filter
    :param int border_size: the size of the border to add to leave
        space for the shadow
    :param tuple offset: the offset of the shadow as (x, y)
    :param tuple shadow_color: the color of the shadow as a
        tuple containing (r, g, b, a) information
    :returns: the new image with the drop shadow
    :rtype: `PIL.Image`
    """
    width  = image.size[0] + abs(offset[0]) + 2 * border_size
    height = image.size[1] + abs(offset[1]) + 2 * border_size

    key = (width, height, iterations, border_size, offset, shadow_color)
    existing_shadow = _drop_shadows_cache.get(key)
    if existing_shadow:
        shadow = existing_shadow.copy()
    else:
        shadow = Image.new('RGBA', (width, height),
                           (0xff, 0xff, 0xff, 0x00))

        # Place the shadow, with the required offset
        # if < 0, push the rest of the image right
        shadow_lft = border_size + max(offset[0], 0)
        # if < 0, push the rest of the image down
        shadow_top  = border_size + max(offset[1], 0)

        shadow.paste(shadow_color,
                     [shadow_lft, shadow_top,
                      shadow_lft + image.size[0],
                      shadow_top + image.size[1]])

        # Apply the BLUR filter repeatedly
        for i in range(iterations):
            shadow = shadow.filter(ImageFilter.BLUR)

        _drop_shadows_cache[key] = shadow.copy()

    # Paste the original image on top of the shadow
    # if the shadow offset was < 0, push right
    img_lft = border_size - min(offset[0], 0)
    # if the shadow offset was < 0, push down
    img_top = border_size - min(offset[1], 0)

    shadow.paste(image, (img_lft, img_top))
    return shadow


class ImageCacheManager(GObject.GObject):

    """Helper to cache image transformations.

    Image transformations can be expensive and datagrid views will
    ask for them a lot. This will help by:

        * Caching the mru images so the pixbuf is ready to be used,
          without having to load and transform it again

        * Do the transformations on another thread so larger images
          transformation will not disturb the main one.

    """

    __gsignals__ = {
        'image-loaded': (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    _instance = None

    MAX_CACHE_SIZE = 200
    IMAGE_BORDER_SIZE = 6
    IMAGE_SHADOW_SIZE = 6
    IMAGE_SHADOW_OFFSET = 2

    def __init__(self):
        """Initialize the image cache manager object."""
        super(ImageCacheManager, self).__init__()

        self._lock = threading.Lock()
        self._cache = {}
        self._placeholders = {}
        self._mru = collections.deque([], self.MAX_CACHE_SIZE)
        self._waiting = set()
        # We are using a LifoQueue instead of a Queue to load the most recently
        # used image. For example, when scrolling the treeview, you will want
        # the visible rows to be loaded before the ones that were put in the
        # queue during the process.
        self._queue = Queue.LifoQueue()

        self._task = threading.Thread(target=self._transform_task)
        self._task.daemon = True
        self._task.start()

    ###
    # Public
    ###

    @classmethod
    def get_default(cls):
        """Get the singleton default cache manager.

        :return: the cache manager
        :rtype: :class:`ImageCacheManager`
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_image(self, path, size=24, fill_image=True, draw_border=False,
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
        params = (path, size, fill_image, draw_border, draft)

        with self._lock:
            # We want this params to be the last element on the deque (meaning
            # it will be the most recently used item). Since we will append it
            # bellow, if it were already in the deque, make sure to remove it
            if params in self._mru:
                self._mru.remove(params)
            # When self._mru reaches its maxlen, the least recently used
            #element (the position 0 in case of an append) will be removed
            self._mru.append(params)

            pixbuf = self._cache.get(params, None)
            # The pixbuf is on cache
            if pixbuf is not None:
                return pixbuf

            # The pixbuf is not on cache, but we don't want to
            # load it on a thread
            if not load_on_thread:
                pixbuf = self._transform_image(*params)
                # If no pixbuf, let the fallback image be returned
                if pixbuf:
                    self._cache_pixbuf(params, pixbuf)
                    return pixbuf
            elif params not in self._waiting:
                self._waiting.add(params)
                self._queue.put(params)

        # Size will always be rounded to the next value. After 48, the
        # next is 256 and we don't want something that big here.
        fallback_size = min(size, 48)
        fallback = get_icon_for_file(path or '', fallback_size)

        placeholder_key = (fallback, ) + tuple(params[1:])
        placeholder = self._placeholders.get(placeholder_key, None)
        if placeholder is None:
            # If the image is damaged for some reason, use fallback for
            # its mimetype. Maybe the image is not really an image
            # (it could be a video, a plain text file, etc)
            placeholder = self._transform_image(
                fallback, fallback_size, *params[2:])
            self._placeholders[placeholder_key] = placeholder
            # Make the placeholder the initial value for the image. If the
            # loading fails, it will be used as the pixbuf for the image.
            self._cache[params] = placeholder

        return placeholder

    ###
    # Private
    ###

    def _cache_pixbuf(self, params, pixbuf):
        """Cache the pixbuf.

        Cache the pixbuf generated by the given params.
        This will also free any item any item that is not needed
        anymore (the least recently used items after the
        cache > :attr:`.MAX_CACHE_SIZE`) from the cache.

        :param tuple params: the params used to do the image
            transformation. Will be used as the key for the cache dict
        :param pixbuf: the pixbuf to be cached.
        :type pixbuf: :class:`GdkPixbuf.Pixbuf`
        """
        self._cache[params] = pixbuf
        self._waiting.discard(params)

        # Free anything that is not needed anymore from the memory
        for params in set(self._cache) - set(self._mru):
            del self._cache[params]

    def _transform_task(self):
        """Task responsible for doing image transformations.

        This will run on another thread, checking the queue for any
        new images, transforming and caching them after.

        After loading any image here, 'image-loaded' signal
        will be emitted.
        """
        while True:
            params = self._queue.get()
            # It probably isn't needed anymore
            if params not in self._mru:
                continue

            pixbuf = self._transform_image(*params)
            if pixbuf is None:
                continue

            with self._lock:
                self._cache_pixbuf(params, pixbuf)
            GObject.idle_add(self.emit, 'image-loaded')

    def _transform_image(self, path, size, fill_image, draw_border, draft):
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
        :returns: the resized pixbuf
        :rtype: :class:`GdkPixbuf.Pixbuf`
        """
        path = path or ''
        image = self._open_image(path, size, draft)
        if image is None:
            return None

        if draw_border:
            image = add_border(image, border_size=self.IMAGE_BORDER_SIZE)
            image = add_drop_shadow(
                image, border_size=self.IMAGE_SHADOW_SIZE,
                offset=(self.IMAGE_SHADOW_OFFSET, self.IMAGE_SHADOW_OFFSET))

            size += self.IMAGE_BORDER_SIZE * 2
            size += self.IMAGE_SHADOW_SIZE * 2
            size += self.IMAGE_SHADOW_OFFSET
        else:
            # FIXME: There's a bug on PIL where image.thumbnail modifications
            # will be lost for some images when saving it the way we do on
            # image2pixbuf (even image.copy().size != image.size when it was
            # resized).  Adding a border of size 0 will make it at least be
            # pasted to a new image (which didn't have its thumbnail method
            # called), working around this issue.
            image = add_border(image, 0)

        pixbuf = image2pixbuf(image)
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

    def _open_image(self, path, size, draft):
        """Open the image on the given path.

        :param str path: the image path
        :param int size: the size to resize the image. It will be resized
            to fit a square of (size, size)
        :param bool draft: if we should load the image as a draft. This
            trades a little quality for a much higher performance.
        :returns: the opened image
        :rtype: :class:`PIL.Image`
        """
        # When trying to open the brokensuit images
        # (https://code.google.com/p/javapng/wiki/BrokenSuite), PIL failed to
        # open 27 of them, while Pixbuf failed to open 32. But trying PIL first
        # and Pixbuf if it failed reduced that number to 20.
        # In general, most of the images (specially if they are not broken,
        # which is something more uncommon) will be opened directly by PIL.
        try:
            image = Image.open(path)
            if draft:
                image.draft('P', (size, size))
            image.load()
        except (IOError, SyntaxError, OverflowError, struct.error) as e:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            except GLib.GError:
                return None
            else:
                image = Image.fromstring(
                    "RGB", (pixbuf.get_width(), pixbuf.get_height()),
                    pixbuf.get_pixels())

        image.thumbnail((size, size), Image.BICUBIC)
        return image
