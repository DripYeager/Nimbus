"""
The visual language of Nimbus: colors, radii, sizes and motion timings. Inspired by a golden
cloud crossing a bright sky — sky-blue header, cloud gold and energy orange as accents, on a
deep night-sky body that keeps long answers easy to read. Pure constants; nothing is drawn here.
"""

from __future__ import annotations

# Sky and body
SKY_TOP = "#2F8FE8"
SKY_BOTTOM = "#7CC8FF"
NIGHT = "#0E1A2B"
SURFACE = "#15253B"
SURFACE_RAISED = "#1C3150"
SURFACE_HOVER = "#24406A"
BORDER = "#2A4366"

# Accents
CLOUD_GOLD = "#FFC940"
CLOUD_GOLD_DEEP = "#E8A317"
CLOUD_SHADOW = "#C98A12"
ENERGY_ORANGE = "#FF7A1A"
ENERGY_ORANGE_SOFT = "#FF9F4D"

# Text
TEXT = "#F4F7FB"
TEXT_MUTED = "#9FB1C7"
TEXT_ON_GOLD = "#3A2600"

# Status
SUCCESS = "#4ADE80"
DANGER = "#FF5A5F"
LOCAL_BADGE = "#2BB673"
CLOUD_BADGE = ENERGY_ORANGE

FONT_FAMILY = "Segoe UI"
FONT_SIZE = 10
TITLE_FONT_FAMILY = "Segoe UI Black"

RADIUS_WINDOW = 18
RADIUS_BUBBLE = 14
RADIUS_CONTROL = 10

CHAT_WIDTH = 720
CHAT_HEIGHT = 600
CHAT_MIN_HEIGHT = 420
HEADER_HEIGHT = 64
SHADOW_MARGIN = 28
SHADOW_BLUR = 30
SHADOW_ALPHA = 140

# Motion
SUMMON_MS = 240
DISMISS_MS = 170
SUMMON_RISE_PX = 26
AURA_PERIOD_MS = 1400
BOB_PERIOD_MS = 1200
BOB_AMPLITUDE_PX = 3

PLACEHOLDER_TEXT = "Where to? Ask about your files, or tell me what to open…"
