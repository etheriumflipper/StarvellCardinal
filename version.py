"""
Версия Starvell Cardinal
"""

import os

VERSION = "0.2.8"
REPOSITORY_URL = "https://github.com/etheriumflipper/StarvellCardinal.git"
VERSION_URL = os.getenv(
    "STARVELL_VERSION_URL",
    "https://raw.githubusercontent.com/etheriumflipper/StarvellCardinal/main/version.py"
)
