"""
Helper utilities for agent implementations.
"""

import base64
import math
from io import BytesIO

from PIL import Image

IMAGE_FACTOR = 28
MIN_PIXELS = 100 * 28 * 28
MAX_PIXELS = 16384 * 28 * 28
MAX_RATIO = 200


def add_period_robustly(text: str) -> str:
    """
    Append a period to the text if it does not already end with a punctuation mark.

    The punctuation character is chosen based on the dominant language detected
    in the text:
      - Predominantly Chinese  → '。'
      - Predominantly English (or balanced) → '.'

    Args:
        text: Input text string.

    Returns:
        The original text with a period appended if needed, or the original
        text unchanged if it already ends with a recognised punctuation mark.
        Returns the input as-is if it is empty, None, or not a string.
    """
    if not text or not isinstance(text, str):
        return text

    text = text.strip()
    if not text:
        return text

 
    END_PUNCTUATIONS = {
        '。', '！', '？', '…', '；',
        '.', '!', '?', ';',
        '~', '～', '》', '」', '』', '）', ')', ']', '}',
    }

    if text[-1] in END_PUNCTUATIONS:
        return text

    # Determine the dominant language by counting Chinese vs. ASCII-alpha characters.
    chinese_count = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    english_count = sum(1 for ch in text if ch.isalpha() and ord(ch) < 128)

    return text + ('。' if chinese_count > english_count else '.')



def pil_to_base64(image) -> str:
    """Convert PIL image to base64 string."""
    if not isinstance(image, Image.Image):
        image = Image.open(BytesIO(image)).convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def judge_scroll_direction(start_x: float, start_y: float, end_x: float, end_y: float) -> str:
    """Determine scroll direction from start to end coordinates."""
    delta_x = end_x - start_x
    delta_y = end_y - start_y

    if abs(delta_x) > abs(delta_y):
        return "left" if delta_x < 0 else "right"
    else:
        return "down" if delta_y < 0 else "up"


def judge_swipe_direction(start_x: float, start_y: float, end_x: float, end_y: float) -> str:
    """Determine swipe direction from start to end coordinates."""
    delta_x = end_x - start_x
    delta_y = end_y - start_y

    if abs(delta_x) > abs(delta_y):
        return "left" if delta_x < 0 else "right"
    else:
        return "down" if delta_y > 0 else "up"


def reverse_swipe_direction(direction: str) -> str:
    if direction == "up":
        return "down"
    elif direction == "down":
        return "up"
    else:
        if direction == "left" or direction == "right":
            return direction
        else:
            raise ValueError(f"Invalid direction: {direction}")


def round_by_factor(number: int, factor: int) -> int:
    """Returns the closest integer to 'number' that is divisible by 'factor'."""
    return round(number / factor) * factor


def ceil_by_factor(number: int, factor: int) -> int:
    """Returns the smallest integer greater than or equal to 'number' that is divisible by 'factor'."""
    return math.ceil(number / factor) * factor


def floor_by_factor(number: int, factor: int) -> int:
    """Returns the largest integer less than or equal to 'number' that is divisible by 'factor'."""
    return math.floor(number / factor) * factor


def linear_resize(
    height: int,
    width: int,
    factor: int = IMAGE_FACTOR,
    min_pixels: int = MIN_PIXELS,
    max_pixels: int = MAX_PIXELS,
) -> tuple[int, int]:
    """Linearly resize image dimensions to fit within pixel constraints."""
    if width * height > max_pixels:
        resize_factor = math.sqrt(max_pixels / (width * height))
        width, height = int(width * resize_factor), int(height * resize_factor)
    if width * height < min_pixels:
        resize_factor = math.sqrt(min_pixels / (width * height))
        width, height = (
            math.ceil(width * resize_factor),
            math.ceil(height * resize_factor),
        )

    return height, width


def smart_resize(
    height: int,
    width: int,
    factor: int = IMAGE_FACTOR,
    min_pixels: int = MIN_PIXELS,
    max_pixels: int = MAX_PIXELS,
) -> tuple[int, int]:
    """
    Rescales the image so that the following conditions are met:

    1. Both dimensions (height and width) are divisible by 'factor'.
    2. The total number of pixels is within the range ['min_pixels', 'max_pixels'].
    3. The aspect ratio of the image is maintained as closely as possible.
    """
    if max(height, width) / min(height, width) > MAX_RATIO:
        raise ValueError(
            f"absolute aspect ratio must be smaller than {MAX_RATIO}, got {max(height, width) / min(height, width)}"
        )
    h_bar = max(factor, round_by_factor(height, factor))
    w_bar = max(factor, round_by_factor(width, factor))
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = floor_by_factor(height / beta, factor)
        w_bar = floor_by_factor(width / beta, factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = ceil_by_factor(height * beta, factor)
        w_bar = ceil_by_factor(width * beta, factor)
    return h_bar, w_bar


if __name__ == "__main__":
    h, w = smart_resize(1080, 2400)
    print(h, w)
