"""LaTeX-to-text conversion for HP50g TGV documents."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from utils.charmap import HP_HEX_MAP, LATEX_TO_CHAR_MAP

DISPLAY_MATH_RE = re.compile(r'\\\[(.*?)\\\]', re.DOTALL)
FIGURE_RE = re.compile(r'\\begin\{figure\}(?:\[[^\]]*\])?(.*?)\\end\{figure\}', re.DOTALL)
NEWCOMMAND_RE = re.compile(
    r'\\newcommand\s*\{\\([A-Za-z@]+)\}\s*(?:\[[^\]]*\])?\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}',
    re.DOTALL,
)
TAG_PATTERN = re.compile(r'\[(?:SUB|SUP|NORM|B|/B|I|/I|U|/U|INV|/INV)\]')


def _is_within_directory(path: Path, root_dir: Path) -> bool:
    """Return whether ``path`` stays within ``root_dir`` after resolution."""
    try:
        path.relative_to(root_dir)
        return True
    except ValueError:
        return False


def read_tex_with_includes(
    input_path: Path,
    visited: set[Path] | None = None,
    root_dir: Path | None = None,
) -> str:
    """Read a TeX file and inline ``\\include`` and ``\\input`` references.

    Args:
        input_path: Entry-point TeX file to expand.
        visited: Optional set used to avoid recursive include loops.

    Returns:
        str: Expanded TeX source.

    Raises:
        FileNotFoundError: If the root input file does not exist.
    """
    if visited is None:
        visited = set()

    input_path = input_path.resolve()
    if root_dir is None:
        root_dir = input_path.parent
    else:
        root_dir = root_dir.resolve()

    if input_path in visited:
        return ""

    visited.add(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    text = input_path.read_text(encoding="utf-8")

    def replace_include(match: re.Match[str]) -> str:
        name = match.group(2).strip()
        include_path = input_path.parent / name
        if include_path.suffix == "":
            include_path = include_path.with_suffix(".tex")
        include_path = include_path.resolve()

        if not _is_within_directory(include_path, root_dir):
            logging.warning("Blocked include outside project root: %s", include_path)
            return match.group(0)

        if include_path.exists():
            return read_tex_with_includes(include_path, visited, root_dir=root_dir)

        logging.warning("Included file not found: %s", include_path)
        return match.group(0)

    return re.sub(r'\\(include|input)\{([^}]+)\}', replace_include, text)


def extract_newcommands(text: str) -> tuple[dict[str, str], str]:
    """Extract ``\newcommand`` definitions from TeX source.

    Args:
        text: Expanded TeX source.

    Returns:
        tuple[dict[str, str], str]: Mapping of command names to values and the
        source text with those definitions removed.
    """
    commands: dict[str, str] = {}

    for match in NEWCOMMAND_RE.finditer(text):
        name = match.group(1).strip()
        value = match.group(2).strip()
        commands[name] = value

    text_wo_commands = NEWCOMMAND_RE.sub("", text)
    return commands, text_wo_commands


def resolve_commands(text: str, commands: dict[str, str], max_passes: int = 8) -> str:
    """Expand previously extracted macro definitions in a text fragment.

    Args:
        text: Text in which command references should be resolved.
        commands: Mapping of command names to replacement values.
        max_passes: Maximum expansion passes for nested command definitions.

    Returns:
        str: Text with commands expanded.
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
    """Split TeX content into paragraph, figure, and display-math blocks.

    Args:
        text: TeX source after macro definition extraction.

    Returns:
        list[str]: Ordered content blocks ready for fragment cleaning.
    """
    pattern = re.compile(
        r'\\\[(.*?)\\\]|\\begin\{figure\}(?:\[[^\]]*\])?(.*?)\\end\{figure\}',
        re.DOTALL,
    )

    blocks: list[str] = []
    last_end = 0

    for match in pattern.finditer(text):
        prefix = text[last_end:match.start()]
        blocks.extend(split_text_blocks(prefix))

        display_math = match.group(1)
        figure_body = match.group(2)

        if display_math is not None:
            blocks.append(display_math.strip())
        elif figure_body is not None:
            blocks.append(figure_body.strip())

        last_end = match.end()

    suffix = text[last_end:]
    blocks.extend(split_text_blocks(suffix))
    return [block for block in blocks if block.strip()]


def split_text_blocks(text: str) -> list[str]:
    """Split ordinary TeX text into paragraph-sized blocks.

    Args:
        text: Raw TeX text outside figure or display-math blocks.

    Returns:
        list[str]: Cleaned paragraph fragments.
    """
    text = re.sub(r'%.*', '', text)
    text = re.sub(r'\\section\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\subsection\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\subsubsection\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\paragraph\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    text = re.sub(r'\\ref\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\cite\{([^}]*)\}', r'[\1]', text)

    parts = re.split(r'\n\s*\n', text)
    return [part.strip() for part in parts if part.strip()]


def _apply_repeated_substitution(
    text: str,
    pattern: re.Pattern[str],
    replacement: str,
    *,
    max_passes: int,
    label: str,
) -> str:
    """Apply a nested-regex rewrite with a strict, input-derived pass limit."""
    for _ in range(max_passes):
        text, replacements = pattern.subn(replacement, text)
        if replacements == 0:
            return text

    if pattern.search(text):
        logging.warning("Stopped expanding %s after %d pass(es)", label, max_passes)
    return text


