#!/usr/bin/env python3
import logging
import sys

from manage.main import main

import config

logging.basicConfig(level=logging.DEBUG)

if __name__ == '__main__':
    sys.exit(main(config))
