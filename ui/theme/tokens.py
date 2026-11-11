"""
The visual language of Nimbus: colors, type, radii, sizes and motion timings. The palette takes
its cues from a martial-arts adventure on a golden cloud: gi orange and wristband blue as the
two accents, cloud gold for highlights, a bright sky for headers, and a deep night body so long
answers stay easy to read. Pure constants; nothing is drawn here.
"""

from __future__ import annotations

# Sky and body
SKY_TOP = "#1E6FE0"
SKY_BOTTOM = "#58B4FF"
NIGHT = "#0A1020"
NIGHT_DEEP = "#070B16"
SURFACE = "#111A2E"
SURFACE_RAISED = "#16223B"
SURFACE_HOVER = "#1E2D4D"
BORDER = "#22314F"
BORDER_STRONG = "#2F4470"

# Accents
GI_ORANGE = "#FF8A1F"
GI_ORANGE_DEEP = "#F2650A"
GI_BLUE = "#2D5BDA"
GI_BLUE_SOFT = "#4C7BFF"
CLOUD_GOLD = "#FFC940"
CLOUD_GOLD_DEEP = "#E8A317"
CLOUD_SHADOW = "#C98A12"
# Kept for the existing accent gradients; the energy colour is the gi orange.
ENERGY_ORANGE = GI_ORANGE
ENERGY_ORANGE_SOFT = "#FFAA55"
SCOUTER_GREEN = "#3EF08A"

# Text
TEXT = "#F3F6FC"
TEXT_MUTED = "#93A3BF"
TEXT_FAINT = "#7A8BAA"
TEXT_ON_GOLD = "#2B1A00"
TEXT_ON_ORANGE = "#1F0E00"

# Status
SUCCESS = "#3EE08A"
DANGER = "#FF5A6A"
LOCAL_BADGE = "#1FAF6B"
CLOUD_BADGE = GI_ORANGE

FONT_FAMILY = "Segoe UI"
FONT_FALLBACK = "Arial"
FONT_SIZE = 10
# A bundled comic-book display face (assets/fonts, SIL OFL) for titles and big moments.
DISPLAY_FONT_FAMILY = "Bangers"
TITLE_FONT_FAMILY = DISPLAY_FONT_FAMILY
MONO_FONT_FAMILY = "Cascadia Mono"

RADIUS_WINDOW = 22
RADIUS_CARD = 16
RADIUS_BUBBLE = 18
RADIUS_CONTROL = 12
RADIUS_PILL = 999

CHAT_WIDTH = 780
CHAT_HEIGHT = 660
CHAT_MIN_HEIGHT = 460
HEADER_HEIGHT = 68
SHADOW_MARGIN = 30
ICON_SIZE = 18

# Motion
SUMMON_MS = 260
DISMISS_MS = 170
SUMMON_RISE_PX = 26
AURA_PERIOD_MS = 1400
BOB_PERIOD_MS = 1200
BOB_AMPLITUDE_PX = 3
ORB_PULSE_MS = 900

PLACEHOLDER_TEXT = "Where to? Ask about your files, or tell me what to open…"
