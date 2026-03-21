"""uild-tgv command.

This command only validates the final CLI shape and logging flow.
It does not perform real TGV generation yet.
"""

from __future__ import annotations

import argparse
import logging
import json
from pathlib import Path

from commands.base import Command

from tgv.TeX2txt import convert_tex_to_hp_text
from tgv.genT49 import generate_t49


class BuildTGVCommand(Command):
    name = "build-tgv"
    help = "Build TGV artifacts from a project directory"

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("target_dir", help="Path to the project directory containing hp.tex and related assets")
        parser.add_argument("--tex-file", default="hp.tex", help="Main TeX input file name inside target_dir")
        parser.add_argument("--txt-file", default="hp.txt", help="Output text file name for the converted TeX content")
        parser.add_argument("--data-file", default="4-data.tex", help="Optional TeX data file used for variable injection")
        parser.add_argument("--inject-vars", action="store_true", help="run variable injection stage")
        parser.add_argument("--gen-imgs", action="store_true", help="run BMP generation stage")
        parser.add_argument("--gen-text", action="store_true", help="run TeX-to-text stage")
        parser.add_argument("--gen-t49", action="store_true", help="run T49 generation stage")
        parser.add_argument("--gen-all", action="store_true", help="run all TGV build stages")

    def run(self, args: argparse.Namespace) -> int:
        logging.info("build-tgv command selected")

        ## Validate target directory
        target_dir = Path(args.target_dir).resolve()
        if not target_dir.is_dir():
            logging.error("Target directory does not exist: %s", target_dir)
            return 1
        logging.info("Target directory: %s", target_dir)

        ## Validate arguments
        args_dict = vars(args)
        logging.debug("CLI arguments:\n%s", json.dumps(args_dict, indent=4))
        selected_stages = self._resolve_selected_stages(args)
        if not selected_stages:
            logging.error(
                "No build stage selected. Use one of --inject-vars, --gen-imgs, --gen-text, --gen-t49, or --gen-all."
            )
            return 2

        ## Validate input files and prepare output paths
        tex_path = target_dir / args.tex_file
        if not self._check_existence(tex_path, "TeX file"):
            return 3
        logging.debug("Resolved TeX path: %s", tex_path)

        data_path = target_dir / args.data_file
        if not self._check_existence(data_path, "Data file"):
            logging.warning("Data file does not exist (will skip variable injection): %s", data_path)
        logging.debug("Resolved data path: %s", data_path)

        out_dir = target_dir / "HP"
        if not out_dir.exists():
            logging.info("HP output directory does not exist, creating: %s", out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
        logging.debug("Resolved HP output path: %s", out_dir)
        txt_path = out_dir / args.txt_file
        t49_path = txt_path.with_suffix(".T49")

        ## Run selected stages
        logging.info("Selected TGV stages: %s", ", ".join(selected_stages))
        for stage_name in selected_stages:
            logging.info("[Running stage: %s]", stage_name)
            if stage_name == "gen-text":
                convert_tex_to_hp_text(tex_path, txt_path)
            if stage_name == "gen-t49":
                generate_t49(txt_path, t49_path)
        logging.info("[build-tgv completed]")
        return 0

    def _resolve_selected_stages(self, args: argparse.Namespace) -> list[str]:
        if args.gen_all:
            return ["inject-vars", "gen-imgs", "gen-text", "gen-t49"]

        stages: list[str] = []
        if args.inject_vars:
            stages.append("inject-vars")
        if args.gen_imgs:
            stages.append("gen-imgs")
        if args.gen_text:
            stages.append("gen-text")
        if args.gen_t49:
            stages.append("gen-t49")
        return stages

    def _check_existence(self, path: Path, description: str) -> bool:
        if not path.exists():
            logging.error("%s does not exist: %s", description, path)
            return False
        return True
