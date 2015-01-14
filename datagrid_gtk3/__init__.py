# -*- coding: utf-8 -*-

__author__ = 'viaForensics'
__email__ = 'info@viaforensics.com'
__version__ = '0.1.0'

# Set default logging handler to avoid "No handler found" warnings.
import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
