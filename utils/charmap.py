# -----------------------------------------------------------------------------
# TGV / HP50g character map
#
# This table should be understood as a TGV-specific single-byte glyph map, not
# as plain Unicode, UTF-8, or raw ISO-8859-1 text.
#
# Practical model
# - The .T49 payload used by TGV behaves like a stream of 1-byte glyph codes.
# - Standard printable ASCII usually passes through unchanged.
# - Many mathematical and Greek symbols live in the extended 8-bit range.
# - Some low control-range values (for example 0x04..0x1F) are also reused as
#   printable glyph slots by TGV.
#
# Relationship to HP character sets
# - This map is related to the classic HP48/49 RPL character set family:
#   several symbols appear in the same general byte regions used by HP for
#   math and calculator glyphs.
# - However, this map is NOT identical to the standard HP48/49 character map.
# - Some code points match known HP/RPL positions, while others are clearly
#   reassigned by TGV / WinHP.
# - Because of that, this file should be treated as a viewer/font glyph map
#   for TGV content, not as a universal HP50g text encoding table.
#
# Important implications
# - A byte here means "display this glyph in TGV", not necessarily "this is the
#   official OS-wide encoding for the same Unicode character".
# - The same symbol may exist at a different byte in standard HP48/49 text.
# - Some entries in this table intentionally use semantic placeholders rather
#   than true Unicode characters when TGV exposes a special display symbol that
#   does not map cleanly to normal text authoring.
#
# Source of truth for this map
# - The entries in this file were derived and validated from WinHP-generated
#   .T49 examples and then confirmed by rendering on the HP50g screen.
# - Therefore, this map reflects observed TGV behavior first.
# - External HP48/49 charset references are useful for comparison and for
#   finding related symbols, but they must not override a verified TGV sample.
#
# Recommended maintenance rule
# - Treat this table as a verified TGV glyph map.
# - When adding new symbols, prefer the following process:
#   1. Generate a minimal .T49 example in WinHP containing only the target
#      symbol or the smallest possible controlled sample.
#   2. Extract the payload byte used for that symbol.
#   3. Validate the generated file on the HP50g screen.
#   4. Add the new entry here with a short note about its origin.
#
# Suggested interpretation of entry status
# - "verified": confirmed from WinHP sample and HP50g rendering
# - "compatible": matches both TGV behavior and known HP48/49 conventions
# - "remapped": valid for TGV, but differs from standard HP48/49 expectations
#
# In short:
# This is best viewed as a TGV font/glyph encoding layer for .T49 generation.
# It is related to HP48/49 character conventions, but it is not identical to
# the standard HP RPL charset and should be maintained from verified samples.
# -----------------------------------------------------------------------------

