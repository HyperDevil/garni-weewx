#
#    Copyright (c) 2009-2015 Tom Keffer <tkeffer@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

"""User extensions module

This module is imported from the main executable, so anything put here will be
executed before anything else happens. This makes it a good place to put user
extensions.
"""

import locale

# This sets the locale for all categories to the user’s default setting (typically specified in the
# LANG environment variable). See: https://docs.python.org/3/library/locale.html#locale.setlocale
locale.setlocale(locale.LC_ALL, '')

from weewx.units import obs_group_dict

#lightning sensor
obs_group_dict["lightningDistance"] = "group_distance"
obs_group_dict["lightningCount5m"] = "group_count"
obs_group_dict["lightningCount30m"] = "group_count"
obs_group_dict["lightningCount1h"] = "group_count"
obs_group_dict["lightningCount1d"] = "group_count"

#batteries
obs_group_dict["outdoorBatteryOk"] = "group_count"
obs_group_dict["consoleBatteryOk"] = "group_count"
obs_group_dict["lightningBatteryOk"] = "group_count"
obs_group_dict["outdoorSensorConnected"] = "group_count"
obs_group_dict["lightningSensorConnected"] = "group_count"

#wgbt
obs_group_dict["wbgt"] = "group_temperature"
