"""
HP50g TGV Pipeline: Diagram Optimizer (Model 0)
==============================================
This module converts high-resolution source images (PNG, JPG) into 1-bit monochrome
BMPs optimized for the HP50g's low-resolution screen. 

The optimizer generates 12 different 'Variations' for every input image. Each 
variation uses a different combination of sharpening, thickening, and 
thresholding. This allows the user to select the best-looking result for 
their specific diagram (e.g., circuit schematics need thick lines, while 
photos need dithering).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageOps
import logging


@dataclass(frozen=True)
class Variation:
    """
    Parameter set for a specific image transformation.
    - name: Filename suffix for this variation.
    - crop: Whether to auto-remove white borders.
    - pre_detail/unsharp: Sharpening filters applied before resizing.
    - pre_thicken: Line thickening applied to high-res source.
    - threshold: Grayscale value (0-255) for binarization.
    - post_thicken: Line thickening applied after downscaling.
    - margin: Padding pixels around the final image.
    """
    name: str
    crop: bool
    pre_detail: bool
    pre_unsharp: bool
    pre_thicken: int
    threshold: int
    post_thicken: int
    margin: int = 2
    # Advanced Modifiers
    edge_enhance: bool = False
    equalize: bool = False
    dither: bool = False


class DiagramOptimizer:
    """
    Orchestrates the conversion of diagrams into multiple monochrome 1-bit 
    BMP variations and generates a summary preview sheet.
    """

    # High-quality Lanczos resampling is used for the downscale step
    RESIZE_METHOD = Image.Resampling.LANCZOS

    def __init__(
        self,
        white_crop_threshold: int = 245,
        preview_scale: int = 3,
    ) -> None:
        """
        Initializes the optimizer.
        - white_crop_threshold: Pixels brighter than this are treated as 'empty' border.
        - preview_scale: Upscale factor for the final preview.png grid.
        """
        self.white_crop_threshold = white_crop_threshold
        self.preview_scale = preview_scale

    def _crop_white_borders(self, gray: Image.Image) -> Image.Image:
        """Removes excessive white space around a diagram to maximize detail."""
        lut = [0 if value >= self.white_crop_threshold else 255 for value in range(256)]
        mask = gray.point(lut, mode="L")
        bbox = mask.getbbox()
        if bbox is None:
            return gray.copy()
        return gray.crop(bbox)

    def _resize_to_fit(self, img: Image.Image, target_w: int, target_h: int, margin: int) -> Image.Image:
        """Resizes the image to fit within the HP50g screen dimensions while maintaining aspect ratio."""
        src_w, src_h = img.size
        usable_w = max(1, target_w - 2 * margin)
        usable_h = max(1, target_h - 2 * margin)

        scale = min(usable_w / src_w, usable_h / src_h)
        new_w = max(1, int(round(src_w * scale)))
        new_h = max(1, int(round(src_h * scale)))
        return img.resize((new_w, new_h), resample=self.RESIZE_METHOD)

    def _binarize(self, img: Image.Image, threshold: int) -> Image.Image:
        """Converts grayscale to pure black/white using a fixed threshold."""
        lut = [0 if value <= threshold else 255 for value in range(256)]
        return img.point(lut, mode="L")

    def _thicken_lines(self, img: Image.Image, amount: int) -> Image.Image:
        """Expands dark pixels (lines) using a MinFilter to make them survive the low-res screen."""
        if amount <= 0:
            return img
        for _ in range(amount):
            img = img.filter(ImageFilter.MinFilter(size=3))
        return img

    def _center_on_canvas(self, img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """Pastes the processed diagram onto a white canvas of the exact HP50g GROB size."""
        canvas = Image.new("L", (target_w, target_h), 255)
        offset_x = (target_w - img.width) // 2
        offset_y = (target_h - img.height) // 2
        canvas.paste(img, (offset_x, offset_y))
        return canvas

    def _prepare_base(self, input_path: Path) -> Image.Image:
        """Loads and converts the input image to Grayscale (L mode)."""
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
        """The main transformation pipeline for a single variation."""
        img = base_gray.copy()
        
        # 1. Global Contrast Correction (equalize helps with bad lighting)
        if variation.equalize:
            img = ImageOps.equalize(img)
        else:
            img = ImageOps.autocontrast(img, cutoff=0)

        # 2. Border Cropping
        if variation.crop:
            img = self._crop_white_borders(img)

        # 3. High-Res Filtering (Detail/Unsharp sharpen the image)
        if variation.edge_enhance:
            img = img.filter(ImageFilter.EDGE_ENHANCE_MORE)
        if variation.pre_detail:
            img = img.filter(ImageFilter.DETAIL)
        if variation.pre_unsharp:
            img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=180, threshold=2))

        # 4. Pre-Resize Dilation (thickens lines while resolution is still high)
        actual_pre_thicken = max(0, variation.pre_thicken + thicken_amount - 2)
        img = self._thicken_lines(img, actual_pre_thicken)
        
        # 5. Downscale to HP50g size
        img = self._resize_to_fit(img, target_w, target_h, variation.margin)

        # 6. Binarization Strategy (Dithering is better for gradients/photos)
        if variation.dither:
            img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")
        else:
            img = self._binarize(img, variation.threshold)

        # 7. Post-Resize Dilation (thicken lines at the final resolution)
        img = self._thicken_lines(img, variation.post_thicken)
        
        # 8. Canvas Formatting
        img = self._center_on_canvas(img, target_w, target_h)
        return img.convert("1", dither=Image.Dither.NONE)

    def _default_variations(self) -> list[Variation]:
        """Defines the 12 presets to be generated for every image."""
        return [
            # --- Standard Diagram Optimizations ---
            Variation("01_standard_soft", True, True, False, 2, 150, 0),
            Variation("02_standard_strong", True, True, False, 3, 125, 0),
            Variation("03_post_thicken_only", True, False, True, 0, 165, 1),
            Variation("04_hybrid_thicken", True, True, True, 1, 145, 1),
            
            # --- Advanced Filtering ---
            Variation("05_fine_lines", True, False, True, 1, 175, 0),
            Variation(
                name="06_edge_enhanced", # Good for blurry or faint inputs
                crop=True, pre_detail=False, pre_unsharp=False, pre_thicken=1, 
                threshold=150, post_thicken=0, edge_enhance=True
            ),
            Variation(
                name="07_equalized_contrast", # Good for uneven background lighting
                crop=True, pre_detail=True, pre_unsharp=False, pre_thicken=2, 
                threshold=140, post_thicken=0, equalize=True
            ),
            Variation(
                name="08_dithered_photo", # Mandatory for photos/3D gradients
                crop=True, pre_detail=False, pre_unsharp=True, pre_thicken=0, 
                threshold=128, post_thicken=0, dither=True
            ),

            # --- Structural Overrides ---
            Variation("09_fullframe_margin", False, True, False, 2, 135, 0, margin=1),
            Variation("10_extreme_bold", True, True, True, 4, 110, 1),
            Variation("11_extreme_thin", True, False, False, 0, 200, 0),
            Variation("12_raw_baseline", False, False, False, 0, 128, 0), # Pure conversion
        ]

    def _build_preview(self, images: list[tuple[str, Image.Image]], output_path: Path) -> None:
        """Creates a single PNG grid containing all 12 variations for easy side-by-side comparison."""
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
            x = gap + col * (cell_w + gap)
            y = gap + row * (cell_h + label_h + gap)

            # Nearest neighbor keeps pixels sharp in the zoomed preview
            scaled = img.convert("L").resize((cell_w, cell_h), resample=Image.Resampling.NEAREST)
            preview.paste(scaled, (x, y))
            draw.rectangle((x - 1, y - 1, x + cell_w, y + cell_h), outline=0)
            draw.text((x + 2, y + cell_h + 4), name, fill=0)

        preview.save(output_path, format="PNG")

    def process_diagram(
        self,
        input_path_str: str,
        output_dir_str: str,
        target_w: int = 130,
        target_h: int = 72,
        thicken_amount: int = 2,
    ) -> list[Path]:
        """
        Main method to process a diagram file. 
        It saves 12 BMP variations and 1 preview PNG to the output directory.
        """
        input_path = Path(input_path_str)
        output_dir = Path(output_dir_str)
        output_dir.mkdir(parents=True, exist_ok=True)

        logging.info(f"Optimizing image: {input_path.name}")

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
        logging.info(f"Preview generated: {preview_path.name}")

        return saved_paths

if __name__ == "__main__":
    # Test execution
    optimizer = DiagramOptimizer()
    optimizer.process_diagram(
        "test/input/diagram_highres.png",
        "test/output/0_optimized_diagram_variations",
        target_w=130,
        target_h=72,
        thicken_amount=3, 
    )
