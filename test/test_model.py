# -*- coding: utf-8 -*-
"""

@author: Lukas Sandström
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from rss_im_sweep.main import Model, Observable

model = Model()

model.add_variable("ddict", {2: ("as", 3), "r": 22, "none": None})

with open("test.json", "w") as fp:
    model.store_json(fp)

with open("test.json") as fp:
    model.load_json(fp)

print(model.ddict.get())