HP_HEX_MAP = {
    # Greek & Math Symbols
    "ν": b"\x04",   # \nu
    "ℵ": b"\x05",   # \aleph
    "Λ": b"\x06",   # \Lambda
    "Γ": b"\x07",   # \Gamma
    "Φ": b"\x08",   # \Phi
    "Ψ": b"\x09",   # \Psi

    "ℬ": b"\x0C",   # \mathcal{B}
    "𝒞": b"\x0E",   # \mathcal{C}
    "𝒟": b"\x0F",   # \mathcal{D}
    "ℰ": b"\x10",   # \mathcal{E}
    "ℱ": b"\x12",   # \mathcal{F}
    "𝒫": b"\x13",   # \mathcal{P}
    "ℜ": b"\x16",   # \Re
    "ξ": b"\x17",   # \xi
    "ℕ": b"\x18",   # \mathbb{N}
    "ℤ": b"\x19",   # \mathbb{Z}
    "ℚ": b"\x1A",   # \mathbb{Q}
    "ℝ": b"\x1B",   # \mathbb{R}
    "ℂ": b"\x1C",   # \mathbb{C}

    # HP-specific formatting symbols (mapped from WinHP hex dump and manual testing)
    "🔟": b"\x1D",  # 10^- (Placeholder emoji for 10^-)
    "⏨": b"\x1F",   # 10^  (Placeholder unicode for 10^)
    "…": b"\x27",   # \ldots (Mapped to 0x27 / standard apostrophe by WinHP)

    # Extended Math & Greek Symbols
    "∠": b"\x80",   # \angle
    "∇": b"\x81",   # \nabla
    "ᶺ": b"\x82",   # special HP caret (to preserve standard ASCII ^ at 0x5E)
    "√": b"\x83",   # \sqrt
    "∫": b"\x84",   # \int
    "Σ": b"\x85",   # \sum
    "▶": b"\x86",   # \blacktriangleright
    "π": b"\x87",   # \pi
    "∂": b"\x88",   # \partial
    "≤": b"\x89",   # \leq
    "≥": b"\x8A",   # \geq
    "≠": b"\x8B",   # \neq
    "α": b"\x8C",   # \alpha
    "→": b"\x8D",   # \rightarrow
    "←": b"\x8E",   # \leftarrow
    "↓": b"\x8F",   # \downarrow
    "↑": b"\x90",   # \uparrow
    "γ": b"\x91",   # \gamma
    "δ": b"\x92",   # \delta
    "ε": b"\x93",   # \epsilon
    "η": b"\x94",   # \eta
    "Θ": b"\x95",   # \Theta
    "λ": b"\x96",   # \lambda
    "ρ": b"\x97",   # \rho
    "σ": b"\x98",   # \sigma
    "τ": b"\x99",   # \tau
    "ω": b"\x9A",   # \omega
    "Δ": b"\x9B",   # \Delta
    "Π": b"\x9C",   # \Pi
    "Ω": b"\x9D",   # \Omega
    "▵": b"\x9E",   # secondary \Delta
    "∞": b"\x9F",   # \infty

    "∥": b"\xA0",   # \parallel
    "≈": b"\xC7",   # \thickapprox
    "∈": b"\xD2",   # \in
    "∉": b"\xD3",   # \notin
    "⊂": b"\xD4",   # \subset
    "∀": b"\xD5",   # \forall
    "⊕": b"\xD6",   # \oplus
    "φ": b"\xD8",   # \phi
    "β": b"\xDF",   # \beta (HP overwrites Latin-1 'ß')
    "⊥": b"\xF2",   # \perp
    "≦": b"\xFE",   # secondary \leq
    "≧": b"\xFF",   # secondary \geq
	
    # Explicit Latin-1 / Unicode forced mappings
    "±": b"\xB1",   # \pm
    "μ": b"\xB5",   # \mu (Greek mu forced to HP micro sign)
    "·": b"\xB7",   # \cdot
    "×": b"\xD7",   # \times
}

# Add this below your existing HP_HEX_MAP in charmap.py

LATEX_TO_CHAR_MAP = {
    r"\nu": "ν",
    r"\aleph": "ℵ",
    r"\Lambda": "Λ",
    r"\Gamma": "Γ",
    r"\Phi": "Φ",
    r"\Psi": "Ψ",
    r"\mathcal{B}": "ℬ",
    r"\mathcal{C}": "𝒞",
    r"\mathcal{D}": "𝒟",
    r"\mathcal{E}": "ℰ",
    r"\mathcal{F}": "ℱ",
    r"\mathcal{P}": "𝒫",
    r"\Re": "ℜ",
    r"\xi": "ξ",
    r"\mathbb{N}": "ℕ",
    r"\mathbb{Z}": "ℤ",
    r"\mathbb{Q}": "ℚ",
    r"\mathbb{R}": "ℝ",
    r"\mathbb{C}": "ℂ",
    r"\angle": "∠",
    r"\nabla": "∇",
    r"\sqrt": "√",
    r"\int": "∫",
    r"\sum": "Σ",
    r"\pi": "π",
    r"\partial": "∂",
    r"\leq": "≤",
    r"\geq": "≥",
    r"\neq": "≠",
    r"\alpha": "α",
    r"\rightarrow": "→",
    r"\leftarrow": "←",
    r"\downarrow": "↓",
    r"\uparrow": "↑",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\epsilon": "ε",
    r"\eta": "η",
    r"\Theta": "Θ",
    r"\lambda": "λ",
    r"\rho": "ρ",
    r"\sigma": "σ",
    r"\tau": "τ",
    r"\omega": "ω",
    r"\Delta": "Δ",
    r"\Pi": "Π",
    r"\Omega": "Ω",
    r"\infty": "∞",
    r"\parallel": "∥",
    r"\approx": "≈",
    r"\in": "∈",
    r"\notin": "∉",
    r"\subset": "⊂",
    r"\forall": "∀",
    r"\oplus": "⊕",
    r"\phi": "φ",
    r"\beta": "β",
    r"\perp": "⊥",
    r"\pm": "±",
    r"\mu": "μ",
    r"\cdot": "·",
    r"\times": "×"
}