"""build-tgv command implementation."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from commands.base import Command, RunResult
from tgv.TeX2txt import convert_tex_to_hp_text
from tgv.genBMP import DiagramOptimizer
from tgv.genT49 import generate_t49
from tgv.injectVars import injectVars


class BuildTGVCommand(Command):
    """Build TGV-related artifacts from a project directory."""

    name = "build-tgv"
    help = "Build TGV artifacts from a project directory"

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        """Register CLI arguments for the build-tgv subcommand.

        Args:
            parser: Parser dedicated to this subcommand.
        """
        parser.add_argument("target_dir", help="Path to the project directory containing hp.tex and related assets")
        parser.add_argument("--tex-file", default="hp.tex", help="Main TeX input file name inside target_dir")
        parser.add_argument("--txt-file", default="hp.txt", help="Output text file name for the converted TeX content")
        parser.add_argument("--data-file", default="4-data.tex", help="Optional TeX data file used for variable injection")
        parser.add_argument("--inject-vars", action="store_true", help="run variable injection stage")
        parser.add_argument("--gen-imgs", action="store_true", help="run BMP generation stage")
        parser.add_argument("--gen-text", action="store_true", help="run TeX-to-text stage")
        parser.add_argument("--gen-t49", action="store_true", help="run T49 generation stage")

    def run(self, args: argparse.Namespace) -> RunResult:
        """Execute the selected build stages.

        Args:
            args: Parsed CLI arguments for this command.

        Returns:
            RunResult: Structured outcome describing success or failure.
        """
        logging.info("build-tgv command selected")

        target_dir = Path(args.target_dir).resolve()
        if not target_dir.is_dir():
            message = f"Target directory does not exist: {target_dir}"
            logging.error(message)
            return RunResult(ok=False, message=message)
        logging.info("Target directory: %s", target_dir)

        args_dict = vars(args)
        logging.debug("CLI arguments:\n%s", json.dumps(args_dict, indent=4))
        selected_stages = self._resolve_selected_stages(args)
        if not selected_stages:
            message = "No build stage selected. Use one of --inject-vars, --gen-imgs, --gen-text or --gen-t49"
            logging.error(message)
            return RunResult(ok=False, message=message)

        tex_path = target_dir / args.tex_file
        if not self._check_existence(tex_path, "TeX file"):
            return RunResult(ok=False, message=f"TeX file does not exist: {tex_path}")
        logging.debug("Resolved TeX path: %s", tex_path)

        out_dir = target_dir / "HP"
        out_dir.mkdir(parents=True, exist_ok=True)
        logging.debug("Resolved HP output path: %s", out_dir)
        txt_path = out_dir / args.txt_file
        t49_path = txt_path.with_suffix(".T49")

        logging.info("Selected TGV stages: %s", ", ".join(selected_stages))
        for stage_name in selected_stages:
            logging.info("[Running stage: %s]", stage_name)
            if stage_name == "inject-vars":
                data_path = target_dir / args.data_file
                if not self._check_existence(data_path, "Data file"):
                    logging.warning("Data file does not exist (will skip variable injection): %s", data_path)
                else:
                    output_name = f"{tex_path.stem}_injected{tex_path.suffix}"
                    injectVars(args.target_dir, args.tex_file, args.data_file, output_name)

            if stage_name == "gen-text":
                convert_tex_to_hp_text(tex_path, txt_path)
            if stage_name == "gen-t49":
                generate_t49(txt_path, t49_path)
            if stage_name == "gen-imgs":
                self._generate_images(target_dir)

        logging.info("[build-tgv completed]")
        return RunResult(
            ok=True,
            message="build-tgv completed successfully",
            data={
                "target_dir": str(target_dir),
                "selected_stages": selected_stages,
                "text_output": str(txt_path),
                "t49_output": str(t49_path),
            },
        )

    def _resolve_selected_stages(self, args: argparse.Namespace) -> list[str]:
        """Return the ordered list of build stages selected on the CLI.

        Args:
            args: Parsed CLI arguments.

        Returns:
            list[str]: Stage names in execution order.
        """
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
        """Check whether an expected path exists.

        Args:
            path: Path to validate.
            description: Human-readable label for logging.

        Returns:
            bool: True when the path exists, otherwise False.
        """
        if not path.exists():
            logging.error("%s does not exist: %s", description, path)
            return False
        return True

    def _generate_images(self, target_dir: Path) -> None:
        """Generate optimized BMP variants for source images.

        Args:
            target_dir: Root project directory containing the image folder.
        """
        img_src_path = target_dir / "img"
        bmp_options_path = img_src_path / "bmp_options"
        bmp_selected_path = img_src_path / "bmp_images"
        bmp_options_path.mkdir(parents=True, exist_ok=True)
        bmp_selected_path.mkdir(parents=True, exist_ok=True)

        if not img_src_path.is_dir():
            return

        supported_exts = {".png", ".jpg", ".jpeg", ".bmp"}
        optimizer = DiagramOptimizer()
        for img_file in img_src_path.iterdir():
            if img_file.is_file() and img_file.suffix.lower() in supported_exts:
                specific_opt_dir = bmp_options_path / img_file.stem
                optimizer.process_diagram(
                    input_path_str=str(img_file),
                    output_dir_str=str(specific_opt_dir),
                )
