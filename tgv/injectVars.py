"""
HP50g TGV Pipeline: Variable Injection Module
=============================================
This module automates the replacement of custom LaTeX commands with their actual
values. It allows for a 'Template' workflow where the main document (hp.tex) 
contains placeholders that are dynamically filled from a data file (4-data.tex).

Workflow:
1. Load: Scans the data file for \newcommand{\'VAR}{VAL} definitions.
2. Backup: Creates a copy of the original source to prevent data loss.
3. Inject: Replaces all instances of \'VAR in the source with VAL.

Key Features:
- Supports nested braces (e.g., 10^{-3}) in LaTeX values.
- Longest-match-first sorting to prevent partial word replacements.
- Automatic backup of original source files.
"""

import argparse
import re
import shutil
from pathlib import Path

def load_variables(data_file_path: Path) -> dict:
    """
    STEP 1: EXTRACTION
    Reads a 'data' LaTeX file and finds all instances of \newcommand{\\Name}{Value}.
    """
    variables = {}
    
    if not data_file_path.exists():
        print(f"[ERROR] Data file not found: {data_file_path}")
        return variables

    with open(data_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # REGEX EXPLANATION:
    # \\newcommand\{\\([a-zA-Z0-9]+)\} -> Matches the command name (e.g., \HMax)
    # \{((?:[^{}]|\{[^{}]*\})*)\}      -> Matches the value, allowing for one level 
    #                                     of nested braces like {10^{-3}}
    pattern = re.compile(r'\\newcommand\{\\([a-zA-Z0-9]+)\}\{((?:[^{}]|\{[^{}]*\})*)\}')
    matches = pattern.findall(content)
    
    for var_name, var_value in matches:
        variables[var_name] = var_value # Stores as {'HMax': '150', 'VarB': '20'}
        
    return variables

def inject_variables(target_file_path: Path, output_file_path: Path, variables: dict):
    """
    STEP 2: INJECTION
    Finds placeholders in your main text and swaps them for the real values.
    """
    if not target_file_path.exists():
        print(f"[ERROR] Target file not found: {target_file_path}")
        return

    with open(target_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Sort by name length (descending). 
    # This prevents replacing '\Var' if the command is actually '\Variable'.
    sorted_vars = sorted(variables.items(), key=lambda x: len(x[0]), reverse=True)
    
    for var_name, var_value in sorted_vars:
        # (?![a-zA-Z]) ensures we match the end of the command and not a longer word
        pattern = r'\\' + re.escape(var_name) + r'(?![a-zA-Z])'
        
        # Use a lambda for replacement to ensure backslashes in the value 
        # (like 10^{-3}) aren't treated as escape characters by re.sub.
        content = re.sub(pattern, lambda _: var_value, content)
        
    # Write the updated text to the new file
    output_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print(f"[INFO] Successfully injected {len(variables)} variables into {output_file_path.name}")

def injectVars(dir_path: str, input_name: str, data_name: str, output_name: str = "") -> None:
    """
    ORCHESTRATION & BACKUP logic.
    Handles file paths and ensures we don't accidentally lose the original 'clean' source.
    """
    base_dir = Path(dir_path)
    data_file = base_dir / data_name
    input_file = base_dir / input_name
    
    if output_name:
        # Case A: We are outputting to a different file (no overwrite)
        output_file = base_dir / output_name
        source_for_mapping = input_file
    else:
        # Case B: We are overwriting the original (Standard for this pipeline)
        output_file = input_file
        # Create a backup (e.g., hp_org.tex) so we can run the script many times 
        # without "double-injecting" or losing the original commands.
        backup_file = base_dir / f"{input_file.stem}_org{input_file.suffix}"
        
        if input_file.exists():
            if not backup_file.exists():
                shutil.copy2(input_file, backup_file)
                print(f"[INFO] Backed up original file to {backup_file.name}")
            
            # We always use the 'clean' backup as the source for replacements
            source_for_mapping = backup_file
        else:
            source_for_mapping = input_file
    
    # Run the extraction and injection
    extracted_vars = load_variables(data_file)
    if extracted_vars:
        inject_variables(source_for_mapping, output_file, extracted_vars)
    else:
        print(f"[WARNING] No variables found in {data_file.name}")

if __name__ == "__main__":
    # Standard CLI argument parsing
    parser = argparse.ArgumentParser(description="Inject LaTeX variables from a data file into a target file.")
    parser.add_argument("-d", "--dir", type=str, default=".", help="Project directory.")
    parser.add_argument("-i", "--input", type=str, required=True, help="Main .tex file (e.g., hp.tex).")
    parser.add_argument("-D", "--data", type=str, required=True, help="Data .tex file (e.g., 4-data.tex).")
    parser.add_argument("-o", "--output", type=str, default="", help="Optional separate output filename.")
    
    args = parser.parse_args()
    injectVars(args.dir, args.input, args.data, args.output)
