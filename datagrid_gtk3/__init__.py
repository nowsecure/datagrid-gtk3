# -*- coding: utf-8 -*-

__author__ = 'NowSecure, Inc.'
__email__ = 'info@nowsecure.com'
__version__ = '0.1.5'

import logging
import os

from gi.repository import Gtk


icon_theme = Gtk.IconTheme.get_default()
# Register our icons as ultimate fallback. Those should only
# be used when there's no icon theme registered (e.g. xvfb)
icon_theme.append_search_path(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 'data', 'media', 'icons'))

# Set default logging handler to avoid "No handler found" warnings.
logging.getLogger(__name__).addHandler(logging.NullHandler())
