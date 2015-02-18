"""Image utilities

Some general image utilities using PIL.
"""

import io

from gi.repository import GdkPixbuf
from PIL import Image, ImageFilter, ImageFile

# Generating a drop shadow is an expensive operation. Keep a cache
# of already generated drop shadows so they can be reutilized
_drop_shadows_cache = {}


def image2pixbuf(image):
    """Convert a PIL image to a pixbuf.

    :param image: the image to convert
    :type image: `PIL.Image`
    :returns: the newly created pixbuf
    :rtype: `GdkPixbuf.Pixbuf`
    """
    with io.BytesIO() as f:
        image.save(f, 'png')
        contents = f.getvalue()

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
