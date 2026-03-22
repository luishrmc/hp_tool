"""BMP optimization helpers for HP50g-sized diagrams."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import logging
from PIL import Image, ImageDraw, ImageFilter, ImageOps


@dataclass(frozen=True)
class Variation:
    """Describe one image-processing preset for BMP generation.

    Attributes:
        name: Filename suffix for the generated variation.
        crop: Whether to crop white borders before resizing.
        pre_detail: Whether to apply the detail filter before resizing.
        pre_unsharp: Whether to apply an unsharp mask before resizing.
        pre_thicken: Amount of thickening before resizing.
        threshold: Binarization threshold for non-dithered output.
        post_thicken: Amount of thickening after resizing.
        margin: Padding around the final image on the target canvas.
        edge_enhance: Whether to apply edge enhancement before resizing.
        equalize: Whether to equalize contrast before resizing.
        dither: Whether to use dithering instead of simple thresholding.
    """

    name: str
    crop: bool
    pre_detail: bool
    pre_unsharp: bool
    pre_thicken: int
    threshold: int
    post_thicken: int
    margin: int = 2
    edge_enhance: bool = False
    equalize: bool = False
    dither: bool = False


class DiagramOptimizer:
    """Generate HP50g-friendly monochrome BMP variants from source images."""

    RESIZE_METHOD = Image.Resampling.LANCZOS

    def __init__(
        self,
        white_crop_threshold: int = 245,
        preview_scale: int = 3,
    ) -> None:
        """Configure image optimization defaults.

        Args:
            white_crop_threshold: Pixels brighter than this are treated as empty border.
            preview_scale: Upscale factor for generated preview sheets.
        """
        self.white_crop_threshold = white_crop_threshold
        self.preview_scale = preview_scale

    def _crop_white_borders(self, gray: Image.Image) -> Image.Image:
        """Remove large white borders around an image."""
        lut = [0 if value >= self.white_crop_threshold else 255 for value in range(256)]
        mask = gray.point(lut, mode="L")
        bbox = mask.getbbox()
        if bbox is None:
            return gray.copy()
        return gray.crop(bbox)

    def _resize_to_fit(self, img: Image.Image, target_w: int, target_h: int, margin: int) -> Image.Image:
        """Resize an image to fit the calculator display bounds."""
        src_w, src_h = img.size
        usable_w = max(1, target_w - 2 * margin)
        usable_h = max(1, target_h - 2 * margin)

        scale = min(usable_w / src_w, usable_h / src_h)
        new_w = max(1, int(round(src_w * scale)))
        new_h = max(1, int(round(src_h * scale)))
        return img.resize((new_w, new_h), resample=self.RESIZE_METHOD)

    def _binarize(self, img: Image.Image, threshold: int) -> Image.Image:
        """Convert a grayscale image to black and white using a threshold."""
        lut = [0 if value <= threshold else 255 for value in range(256)]
        return img.point(lut, mode="L")

    def _thicken_lines(self, img: Image.Image, amount: int) -> Image.Image:
        """Expand dark pixels to preserve thin strokes at low resolution."""
        if amount <= 0:
            return img
        for _ in range(amount):
            img = img.filter(ImageFilter.MinFilter(size=3))
        return img

    def _center_on_canvas(self, img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """Center an image on a fixed-size white canvas."""
        canvas = Image.new("L", (target_w, target_h), 255)
        offset_x = (target_w - img.width) // 2
        offset_y = (target_h - img.height) // 2
        canvas.paste(img, (offset_x, offset_y))
        return canvas

    def _prepare_base(self, input_path: Path) -> Image.Image:
        """Load a source image as grayscale.

        Args:
            input_path: Source image path.

        Returns:
            Image.Image: Grayscale source image.

        Raises:
            FileNotFoundError: If the input image does not exist.
        """
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        return Image.open(input_path).convert("L")

    def _apply_variation(
        self,
        base_gray: Image.Image,
        variation: Variation,
        target_w: int,
        target_h: int,
        thicken_amount: int,
    ) -> Image.Image:
        """Apply one variation preset to a source image."""
        img = base_gray.copy()

        if variation.equalize:
            img = ImageOps.equalize(img)
        else:
            img = ImageOps.autocontrast(img, cutoff=0)

        if variation.crop:
            img = self._crop_white_borders(img)

        if variation.edge_enhance:
            img = img.filter(ImageFilter.EDGE_ENHANCE_MORE)
        if variation.pre_detail:
            img = img.filter(ImageFilter.DETAIL)
        if variation.pre_unsharp:
            img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=180, threshold=2))

        actual_pre_thicken = max(0, variation.pre_thicken + thicken_amount - 2)
        img = self._thicken_lines(img, actual_pre_thicken)
        img = self._resize_to_fit(img, target_w, target_h, variation.margin)

        if variation.dither:
            img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")
        else:
            img = self._binarize(img, variation.threshold)

        img = self._thicken_lines(img, variation.post_thicken)
        img = self._center_on_canvas(img, target_w, target_h)
        return img.convert("1", dither=Image.Dither.NONE)

    def _default_variations(self) -> list[Variation]:
        """Return the preset variation list used for image generation."""
        return [
            Variation("01_standard_soft", True, True, False, 2, 150, 0),
            Variation("02_standard_strong", True, True, False, 3, 125, 0),
            Variation("03_post_thicken_only", True, False, True, 0, 165, 1),
            Variation("04_hybrid_thicken", True, True, True, 1, 145, 1),
            Variation("05_fine_lines", True, False, True, 1, 175, 0),
            Variation(
                name="06_edge_enhanced",
                crop=True,
                pre_detail=False,
                pre_unsharp=False,
                pre_thicken=1,
                threshold=150,
                post_thicken=0,
                edge_enhance=True,
            ),
            Variation(
                name="07_equalized_contrast",
                crop=True,
                pre_detail=True,
                pre_unsharp=False,
                pre_thicken=2,
                threshold=140,
                post_thicken=0,
                equalize=True,
            ),
            Variation(
                name="08_dithered_photo",
                crop=True,
                pre_detail=False,
                pre_unsharp=True,
                pre_thicken=0,
                threshold=128,
                post_thicken=0,
                dither=True,
            ),
            Variation("09_fullframe_margin", False, True, False, 2, 135, 0, margin=1),
            Variation("10_extreme_bold", True, True, True, 4, 110, 1),
            Variation("11_extreme_thin", True, False, False, 0, 200, 0),
            Variation("12_raw_baseline", False, False, False, 0, 128, 0),
        ]

    def _build_preview(self, images: list[tuple[str, Image.Image]], output_path: Path) -> None:
        """Build a grid preview of generated image variations."""
        if not images:
            return

        cell_w = images[0][1].width * self.preview_scale
        cell_h = images[0][1].height * self.preview_scale
        label_h = 22
        gap = 10
        cols = 3
        rows = (len(images) + cols - 1) // cols

        preview_w = cols * cell_w + (cols + 1) * gap
        preview_h = rows * (cell_h + label_h) + (rows + 1) * gap
        preview = Image.new("L", (preview_w, preview_h), 255)
        draw = ImageDraw.Draw(preview)

        for idx, (name, img) in enumerate(images):
            row = idx // cols
            col = idx % cols
            x_pos = gap + col * (cell_w + gap)
            y_pos = gap + row * (cell_h + label_h + gap)
            scaled = img.convert("L").resize((cell_w, cell_h), resample=Image.Resampling.NEAREST)
            preview.paste(scaled, (x_pos, y_pos))
            draw.rectangle((x_pos - 1, y_pos - 1, x_pos + cell_w, y_pos + cell_h), outline=0)
            draw.text((x_pos + 2, y_pos + cell_h + 4), name, fill=0)

        preview.save(output_path, format="PNG")

    def process_diagram(
        self,
        input_path_str: str,
        output_dir_str: str,
        target_w: int = 130,
        target_h: int = 72,
        thicken_amount: int = 2,
    ) -> list[Path]:
        """Generate BMP variants and a preview sheet for one source image.

        Args:
            input_path_str: Source image path.
            output_dir_str: Directory that receives generated assets.
            target_w: Target canvas width in pixels.
            target_h: Target canvas height in pixels.
            thicken_amount: Global line-thickening adjustment.

        Returns:
            list[Path]: Paths to the generated BMP files.

        Raises:
            FileNotFoundError: If the input image does not exist.
        """
        input_path = Path(input_path_str)
        output_dir = Path(output_dir_str)
        output_dir.mkdir(parents=True, exist_ok=True)

        logging.info("Optimizing image: %s", input_path.name)

        base_gray = self._prepare_base(input_path)
        base_name = input_path.stem
        saved_paths: list[Path] = []
        preview_items: list[tuple[str, Image.Image]] = []

        for variation in self._default_variations():
            final_image = self._apply_variation(
                base_gray,
                variation,
                target_w,
                target_h,
                thicken_amount,
            )
            output_path = output_dir / f"{base_name}_{variation.name}.bmp"
            final_image.save(output_path, format="BMP")
            saved_paths.append(output_path)
            preview_items.append((variation.name, final_image))

        preview_path = output_dir / f"{base_name}_preview.png"
        self._build_preview(preview_items, preview_path)
        logging.info("Preview generated: %s", preview_path.name)

        return saved_paths


if __name__ == "__main__":
    optimizer = DiagramOptimizer()
    optimizer.process_diagram(
        "test/input/diagram_highres.png",
        "test/output/0_optimized_diagram_variations",
        target_w=130,
        target_h=72,
        thicken_amount=3,
    )