def clean_latex_fragment(
    text: str,
    target_dir: Path | None,
    bmp_selected_dir: str = "img/bmp_images",
    commands: dict[str, str] | None = None,
) -> str:
    """Convert a single TeX fragment into HP-friendly plain text.

    Args:
        text: Fragment to normalize.
        target_dir: Project directory used to resolve generated BMP assets.
        bmp_selected_dir: Relative directory containing selected BMP files.
        commands: Optional macro lookup table.

    Returns:
        str: Cleaned fragment ready for sanitizing and wrapping.
    """
    commands = commands or {}
    text = resolve_commands(text, commands)
    text = re.sub(r'%.*', '', text)

    image_placeholders: list[str] = []

    def format_image_tag(match: re.Match[str]) -> str:
        img_path = match.group(1).strip()
        stem = Path(img_path).stem
        actual_name = f"{stem}.bmp"

        if target_dir:
            search_path = target_dir / bmp_selected_dir
            if search_path.exists():
                found = sorted(search_path.glob(f"{stem}*.bmp"))
                if found:
                    actual_name = found[0].name

        image_placeholders.append(f"\\image{{{actual_name}}}")
        return f"@@IMGPLACEHOLDER{len(image_placeholders) - 1}@@"

    text = re.sub(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', format_image_tag, text)

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

    accent_replacements = {
        'ã': 'a', 'õ': 'o', 'á': 'a', 'à': 'a', 'â': 'a',
        'é': 'e', 'ê': 'e', 'í': 'i', 'ó': 'o', 'ô': 'o',
        'ú': 'u', 'ç': 'c',
    }
    for bad_char, good_char in accent_replacements.items():
        text = text.replace(bad_char, good_char.lower())
        text = text.replace(bad_char.upper(), good_char.upper())

    text = re.sub(r'_\{([^}]+)\}', r'[SUB]\1[NORM]', text)
    text = re.sub(r'_([a-zA-Z0-9])', r'[SUB]\1[NORM]', text)
    text = re.sub(r'\^\{([^}]+)\}', r'[SUP]\1[NORM]', text)
    text = re.sub(r'\^([a-zA-Z0-9])', r'[SUP]\1[NORM]', text)

    frac_pattern = re.compile(r'\\frac\{((?:[^{}]|\{[^{}]*\})*)\}\{((?:[^{}]|\{[^{}]*\})*)\}')
    text = _apply_repeated_substitution(
        text,
        frac_pattern,
        r'(\1)/(\2)',
        max_passes=text.count(r'\frac'),
        label='\\frac',
    )

    sqrt_pattern = re.compile(r'\\sqrt\{((?:[^{}]|\{[^{}]*\})*)\}')
    text = _apply_repeated_substitution(
        text,
        sqrt_pattern,
        r'√(\1)',
        max_passes=text.count(r'\sqrt'),
        label='\\sqrt',
    )

    for cmd in sorted(LATEX_TO_CHAR_MAP.keys(), key=len, reverse=True):
        text = text.replace(cmd, LATEX_TO_CHAR_MAP[cmd])

    text = re.sub(r'\\([A-Za-z]+)\b', r'\1', text)

    for index, img_tag in enumerate(image_placeholders):
        text = text.replace(f"@@IMGPLACEHOLDER{index}@@", img_tag)

    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\s*\n\s*', ' ', text)
    return text.strip()


def is_char_supported(char: str) -> bool:
    """Check whether a character can be represented in HP output.

    Args:
        char: Character to validate.

    Returns:
        bool: True when the character can be encoded for HP output.
    """
    if char in HP_HEX_MAP:
        return True
    try:
        char.encode("latin-1")
        return True
    except UnicodeEncodeError:
        return False


def smart_wrap(text: str, max_cols: int = 22) -> str:
    """Wrap text to the calculator display width.

    Args:
        text: Text to wrap.
        max_cols: Maximum visible column width per output line.

    Returns:
        str: Wrapped text with embedded formatting tags preserved.
    """
    words = text.split(' ')
    lines: list[str] = []
    current_line: list[str] = []
    current_len = 0

    for word in words:
        if not word:
            continue

        if word.startswith('\\image{'):
            if current_line:
                lines.append(" ".join(current_line))
                current_line = []
                current_len = 0
            lines.append(word)
            continue

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
    """Replace unsupported characters before HP encoding.

    Args:
        text: Text to sanitize.

    Returns:
        str: Sanitized text safe for later encoding.
    """
    safe = []
    for char in text:
        if is_char_supported(char):
            safe.append(char)
        else:
            logging.warning("Unmapped character '%s' replaced with '?'", char)
            safe.append('?')
    return "".join(safe)


def convert_tex_to_hp_text(
    input_path: str,
    output_path: str,
    bmp_selected_dir: str = "img/bmp_images",
    max_cols: int = 22,
) -> None:
    """Convert a TeX document into wrapped HP-friendly text.

    Args:
        input_path: Source TeX file path.
        output_path: Destination text file path.
        bmp_selected_dir: Relative directory containing selected BMP assets.
        max_cols: Maximum visible column width for wrapping.

    Raises:
        FileNotFoundError: If the source TeX file or a required include is missing.
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

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n\n".join(processed_blocks), encoding="utf-8")

    logging.info("Successfully converted %s to %s", in_file.name, out_file.name)
    logging.info("Extracted command definitions: %d", len(commands))
    logging.info("Emitted sequence blocks: %d", len(processed_blocks))
