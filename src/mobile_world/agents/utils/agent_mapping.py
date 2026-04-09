"""
Action mapping for different agent types to mobile world actions.
"""

from mobile_world.runtime.utils.models import (
    ANSWER,
    ASK_USER,
    CLICK,
    DRAG,
    FINISHED,
    INPUT_TEXT,
    KEYBOARD_ENTER,
    LONG_PRESS,
    NAVIGATE_BACK,
    NAVIGATE_HOME,
    OPEN_APP,
    SCROLL,
    WAIT,
)

QWENVL2AW_ACTION_MAP = {
    "click": CLICK,
    "type": INPUT_TEXT,
    "long_press": LONG_PRESS,
    "scroll": SCROLL,
    "back": NAVIGATE_BACK,
    "home": NAVIGATE_HOME,
    "enter": KEYBOARD_ENTER,
    "answer": ANSWER,
    "open_app": OPEN_APP,
    "wait": WAIT,
    "terminate": FINISHED,
    "swipe": DRAG,
    "ask_user": ASK_USER,
    "drag": DRAG,
}


GUIOWL2AW_ACTION_MAP = {
    "click": CLICK,
    "type": INPUT_TEXT,
    "long_press": LONG_PRESS,
    "scroll": SCROLL,
    "back": NAVIGATE_BACK,
    "home": NAVIGATE_HOME,
    "enter": KEYBOARD_ENTER,
    "answer": ANSWER,
    "open": OPEN_APP,
    "wait": WAIT,
    "terminate": FINISHED,
    "swipe": DRAG,
    "interact": ASK_USER,
}

UIINS_ACTION_MAP = {"click": CLICK, "long_press": LONG_PRESS}
