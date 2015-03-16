#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Test for external libs."""

import base64
import os
import tempfile
import unittest

from PIL import Image

from datagrid_gtk3.utils import imageutils

_MEDIA_FILES = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), os.pardir, "data", "media")
_TEST_IMAGE_BASE64 = """
AAABAAIAEBACAAEAAQCwAAAAJgAAACAgEAABAAQA6AIAANYAAAAoAAAAEAAAACAAAAABAAEAAAAA
AEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP///wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABjDAAA
UpAAAGMQAABSkAAAYwwAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//8AAP//AAD//wAA//8AAP//AAAA
AQAAAAEAAAABAAAAAQAAAAEAAAABAAAAAQAA//8AAP//AAD//wAA//8AACgAAAAgAAAAQAAAAAEA
BAAAAAAAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAAACAAAAAgIAAgAAAAIAAgACAgAAAgICA
AMDAwAAAAP8AAP8AAAD//wD/AAAA/wD/AP//AAD///8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAA//gAAAD/+AAAAHj/gAAAAPAHgAAA8AeAAAeHAHAAAADwB4AAAPAHgAAI
cAAAAAAA+IgAAAD4iAAAD3AAAAAAAPAPAAAA8A8AAAiAAAAAAAD3iAAAAPeIAAAAiHeAAAAAiHAA
AACIcAAAAAeIcAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/////////////////////////////////
///////////////////////////////AEAQBwBAEAcAQBAHAEAQBwBAEAcAQBAHAEAQBwBAEAcAQ
BAH//////////////////////////////////////////////////////////w==
"""


class PILTest(unittest.TestCase):

    """Test for some PIL bugs."""

    def test_thumbnail_no_bug(self):
        """Test :meth:`PIL.thumbnail` without bugs."""
        image = Image.open(
            os.path.join(_MEDIA_FILES, 'icons', 'image.png'))
        image.load()
        self.assertEqual(image.size, (32, 32))

        image.thumbnail((10, 10), Image.BICUBIC)

        # This is a comparison with the test bellow in a file that doesn't fail
        image_copy = image.copy()
        self.assertEqual(image_copy.size, (10, 10))
        pixbuf = imageutils.image2pixbuf(image)
        self.assertEqual(
            (pixbuf.get_width(), pixbuf.get_height()), (10, 10))

    def test_thumbnail_bug_exists(self):
        """Test for the existence of a bug on :meth:`PIL.thumbnail`."""
        with tempfile.NamedTemporaryFile() as f:
            # This image has something that breaks thumbnail propagation
            f.write(base64.b64decode(_TEST_IMAGE_BASE64))
            f.flush()

            image = Image.open(f.name)
            image.load()
            self.assertEqual(image.size, (32, 32))

            image.thumbnail((10, 10), Image.BICUBIC)

            # When both those tests fail, it means we can remove fix the FIXME
            # code on datagrid_gtk3.utils.transformations.image_transform.
            # This should propagate the changes done by thumbnail
            image_copy = image.copy()
            self.assertEqual(image_copy.size, (32, 32))
            pixbuf = imageutils.image2pixbuf(image)
            self.assertEqual(
                (pixbuf.get_width(), pixbuf.get_height()), (32, 32))



if __name__ == '__main__':
    unittest.main()
