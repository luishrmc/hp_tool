"""Variable injection helpers for LaTeX-based TGV projects."""

from __future__ import annotations

import argparse
import logging
import re
import shutil
from pathlib import Path


def load_variables(data_file_path: Path) -> dict[str, str]:
    """Load placeholder values from a LaTeX data file.

    Args:
        data_file_path: Path to the file containing ``\newcommand`` definitions.

    Returns:
        dict[str, str]: Mapping of command names to replacement values.
    """
    variables: dict[str, str] = {}

    if not data_file_path.exists():
        logging.error("Data file not found: %s", data_file_path)
        return variables

    content = data_file_path.read_text(encoding="utf-8")
    pattern = re.compile(r'\\newcommand\{\\([a-zA-Z0-9]+)\}\{((?:[^{}]|\{[^{}]*\})*)\}')
    matches = pattern.findall(content)

    for var_name, var_value in matches:
        variables[var_name] = var_value

    return variables


def inject_variables(
    target_file_path: Path,
    output_file_path: Path,
    variables: dict[str, str],
) -> None:
    """Replace command placeholders in a target file.

    Args:
        target_file_path: Source file whose placeholders should be replaced.
        output_file_path: Destination file for the rendered content.
        variables: Mapping of placeholder names to replacement values.
    """
    if not target_file_path.exists():
        logging.error("Target file not found: %s", target_file_path)
        return

    content = target_file_path.read_text(encoding="utf-8")
    sorted_vars = sorted(variables.items(), key=lambda item: len(item[0]), reverse=True)

    for var_name, var_value in sorted_vars:
        pattern = r'\\' + re.escape(var_name) + r'(?![a-zA-Z])'
        content = re.sub(pattern, lambda _: var_value, content)

    output_file_path.parent.mkdir(parents=True, exist_ok=True)
    output_file_path.write_text(content, encoding="utf-8")
    logging.info(
        "Successfully injected %d variables into %s",
        len(variables),
        output_file_path.name,
    )


def injectVars(dir_path: str, input_name: str, data_name: str, output_name: str = "") -> None:
    """Inject variables from a data file into the target TeX file.

    Args:
        dir_path: Project directory containing the input and data files.
        input_name: Main TeX file name.
        data_name: TeX file containing replacement command definitions.
        output_name: Optional destination file name. When omitted, the input
            file is overwritten after creating a backup.
    """
    base_dir = Path(dir_path)
    data_file = base_dir / data_name
    input_file = base_dir / input_name

    if output_name:
        output_file = base_dir / output_name
        source_for_mapping = input_file
    else:
        output_file = input_file
        backup_file = base_dir / f"{input_file.stem}_org{input_file.suffix}"

        if input_file.exists():
            if not backup_file.exists():
                shutil.copy2(input_file, backup_file)
                logging.info("Backed up original file to %s", backup_file.name)

            source_for_mapping = backup_file
        else:
            source_for_mapping = input_file

    extracted_vars = load_variables(data_file)
    if extracted_vars:
        inject_variables(source_for_mapping, output_file, extracted_vars)
    else:
        logging.warning("No variables found in %s", data_file.name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Inject LaTeX variables from a data file into a target file.",
    )
    parser.add_argument("-d", "--dir", type=str, default=".", help="Project directory.")
    parser.add_argument("-i", "--input", type=str, required=True, help="Main .tex file (e.g., hp.tex).")
    parser.add_argument("-D", "--data", type=str, required=True, help="Data .tex file (e.g., 4-data.tex).")
    parser.add_argument("-o", "--output", type=str, default="", help="Optional separate output filename.")

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    args = parser.parse_args()
    injectVars(args.dir, args.input, args.data, args.output)
