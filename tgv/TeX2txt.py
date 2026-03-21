"""
HP50g TGV Pipeline: LaTeX to Plain Text Converter
=================================================
This module transforms LaTeX source code into formatted plain text compatible 
with the TGV viewer on the HP50g. 

Key transformation steps:
1. Recursive expansion of \'include and \'input.
2. Resolution of user-defined \newcommand macros.
3. Parsing of document structure (paragraphs, equations, figures).
4. Conversion of math syntax (\'frac, \'sqrt, subscripts) into plain-text notation.
5. Character mapping from Unicode/LaTeX to the HP50g internal charset.
6. Smart word-wrapping for the 22-column calculator display.
"""

import re
import logging
from pathlib import Path
from utils.charmap import HP_HEX_MAP, LATEX_TO_CHAR_MAP

# --- REGEX DEFINITIONS ---

# Captures display math blocks: \[ ... \]
DISPLAY_MATH_RE = re.compile(r'\\\[(.*?)\\\]', re.DOTALL)

# Captures figure environments to extract image and caption data
FIGURE_RE = re.compile(r'\\begin\{figure\}(?:\[[^\]]*\])?(.*?)\\end\{figure\}', re.DOTALL)

# Extracts \newcommand{\name}{value} with support for nested braces in the value
NEWCOMMAND_RE = re.compile(
    r'\\newcommand\s*\{\\([A-Za-z@]+)\}\s*(?:\[[^\]]*\])?\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}',
    re.DOTALL,
)

# Identifies HP-specific formatting tags used during the wrapping process
TAG_PATTERN = re.compile(r'\[(?:SUB|SUP|NORM|B|/B|I|/I|U|/U|INV|/INV)\]')


