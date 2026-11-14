# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Constants for the HVX Indoor Environment integration."""

from __future__ import annotations

import logging

DOMAIN = "hvx_ieq"
LOGGER = logging.getLogger(__package__)

CONF_BUILDING_TYPE = "building_type"
CONF_TARGET_CATEGORY = "target_category"
CONF_WINDOW_DAYS = "window_days"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_AREAS = "areas"
CONF_ROOMS = "rooms"

DEFAULT_TARGET_CATEGORY = "II"
DEFAULT_WINDOW_DAYS = 7
DEFAULT_SCAN_INTERVAL = 15  # minutes
DEFAULT_BUILDING_TYPE = "residential"  # most HA installs are homes: assessed around the clock

CATEGORIES = ["I", "II", "III", "IV"]
BUILDING_TYPES = ["office", "school", "residential", "meeting_room", "classroom"]

# hvx parameter -> Home Assistant sensor device class
PARAMETER_DEVICE_CLASSES = {
    "temperature": "temperature",
    "co2": "carbon_dioxide",
    "humidity": "humidity",
}
PARAMETER_LABELS = {"temperature": "temperature", "co2": "CO₂", "humidity": "humidity"}

SOURCE_NAME = "ha"

# Enum sensor states (hassfest requires lowercase keys)
CATEGORY_STATES = {"I": "cat_i", "II": "cat_ii", "III": "cat_iii", "IV": "cat_iv", None: "below_iv"}

SERVICE_GENERATE_REPORT = "generate_report"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_FORMAT = "format"
ATTR_FULL_ANALYSIS = "full_analysis"
REPORT_DIR = "hvx_ieq"
