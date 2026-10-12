import io
import os
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "roboto.ttf")

def get_font(size: int = 32) -> ImageFont.FreeTypeFont:
    try:
        if os.path.exists(FONT_PATH):
            return ImageFont.truetype(FONT_PATH, size=size)
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()

def evaluate_guess_states(guesses: List[str], solution: str) -> List[Dict[str, Any]]:
    """Evaluates each guess against solution and returns list of {guess, result}."""
    sol_upper = solution.upper()
    evaluated = []

    for g in guesses:
        g_upper = g.upper()
        sol_count = {}
        for c in sol_upper:
            sol_count[c] = sol_count.get(c, 0) + 1

        result = ["absent"] * len(g_upper)

        # First pass: correct positions
        for i in range(len(g_upper)):
            if i < len(sol_upper) and g_upper[i] == sol_upper[i]:
                result[i] = "correct"
                sol_count[g_upper[i]] -= 1

        # Second pass: present letters
        for i in range(len(g_upper)):
            if result[i] == "absent" and sol_count.get(g_upper[i], 0) > 0:
                result[i] = "present"
                sol_count[g_upper[i]] -= 1

        evaluated.append({"guess": g_upper, "result": result})

    return evaluated

def generate_wordle_image(guesses: List[str], solution: str) -> bytes:
    """Generates high resolution PNG image of Wordle grid matching the web UI."""
    tiles = evaluate_guess_states(guesses, solution)
    word_len = len(solution)

    tile_size = 60
    gap = 8
    padding = 20
    rows = 6

    width = padding * 2 + word_len * tile_size + (word_len - 1) * gap
    height = padding * 2 + rows * tile_size + (rows - 1) * gap

    # Colors
    bg_color = (18, 18, 19)         # #121213
    correct_color = (83, 141, 78)    # #538d4e
    present_color = (181, 159, 59)   # #b59f3b
    absent_color = (58, 58, 60)      # #3a3a3c
    border_color = (86, 87, 88)      # #565758
    text_color = (255, 255, 255)

    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)
    font = get_font(32)

    # Pad with empty rows if less than 6 guesses
    padded_tiles = list(tiles)
    while len(padded_tiles) < rows:
        padded_tiles.append({
            "guess": " " * word_len,
            "result": ["empty"] * word_len
        })

    for row_idx, row in enumerate(padded_tiles):
        guess_str = row["guess"]
        res_list = row["result"]
        y = padding + row_idx * (tile_size + gap)

        for col_idx in range(word_len):
            x = padding + col_idx * (tile_size + gap)
            state = res_list[col_idx]
            letter = guess_str[col_idx].strip()

            if state == "correct":
                tile_bg = correct_color
                draw.rectangle([x, y, x + tile_size, y + tile_size], fill=tile_bg)
            elif state == "present":
                tile_bg = present_color
                draw.rectangle([x, y, x + tile_size, y + tile_size], fill=tile_bg)
            elif state == "absent":
                tile_bg = absent_color
                draw.rectangle([x, y, x + tile_size, y + tile_size], fill=tile_bg)
            else: # empty
                draw.rectangle([x, y, x + tile_size, y + tile_size], fill=None, outline=border_color, width=2)

            if letter:
                # Center text in tile
                bbox = font.getbbox(letter)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                tx = x + (tile_size - text_w) // 2 - bbox[0]
                ty = y + (tile_size - text_h) // 2 - bbox[1]
                draw.text((tx, ty), letter, fill=text_color, font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