def read_tex_with_includes(input_path: Path, visited: set[Path] | None = None) -> str:
    """
    Recursively merges all \'included or \'inputed files into a single string.
    Prevents infinite recursion using the 'visited' set.
    """
    if visited is None:
        visited = set()

    input_path = input_path.resolve()
    if input_path in visited:
        return ""

    visited.add(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    text = input_path.read_text(encoding="utf-8")

    def replace_include(match: re.Match[str]) -> str:
        name = match.group(2).strip()
        include_path = (input_path.parent / name)
        if include_path.suffix == "":
            include_path = include_path.with_suffix(".tex")

        if include_path.exists():
            return read_tex_with_includes(include_path, visited)

        logging.warning(f"Included file not found: {include_path}")
        return match.group(0)

    return re.sub(r'\\(include|input)\{([^}]+)\}', replace_include, text)


def extract_newcommands(text: str) -> tuple[dict[str, str], str]:
    """
    Finds all \newcommand definitions and stores them in a lookup dictionary.
    Removes the definitions from the text to prevent them from appearing in output.
    """
    commands: dict[str, str] = {}

    for match in NEWCOMMAND_RE.finditer(text):
        name = match.group(1).strip()
        value = match.group(2).strip()
        commands[name] = value

    text_wo_commands = NEWCOMMAND_RE.sub("", text)
    return commands, text_wo_commands


def resolve_commands(text: str, commands: dict[str, str], max_passes: int = 8) -> str:
    """
    Replaces instances of \'MyCommand with its defined value.
    Runs multiple passes to handle 'nested' commands (commands that use other commands).
    """
    resolved = text

    for _ in range(max_passes):
        changed = False
        for name, value in commands.items():
            pattern = rf'\\{re.escape(name)}\b'
            new_resolved = re.sub(pattern, value, resolved)
            if new_resolved != resolved:
                changed = True
                resolved = new_resolved
        if not changed:
            break

    return resolved


def extract_sequence_blocks(text: str) -> list[str]:
    """
    Divides the document into a sequence of 'blocks' (Paragraphs, Images, or Equations).
    This ensures that display equations and figures stay on their own lines.
    """
    pattern = re.compile(
        r'\\\[(.*?)\\\]|\\begin\{figure\}(?:\[[^\]]*\])?(.*?)\\end\{figure\}',
        re.DOTALL,
    )

    blocks: list[str] = []
    last_end = 0

    for match in pattern.finditer(text):
        # Everything before the math/figure is a paragraph block
        prefix = text[last_end:match.start()]
        blocks.extend(split_text_blocks(prefix))

        display_math = match.group(1)
        figure_body = match.group(2)

        if display_math is not None:
            blocks.append(display_math.strip())
        elif figure_body is not None:
            blocks.append(figure_body.strip())

        last_end = match.end()

    # Capture anything remaining after the last match
    suffix = text[last_end:]
    blocks.extend(split_text_blocks(suffix))
    return [block for block in blocks if block.strip()]


def split_text_blocks(text: str) -> list[str]:
    """
    Splits text into paragraphs based on double newlines.
    Removes LaTeX structural noise (sections, labels, citations).
    """
    text = re.sub(r'%.*', '', text) # Remove comments
    text = re.sub(r'\\section\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\subsection\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\subsubsection\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\paragraph\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    text = re.sub(r'\\ref\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\cite\{([^}]*)\}', r'[\1]', text)

    parts = re.split(r'\n\s*\n', text)
    return [part.strip() for part in parts if part.strip()]


def clean_latex_fragment(
    text: str,
    target_dir: Path | None,
    bmp_selected_dir: str = "img/bmp_images",
    commands: dict[str, str] | None = None,
) -> str:
    """
    The core translation engine for a single block of text.
    Converts LaTeX math and formatting into HP-friendly text.
    """
    commands = commands or {}
    text = resolve_commands(text, commands)
    text = re.sub(r'%.*', '', text)

    image_placeholders: list[str] = []

    # --- IMAGE HANDLING ---
    def format_image_tag(match: re.Match[str]) -> str:
        """Finds the actual BMP variation selected for this image."""
        img_path = match.group(1).strip()
        stem = Path(img_path).stem
        actual_name = f"{stem}.bmp"

        if target_dir:
            search_path = target_dir / bmp_selected_dir
            if search_path.exists():
                # Locate the specific variation (e.g. diagram_02_strong.bmp)
                found = sorted(search_path.glob(f"{stem}*.bmp"))
                if found:
                    actual_name = found[0].name

        image_placeholders.append(f"\\image{{{actual_name}}}")
        return f"@@IMGPLACEHOLDER{len(image_placeholders)-1}@@"

    text = re.sub(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', format_image_tag, text)

    # --- FORMATTING STRIPPING ---
    text = re.sub(r'\\caption\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\text\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\mathrm\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\mathbf\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\mathit\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\mathcal\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\left', '', text)
    text = re.sub(r'\\right', '', text)
    text = re.sub(r'\\centering\b', '', text)
    text = re.sub(r'\\begin\{[^}]+\}(?:\[[^\]]*\])?', '', text)
    text = re.sub(r'\\end\{[^}]+\}', '', text)
    text = re.sub(r'\\item\b', '-', text)
    text = text.replace('~', ' ')
    text = text.replace('$', '')

    # --- ACCENT REMOVAL (HP50g limited charset) ---
    accent_replacements = {
        'ã': 'a', 'õ': 'o', 'á': 'a', 'à': 'a', 'â': 'a',
        'é': 'e', 'ê': 'e', 'í': 'i', 'ó': 'o', 'ô': 'o',
        'ú': 'u', 'ç': 'c',
    }
    for bad_char, good_char in accent_replacements.items():
        text = text.replace(bad_char, good_char.lower())
        text = text.replace(bad_char.upper(), good_char.upper())

    # --- MATH TRANSFORMATION ---
    
    # 1. Subscripts and Superscripts (Using TGV formatting tags)
    text = re.sub(r'_\{([^}]+)\}', r'[SUB]\1[NORM]', text)
    text = re.sub(r'_([a-zA-Z0-9])', r'[SUB]\1[NORM]', text)
    text = re.sub(r'\^\{([^}]+)\}', r'[SUP]\1[NORM]', text)
    text = re.sub(r'\^([a-zA-Z0-9])', r'[SUP]\1[NORM]', text)

    # 2. Fractions: \frac{a}{b} -> (a)/(b)
    frac_pattern = r'\\frac\{((?:[^{}]|\{[^{}]*\})*)\}\{((?:[^{}]|\{[^{}]*\})*)\}'
    while re.search(frac_pattern, text):
        text = re.sub(frac_pattern, r'(\1)/(\2)', text)

    # 3. Square Roots: \sqrt{x} -> √(x)
    sqrt_pattern = r'\\sqrt\{((?:[^{}]|\{[^{}]*\})*)\}'
    while re.search(sqrt_pattern, text):
        text = re.sub(sqrt_pattern, r'√(\1)', text)

    # 4. Greek and Special Symbols (via charmap.py)
    for cmd in sorted(LATEX_TO_CHAR_MAP.keys(), key=len, reverse=True):
        text = text.replace(cmd, LATEX_TO_CHAR_MAP[cmd])

    # Clean up remaining backslashes from simple commands
    text = re.sub(r'\\([A-Za-z]+)\b', r'\1', text)

    # Restore images into their correct sequence
    for i, img_tag in enumerate(image_placeholders):
        text = text.replace(f"@@IMGPLACEHOLDER{i}@@", img_tag)

    # Final whitespace normalization
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\s*\n\s*', ' ', text)
    return text.strip()


def is_char_supported(char: str) -> bool:
    """Checks if a character is in the HP50g map or can be encoded as Latin-1."""
    if char in HP_HEX_MAP:
        return True
    try:
        char.encode("latin-1")
        return True
    except UnicodeEncodeError:
        return False


def smart_wrap(text: str, max_cols: int = 22) -> str:
    """
    Wraps text to the HP50g's 22-column limit.
    Ensures that formatting tags (like [SUB]) don't count toward the column width.
    """
    words = text.split(' ')
    lines: list[str] = []
    current_line: list[str] = []
    current_len = 0

    for word in words:
        if not word:
            continue

        # \image directives must always be on their own line
        if word.startswith('\\image{'):
            if current_line:
                lines.append(" ".join(current_line))
                current_line = []
                current_len = 0
            lines.append(word)
            continue

        # Calculate 'visible' length by removing tags
        visible_word = TAG_PATTERN.sub('', word)
        word_len = len(visible_word)
        space_needed = 1 if current_line else 0

        if current_len + word_len + space_needed <= max_cols:
            current_line.append(word)
            current_len += word_len + space_needed
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_len = word_len

    if current_line:
        lines.append(" ".join(current_line))

    return "\n".join(lines)


def sanitize_for_hp(text: str) -> str:
    """Replaces unsupported Unicode characters with '?' to prevent encoding errors."""
    safe = []
    for char in text:
        if is_char_supported(char):
            safe.append(char)
        else:
            logging.warning(f"Unmapped character '{char}' replaced with '?'")
            safe.append('?')
    return "".join(safe)


def convert_tex_to_hp_text(
    input_path: str,
    output_path: str,
    bmp_selected_dir: str = "img/bmp_images",
    max_cols: int = 22,
) -> None:
    """
    The main entry point for file conversion.
    Orchestrates the read -> extract -> clean -> wrap -> write flow.
    """
    in_file = Path(input_path)
    out_file = Path(output_path)

    expanded_content = read_tex_with_includes(in_file)
    commands, body = extract_newcommands(expanded_content)
    blocks = extract_sequence_blocks(body)

    processed_blocks: list[str] = []
    target_dir = in_file.parent

    for block in blocks:
        clean_block = clean_latex_fragment(
            block,
            target_dir=target_dir,
            bmp_selected_dir=bmp_selected_dir,
            commands=commands,
        )
        if not clean_block:
            continue

        safe_block = sanitize_for_hp(clean_block)
        wrapped_block = smart_wrap(safe_block, max_cols=max_cols)
        processed_blocks.append(wrapped_block)

    # Save final text with double newlines between blocks (paragraphs)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n\n".join(processed_blocks), encoding="utf-8")

    logging.info(f"Successfully converted {in_file.name} to {out_file.name}")
    logging.info(f"Extracted command definitions: {len(commands)}")
    logging.info(f"Emitted sequence blocks: {len(processed_blocks)}")
