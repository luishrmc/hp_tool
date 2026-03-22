from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from conn.packet import kermit_encode
from conn.session import KermitSession
from tgv.TeX2txt import clean_latex_fragment, read_tex_with_includes
from tgv.genT49 import build_image_object


class AuditFixesTests(unittest.TestCase):
    def test_read_tex_with_includes_blocks_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            project = root / 'project'
            project.mkdir()
            outside = root / 'secret.tex'
            outside.write_text('SECRET', encoding='utf-8')
            main = project / 'hp.tex'
            main.write_text('before\\input{../secret}after', encoding='utf-8')

            expanded = read_tex_with_includes(main)

            self.assertEqual(expanded, 'before\\input{../secret}after')

    def test_build_image_object_blocks_escape_from_bmp_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base_dir = root / 'HP'
            allowed_dir = root / 'img' / 'bmp_images'
            allowed_dir.mkdir(parents=True)
            base_dir.mkdir()
            outside = root / 'outside.bmp'
            Image.new('1', (2, 2), 1).save(outside)

            grob = build_image_object('../../../outside.bmp', base_dir, '../img/bmp_images')

            self.assertEqual(grob, b'')

    def test_clean_latex_fragment_handles_nested_frac_and_sqrt(self) -> None:
        fragment = r'\frac{1}{\frac{2}{\sqrt{9}}}'

        cleaned = clean_latex_fragment(fragment, None)

        self.assertEqual(cleaned, '(1)/((2)/(√(9)))')

    def test_build_chunk_matches_reference_encoding(self) -> None:
        session = KermitSession(transport=object())
        session.max_encoded_data = 12
        payload = b'ABC\x01#DEF\x7fGHI'

        chunk = session._build_chunk(payload, 0)

        self.assertEqual(chunk['encoded'], kermit_encode(chunk['raw'], qctl=ord('#'), qbin=None))
        self.assertLessEqual(len(chunk['encoded']), session.max_encoded_data)
        self.assertGreater(len(chunk['raw']), 0)


if __name__ == '__main__':
    unittest.main()
