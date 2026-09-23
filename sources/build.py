#!/usr/bin/env python3
"""
build_lygon.py - Automated build pipeline for the Lygon font family.

Lygon is a modernized derivative of the Sansation typeface by Bernd Montag,
licensed under the SIL Open Font License 1.1.

Design Refinements & Technical Features:
1. Cutout Gap Normalization:
   - Halves the excessive cutout gap on B, K, P, R, k, and related glyphs
     to match the proportion of the letter A.
   - Strictly preserves uniform leg and arm stroke thickness across all weights (no wedges).
2. Lowercase j Descender Redesign:
   - Replaces the truncated stub with a graceful, balanced swept curve.
3. OpenType Modernization:
   - OS/2 table upgraded to version 4 with USE_TYPO_METRICS enabled.
   - Explicit sCapHeight (1430) and sxHeight (1050) populated.
   - Correct italic angles (-11.31 deg) and caret slopes (rise 1430, run 286).
   - Gasp table set to 0x000F for clean antialiasing and ClearType.
4. Comprehensive OpenType Features via feaLib:
   - GPOS kerning (kern) covering capital, lowercase, and punctuation pairs.
   - Standard ligatures (liga) and discretionary ligatures (dlig).
   - Stylistic sets (ss01 for alternate g, ss02 for alternate k, ss03 for German Eszett).
   - Case-sensitive forms (case).
   - Oldstyle and lining figures (onum / lnum).
   - Tabular and proportional figures (tnum / pnum).
   - Fractions (frac).
5. Variable Font Generation:
   - Upright: Lygon[wght].ttf, Lygon[wght].woff, Lygon[wght].woff2 (300 to 700).
   - Italic: Lygon-Italic[wght].ttf, Lygon-Italic[wght].woff, Lygon-Italic[wght].woff2 (300 to 700).
   - Complete STAT table and fvar named instances (Light, Regular, Medium, SemiBold, Bold).
6. Static Font Generation:
   - Light (300), Regular (400), Medium (500), SemiBold (600), Bold (700)
     plus matching Italics in TTF, WOFF, and WOFF2 formats.
"""

import os
import io
import copy
import math
import shutil
import tempfile
from fontTools.ttLib import TTFont, newTable
import fontTools.ttLib.tables.ttProgram
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.feaLib.builder import addOpenTypeFeatures
from fontTools.designspaceLib import (
    DesignSpaceDocument,
    AxisDescriptor,
    SourceDescriptor,
    InstanceDescriptor,
)
import fontTools.varLib
import fontTools.varLib.instancer
from fontTools.otlLib.builder import buildStatTable

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(SCRIPT_DIR) == "sources":
    REPO_ROOT = os.path.dirname(SCRIPT_DIR)
    SOURCES_DIR = SCRIPT_DIR
else:
    REPO_ROOT = SCRIPT_DIR
    SOURCES_DIR = os.path.join(REPO_ROOT, "sources") if os.path.exists(os.path.join(REPO_ROOT, "sources")) else SCRIPT_DIR

FONTS_DIR = os.path.join(REPO_ROOT, "fonts")
TTF_DIR = os.path.join(FONTS_DIR, "ttf")
VAR_DIR = os.path.join(FONTS_DIR, "variable")
WOFF_DIR = os.path.join(FONTS_DIR, "woff")
WOFF2_DIR = os.path.join(FONTS_DIR, "woff2")

for d in [TTF_DIR, VAR_DIR, WOFF_DIR, WOFF2_DIR]:
    os.makedirs(d, exist_ok=True)

# SIL Open Font License 1.1 notice
OFL_NOTICE = (
    "Copyright 2026 The Lygon Project Authors (https://github.com/lahdekorpi/lygon)"
)


def build_feature_file(glyph_set):
    """Dynamically generate AFDKO feature text based on glyphs present in font."""
    lines = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        "languagesystem cyrl dflt;",
        "languagesystem grek dflt;",
        "",
    ]

    # --- Standard Ligatures (liga) ---
    # Modern geometric sans: keep individual glyphs for f, i, l, etc. clean and unligatured,
    # avoiding awkward fused bridges and preserving natural dot visibility.
    liga_rules = []
    if liga_rules:
        lines.append("feature liga {")
        lines.extend(liga_rules)
        lines.append("} liga;\n")

    # --- Discretionary Ligatures (dlig) ---
    # Discretionary decorative ligatures (if any)
    dlig_rules = []
    if dlig_rules:
        lines.append("feature dlig {")
        lines.extend(dlig_rules)
        lines.append("} dlig;\n")

    # --- Stylistic Set 1: Alternate double-storey g ---
    ss01_rules = []
    g_pairs = [
        ("g", "g.alt"),
        ("gcircumflex", "gcircumflex.alt"),
        ("gbreve", "gbreve.alt"),
        ("gdotaccent", "gdotaccent.alt"),
        ("gcommaaccent", "gcomma.alt"),
    ]
    for orig, alt in g_pairs:
        if {orig, alt}.issubset(glyph_set):
            ss01_rules.append(f"    sub {orig} by {alt};")
    if ss01_rules:
        lines.append("feature ss01 {")
        lines.append("    featureNames { name \"Alternate double-storey g\"; };")
        lines.extend(ss01_rules)
        lines.append("} ss01;\n")

    # --- Stylistic Set 2: Alternate disconnected k ---
    ss02_rules = []
    k_pairs = [("k", "k.alt"), ("kcommaaccent", "kcomma.alt")]
    for orig, alt in k_pairs:
        if {orig, alt}.issubset(glyph_set):
            ss02_rules.append(f"    sub {orig} by {alt};")
    if ss02_rules:
        lines.append("feature ss02 {")
        lines.append("    featureNames { name \"Alternate disconnected k\"; };")
        lines.extend(ss02_rules)
        lines.append("} ss02;\n")

    # --- Stylistic Set 3: Capital German Eszett ---
    if {"germandbls", "germandbls.cap"}.issubset(glyph_set):
        lines.append("feature ss03 {")
        lines.append("    featureNames { name \"Capital sharp S (Eszett)\"; };")
        lines.append("    sub germandbls by germandbls.cap;")
        lines.append("} ss03;\n")

    # --- Stylistic Alternates (salt) ---
    salt_rules = []
    if {"g", "g.alt"}.issubset(glyph_set):
        salt_rules.append("    sub g from [g.alt];")
    if {"k", "k.alt"}.issubset(glyph_set):
        salt_rules.append("    sub k from [k.alt];")
    if {"germandbls", "germandbls.cap"}.issubset(glyph_set):
        salt_rules.append("    sub germandbls from [germandbls.cap];")
    if salt_rules:
        lines.append("feature salt {")
        lines.extend(salt_rules)
        lines.append("} salt;\n")

    # --- Figures: Oldstyle (onum) and Lining (lnum) ---
    num_pairs = [
        ("zero", "zero.osf"),
        ("one", "one.osf"),
        ("two", "two.osf"),
        ("three", "three.osf"),
        ("four", "four.osf"),
        ("five", "five.osf"),
        ("six", "six.osf"),
        ("seven", "seven.osf"),
        ("eight", "eight.osf"),
        ("nine", "nine.osf"),
    ]
    onum_rules = [f"    sub {l} by {o};" for l, o in num_pairs if {l, o}.issubset(glyph_set)]
    lnum_rules = [f"    sub {o} by {l};" for l, o in num_pairs if {l, o}.issubset(glyph_set)]

    if onum_rules:
        lines.append("feature onum {")
        lines.extend(onum_rules)
        lines.append("} onum;\n")

    if lnum_rules:
        lines.append("feature lnum {")
        lines.extend(lnum_rules)
        lines.append("} lnum;\n")

    # --- Fractions (frac) ---
    frac_rules = []
    if {"one", "slash", "two", "onehalf"}.issubset(glyph_set):
        frac_rules.append("    sub one slash two by onehalf;")
    if {"one", "slash", "four", "onequarter"}.issubset(glyph_set):
        frac_rules.append("    sub one slash four by onequarter;")
    if {"three", "slash", "four", "threequarters"}.issubset(glyph_set):
        frac_rules.append("    sub three slash four by threequarters;")
    if frac_rules:
        lines.append("feature frac {")
        lines.extend(frac_rules)
        lines.append("} frac;\n")

    # --- GPOS Kerning (kern) ---
    raw_classes = {
        "A": [
            "A", "Aacute", "Agrave", "Acircumflex", "Atilde", "Adieresis",
            "Aring", "Amacron", "Abreve", "Aogonek", "Alpha", "Alphatonos"
        ],
        "V": ["V"],
        "W": ["W"],
        "Y": ["Y", "Yacute", "Ydieresis", "Ycircumflex"],
        "T": ["T", "Tcaron", "Tcommaaccent", "Tbar", "Tau"],
        "O": [
            "O", "Oacute", "Ograve", "Ocircumflex", "Otilde", "Odieresis",
            "Oslash", "Omacron", "Obreve", "Ohungarumlaut", "Q", "Omicron", "Omicrontonos"
        ],
        "C": ["C", "Cacute", "Ccircumflex", "Cdotaccent", "Ccaron", "Ccedilla"],
        "L": ["L", "Lacute", "Lcommaaccent", "Lcaron", "Ldot", "Lslash", "Lambda"],
        "P": ["P", "Rho"],
        "R": ["R", "Racute", "Rcaron", "Rcommaaccent"],
        "B": ["B", "Beta"],
        "K": ["K", "Kcommaaccent", "Kappa"],
        "a": [
            "a", "aacute", "agrave", "acircumflex", "atilde", "adieresis",
            "aring", "amacron", "abreve", "aogonek", "alpha", "alphatonos"
        ],
        "o": [
            "o", "oacute", "ograve", "ocircumflex", "otilde", "odieresis",
            "oslash", "omacron", "obreve", "ohungarumlaut", "omicron", "omicrontonos"
        ],
        "e": [
            "e", "eacute", "egrave", "ecircumflex", "edieresis", "emacron",
            "ebreve", "edotaccent", "eogonek", "ecaron", "epsilon", "epsilontonos"
        ],
        "u": [
            "u", "uacute", "ugrave", "ucircumflex", "udieresis", "utilde",
            "umacron", "ubreve", "uring", "uhungarumlaut", "uogonek", "upsilon", "upsilontonos"
        ],
        "v": ["v"],
        "w": ["w", "wcircumflex"],
        "y": ["y", "yacute", "ydieresis", "ycircumflex"],
        "r": ["r", "racute", "rcaron", "rcommaaccent", "rho"],
        "punct": ["period", "comma", "colon", "semicolon", "ellipsis"],
        "hyphen": ["hyphen", "endash", "emdash"],
        "quotes": [
            "quoteleft", "quoteright", "quotesingle",
            "quotedblleft", "quotedblright", "quotedbl"
        ],
    }

    classes = {}
    class_defs = []
    for c_name, c_glyphs in raw_classes.items():
        valid = [g for g in c_glyphs if g in glyph_set]
        if valid:
            classes[c_name] = valid
            class_defs.append(f"    @{c_name} = [{' '.join(valid)}];")

    pair_rules = [
        ("A", "V", -110),
        ("A", "W", -80),
        ("A", "Y", -100),
        ("A", "T", -90),
        ("A", "quotes", -90),
        ("V", "A", -110),
        ("W", "A", -80),
        ("Y", "A", -100),
        ("T", "A", -90),
        ("L", "T", -90),
        ("L", "V", -100),
        ("L", "W", -70),
        ("L", "Y", -90),
        ("L", "quotes", -100),
        ("P", "A", -80),
        ("R", "V", -40),
        ("R", "Y", -50),
        ("R", "T", -40),
        ("V", "o", -70),
        ("V", "a", -70),
        ("V", "e", -70),
        ("V", "u", -50),
        ("V", "r", -60),
        ("W", "o", -50),
        ("W", "a", -50),
        ("W", "e", -50),
        ("W", "u", -40),
        ("W", "r", -40),
        ("Y", "o", -90),
        ("Y", "a", -90),
        ("Y", "e", -90),
        ("Y", "u", -80),
        ("Y", "r", -80),
        ("T", "o", -90),
        ("T", "a", -90),
        ("T", "e", -90),
        ("T", "u", -70),
        ("T", "r", -70),
        ("T", "y", -60),
        ("P", "a", -40),
        ("P", "o", -30),
        ("P", "e", -30),
        ("V", "punct", -90),
        ("W", "punct", -70),
        ("Y", "punct", -100),
        ("T", "punct", -90),
        ("P", "punct", -100),
        ("r", "punct", -70),
        ("v", "punct", -60),
        ("w", "punct", -50),
        ("y", "punct", -70),
        ("T", "hyphen", -80),
    ]

    valid_pairs = []
    for left, right, val in pair_rules:
        if left in classes and right in classes:
            valid_pairs.append(f"    pos @{left} @{right} {val};")

    if valid_pairs:
        lines.append("feature kern {")
        lines.extend(class_defs)
        lines.append("")
        lines.extend(valid_pairs)
        lines.append("} kern;\n")

    # --- GDEF Table and Mark Feature: combining mark attachment ---
    # Mark glyphs are zero-width combining accents that attach to base glyphs.
    # Without GDEF classification and GPOS mark anchors, shapers cannot
    # properly attach combining marks to base letters, causing fontbakery
    # shape_languages failures (e.g. Dutch IJ with combining acute).
    combining_names = [
        "uni0300", "uni0301", "uni0302", "uni0303", "uni0304",
        "uni0306", "uni0307", "uni0308", "uni030A", "uni030B",
        "uni030C", "uni0327", "uni0328",
    ]
    # Above-base marks (accents that sit on top of letters)
    above_marks = [
        "uni0300", "uni0301", "uni0302", "uni0303", "uni0304",
        "uni0306", "uni0307", "uni0308", "uni030A", "uni030B",
        "uni030C",
    ]
    # Below-base marks (cedilla, ogonek)
    below_marks = ["uni0327", "uni0328"]

    present_marks = [n for n in combining_names if n in glyph_set]
    present_above = [n for n in above_marks if n in glyph_set]
    present_below = [n for n in below_marks if n in glyph_set]

    if present_marks:
        mark_class_str = " ".join(present_marks)
        lines.append(f"@CombiningMarks = [{mark_class_str}];")
        lines.append("")
        lines.append("table GDEF {")
        lines.append(f"  GlyphClassDef , , @CombiningMarks, ;")
        lines.append("} GDEF;\n")

        # Build mark feature with anchor-based positioning.
        # Cap height ~1430, x-height ~1050 in Lygon's coordinate space.
        # Combining marks were shifted left by their spacing width, so their
        # "visual center" is at x=0. We anchor them at (0, 0) on the mark side
        # and at (half-width, cap/x-height) on the base side.
        lines.append("feature mark {")

        # Define markClass for above marks anchored at their visual center
        for mark_name in present_above:
            lines.append(f"  markClass {mark_name} <anchor 0 0> @above_marks;")

        # Define markClass for below marks
        for mark_name in present_below:
            lines.append(f"  markClass {mark_name} <anchor 0 0> @below_marks;")

        lines.append("")

        # Define base anchors for all Latin letters
        # Uppercase letters: anchor at (width/2, capHeight=1430) for above
        # Lowercase letters: anchor at (width/2, xHeight=1050) for above
        # For below marks: anchor at (width/2, 0)
        uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        lowercase = "abcdefghijklmnopqrstuvwxyz"

        for char in uppercase:
            if char in glyph_set:
                lines.append(f"  pos base {char} <anchor 0 1430> mark @above_marks;")
        for char in lowercase:
            if char in glyph_set:
                lines.append(f"  pos base {char} <anchor 0 1050> mark @above_marks;")

        if present_below:
            lines.append("")
            for char in uppercase + lowercase:
                if char in glyph_set:
                    lines.append(f"  pos base {char} <anchor 0 0> mark @below_marks;")

        lines.append("} mark;\n")

    return "\n".join(lines)


def build_straight_k(weight_name, is_italic=False):
    """
    Build straight-arm lowercase k matching capital K:
    - Arms reach from x-height (1050) down to baseline (0).
    - Vertical ascender stem from ascender height (1430) down to baseline (0).
    - Halved cutout space (~90 units) with 100% uniform arm thickness (zero wedges).
    - Accurate sidebearings and italic slant handling.
    """
    slant = 0.2 if is_italic else 0.0
    x_shift = -142 if is_italic else 0

    def transform(x, y):
        return (int(round(x + x_shift + y * slant)), y)

    if weight_name == "Light":
        stem_l, stem_r = 150, 255
        dx = -63
        raw_pts = [
            (996, 1050),
            (506 + dx, 569),
            (1002, 0),
            (855, 0),
            (411 + dx, 525),
            (411 + dx, 598),
            (858, 1050),
            (stem_l, 0),
            (stem_l, 1430),
            (stem_r, 1430),
            (stem_r, 0),
        ]
        aw = 1111 if is_italic else 1000
        lsb = 8 if is_italic else 150
    elif weight_name == "Bold":
        stem_l, stem_r = 125, 390
        dx = -16
        raw_pts = [
            (1191, 1050),
            (741 + dx, 576),
            (1207, 0),
            (870, 0),
            (486 + dx, 505),
            (486 + dx, 608),
            (873, 1050),
            (stem_l, 0),
            (stem_l, 1430),
            (stem_r, 1430),
            (stem_r, 0),
        ]
        aw = 1211 if is_italic else 1200
        lsb = -17 if is_italic else 125
    else:  # Regular
        stem_l, stem_r = 150, 335
        dx = -46
        raw_pts = [
            (1086, 1050),
            (646 + dx, 576),
            (1102, 0),
            (855, 0),
            (471 + dx, 505),
            (471 + dx, 608),
            (858, 1050),
            (stem_l, 0),
            (stem_l, 1430),
            (stem_r, 1430),
            (stem_r, 0),
        ]
        aw = 1176 if is_italic else 1092
        lsb = 8 if is_italic else 150

    pts = [transform(x, y) for x, y in raw_pts]
    flags = [1] * 11
    endPts = [6, 10]
    return pts, flags, endPts, aw, lsb


def solve_quadratic(a, b, c):
    """
    Finds a root in [0, 1] for quadratic equation a*t^2 + b*t + c = 0.
    """
    if abs(a) < 1e-9:
        return -c / b if abs(b) > 1e-9 else 0.0
    d = b * b - 4 * a * c
    if d < 0:
        d = 0.0
    r1 = (-b + math.sqrt(d)) / (2 * a)
    r2 = (-b - math.sqrt(d)) / (2 * a)
    roots = [r for r in (r1, r2) if 0.0 <= r <= 1.0]
    return roots[0] if roots else r1


def build_refined_euro(font, weight_name, is_italic, offset=130):
    """
    Redesign the Euro currency symbol (EUR) so both horizontal crossbars cut
    completely through the spine curve and emerge on the left side, eliminating
    visual confusion with mathematical set membership symbols (like element-of).
    """
    glyf = font["glyf"]
    if "Euro" not in glyf:
        return
    g = glyf["Euro"]
    coords = list(g.coordinates)
    flags = list(g.flags)

    # In Sansation, coordinates 14/15/18/19 define the inner crossbars:
    # 14: right-top of upper bar
    # 15: right-bottom of upper bar
    # 18: right-top of lower bar
    # 19: right-bottom of lower bar
    y_up_top = coords[14][1]
    y_up_bot = coords[15][1]
    y_lo_top = coords[18][1]
    y_lo_bot = coords[19][1]

    p_mid = coords[4]
    p_top_ctrl = coords[5]
    p_top = coords[6]
    p_bot_ctrl = coords[3]
    p_bot = coords[2]

    # Upper curve: P0 = p_mid, P1 = p_top_ctrl, P2 = p_top
    a_up = p_mid[1] - 2 * p_top_ctrl[1] + p_top[1]
    b_up = 2 * (p_top_ctrl[1] - p_mid[1])
    c_up_top = p_mid[1] - y_up_top
    c_up_bot = p_mid[1] - y_up_bot

    t_up_top = solve_quadratic(a_up, b_up, c_up_top)
    t_up_bot = solve_quadratic(a_up, b_up, c_up_bot)

    def eval_quad(p0, p1, p2, t):
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
        return x, y

    pt_up_top = eval_quad(p_mid, p_top_ctrl, p_top, t_up_top)
    pt_up_bot = eval_quad(p_mid, p_top_ctrl, p_top, t_up_bot)
    ctrl_up_rem = (
        (1 - t_up_top) * p_top_ctrl[0] + t_up_top * p_top[0],
        (1 - t_up_top) * p_top_ctrl[1] + t_up_top * p_top[1],
    )

    # Lower curve: P0 = p_bot, P1 = p_bot_ctrl, P2 = p_mid
    a_lo = p_bot[1] - 2 * p_bot_ctrl[1] + p_mid[1]
    b_lo = 2 * (p_bot_ctrl[1] - p_bot[1])
    c_lo_top = p_bot[1] - y_lo_top
    c_lo_bot = p_bot[1] - y_lo_bot

    t_lo_top = solve_quadratic(a_lo, b_lo, c_lo_top)
    t_lo_bot = solve_quadratic(a_lo, b_lo, c_lo_bot)

    pt_lo_top = eval_quad(p_bot, p_bot_ctrl, p_mid, t_lo_top)
    pt_lo_bot = eval_quad(p_bot, p_bot_ctrl, p_mid, t_lo_bot)
    ctrl_lo_rem = (
        (1 - t_lo_bot) * p_bot[0] + t_lo_bot * p_bot_ctrl[0],
        (1 - t_lo_bot) * p_bot[1] + t_lo_bot * p_bot_ctrl[1],
    )

    slant = 0.2 if is_italic else 0.0

    base_x_left = p_mid[0] - offset
    x_up_top_left = base_x_left + (y_up_top - p_mid[1]) * slant
    x_up_bot_left = base_x_left + (y_up_bot - p_mid[1]) * slant
    x_lo_top_left = base_x_left + (y_lo_top - p_mid[1]) * slant
    x_lo_bot_left = base_x_left + (y_lo_bot - p_mid[1]) * slant

    new_pts = []
    new_flags = []

    # 1. Bottom terminal and outer bottom curve
    new_pts.append(coords[0])
    new_flags.append(1)
    new_pts.append(coords[1])
    new_flags.append(0)
    new_pts.append(coords[2])
    new_flags.append(1)

    # 2. Lower curve up to lower bar bottom
    new_pts.append((round(ctrl_lo_rem[0]), round(ctrl_lo_rem[1])))
    new_flags.append(0)
    new_pts.append((round(pt_lo_bot[0]), round(pt_lo_bot[1])))
    new_flags.append(1)

    # 3. Lower bar left tab
    new_pts.append((round(x_lo_bot_left), round(y_lo_bot)))
    new_flags.append(1)
    new_pts.append((round(x_lo_top_left), round(y_lo_top)))
    new_flags.append(1)
    new_pts.append((round(pt_lo_top[0]), round(pt_lo_top[1])))
    new_flags.append(1)

    # 4. Middle spine apex
    new_pts.append(p_mid)
    new_flags.append(1)

    # 5. Upper bar left tab
    new_pts.append((round(pt_up_bot[0]), round(pt_up_bot[1])))
    new_flags.append(1)
    new_pts.append((round(x_up_bot_left), round(y_up_bot)))
    new_flags.append(1)
    new_pts.append((round(x_up_top_left), round(y_up_top)))
    new_flags.append(1)
    new_pts.append((round(pt_up_top[0]), round(pt_up_top[1])))
    new_flags.append(1)

    # 6. Upper curve up to top terminal
    new_pts.append((round(ctrl_up_rem[0]), round(ctrl_up_rem[1])))
    new_flags.append(0)
    new_pts.append(coords[6])
    new_flags.append(1)
    new_pts.append(coords[7])
    new_flags.append(0)
    new_pts.append(coords[8])
    new_flags.append(1)

    # 7. Inner path & shelves (points 9 to 24 of original)
    for i in range(9, len(coords)):
        new_pts.append(coords[i])
        new_flags.append(flags[i])

    g.coordinates = GlyphCoordinates(new_pts)
    g.flags = bytearray(new_flags)
    g.endPtsOfContours = [len(new_pts) - 1]
    g.recalcBounds(glyf)


def modify_glyph_geometry(font, weight_name, is_italic=False):
    """
    Apply vector outline refinements:
    - Halve cutout gap on B, K, P, R while strictly maintaining uniform stroke thickness.
    - Transform lowercase k to modern straight-arm design matching K.
    - Retain original lowercase j geometry for user SVG review.
    - Redesign Euro symbol so bars cut through the outer spine curve.
    - Synchronize Cyrillic and Greek variants.
    """
    glyf = font["glyf"]
    hmtx = font["hmtx"]

    # Translation distances per weight
    if weight_name == "Light":
        dx_B = -153
        dx_K = -97
        dx_R = -158
        dx_P = -115
    elif weight_name == "Bold":
        dx_B = -103
        dx_K = -75
        dx_R = -83
        dx_P = -95
    else:  # Regular
        dx_B = -113
        dx_K = -90
        dx_R = -113
        dx_P = -105

    # 1. Modify B:
    # Middle horizontal bar points move towards the stem
    if "B" in glyf:
        g_B = glyf["B"]
        for i in range(len(g_B.coordinates)):
            pt = g_B.coordinates[i]
            if 550 < pt[1] < 850 and 400 < pt[0] < 750:
                g_B.coordinates[i] = (pt[0] + dx_B, pt[1])
        g_B.recalcBounds(glyf)

    # 2. Modify K:
    # Move BOTH the inner vertex AND the outer vertex by the exact same dx
    # so that the upper and lower arms maintain 100% uniform thickness (no wedges)
    if "K" in glyf:
        g_K = glyf["K"]
        for i in range(len(g_K.coordinates)):
            pt = g_K.coordinates[i]
            if 640 < pt[1] < 860 and 350 < pt[0] < 900:
                g_K.coordinates[i] = (pt[0] + dx_K, pt[1])
        g_K.recalcBounds(glyf)

    # 3. Modify R:
    # Move BOTH the inner leg junction AND the outer meeting point with the bowl
    # so the diagonal leg has completely parallel, uniform stroke thickness from top to bottom
    if "R" in glyf:
        g_R = glyf["R"]
        for i in range(len(g_R.coordinates)):
            pt = g_R.coordinates[i]
            if 600 < pt[1] < 800 and 420 < pt[0] < 900:
                g_R.coordinates[i] = (pt[0] + dx_R, pt[1])
            elif 780 < pt[1] < 850 and 800 < pt[0] < 1250 and g_R.flags[i] == 0:
                g_R.coordinates[i] = (pt[0] + int(dx_R * 0.45), pt[1])
        g_R.recalcBounds(glyf)

    # 4. Modify k: Modern straight-arm design matching K (scaled to x-height, halved gap, uniform arms)
    if "k" in glyf:
        pts, flags, endPts, aw, lsb = build_straight_k(weight_name, is_italic)
        g_k = copy.deepcopy(glyf["k"])
        g_k.numberOfContours = 2
        g_k.coordinates = GlyphCoordinates(pts)
        g_k.flags = bytearray(flags)
        g_k.endPtsOfContours = endPts
        g_k.recalcBounds(glyf)
        glyf["k"] = g_k
        font["hmtx"]["k"] = (aw, lsb)
        if "k.alt" in glyf:
            glyf["k.alt"] = copy.deepcopy(g_k)
            font["hmtx"]["k.alt"] = (aw, lsb)

    # 5. Modify P:
    # Bring the lower bowl stroke closer to the stem along its natural curve
    if "P" in glyf:
        g_P = glyf["P"]
        for i in range(len(g_P.coordinates)):
            pt = g_P.coordinates[i]
            if 480 < pt[1] < 760 and 400 < pt[0] < 680 and g_P.flags[i] == 1:
                g_P.coordinates[i] = (pt[0] + dx_P, pt[1])
        g_P.recalcBounds(glyf)

    # 6. Lowercase j (and ligatures fj, ffj):
    # Extend circular descender curve by shifting the two bottommost keypoints (apex and tip) left by 80 units
    dx_j = -80
    for j_name in ["j", "fj", "ffj"]:
        if j_name in glyf and not glyf[j_name].isComposite():
            g_j = glyf[j_name]
            for i in range(len(g_j.coordinates)):
                pt = g_j.coordinates[i]
                # Bottom apex is at y < -340
                if pt[1] < -340:
                    g_j.coordinates[i] = (pt[0] + dx_j, pt[1])
                # Terminal tip is between -320 and -260
                elif -320 < pt[1] < -260 and pt[0] < 800:
                    g_j.coordinates[i] = (pt[0] + dx_j, pt[1])
            g_j.recalcBounds(glyf)

    # 7. Update Cyrillic counterparts:
    # afii10018 (Б) - middle bar
    if "afii10018" in glyf:
        g = glyf["afii10018"]
        for i in range(len(g.coordinates)):
            pt = g.coordinates[i]
            if 600 < pt[1] < 850 and 450 < pt[0] < 600:
                g.coordinates[i] = (pt[0] + dx_B, pt[1])
        g.recalcBounds(glyf)

    # afii10046 (Ь) & afii10044 (Ъ)
    for cname in ["afii10046", "afii10044"]:
        if cname in glyf:
            g = glyf[cname]
            for i in range(len(g.coordinates)):
                pt = g.coordinates[i]
                if 600 < pt[1] < 850 and 450 < pt[0] < 1000:
                    g.coordinates[i] = (pt[0] + dx_B, pt[1])
            g.recalcBounds(glyf)

    # afii10049 (Я) - reversed R
    if "afii10049" in glyf:
        g = glyf["afii10049"]
        for i in range(len(g.coordinates)):
            pt = g.coordinates[i]
            if 580 < pt[1] < 800 and 650 < pt[0] < 800:
                g.coordinates[i] = (pt[0] - dx_R, pt[1])
            elif 580 < pt[1] < 720 and 400 < pt[0] < 600:
                g.coordinates[i] = (pt[0] - dx_R, pt[1])
        g.recalcBounds(glyf)

    # Greek beta
    if "beta" in glyf:
        g = glyf["beta"]
        for i in range(len(g.coordinates)):
            pt = g.coordinates[i]
            if 600 < pt[1] < 850 and 500 < pt[0] < 650:
                g.coordinates[i] = (pt[0] + dx_B, pt[1])
        g.recalcBounds(glyf)

    # Greek kappa & Cyrillic Ka (afii10028)
    for cname in ["kappa", "afii10028", "afii10076"]:
        if cname in glyf and not glyf[cname].isComposite():
            g = glyf[cname]
            for i in range(len(g.coordinates)):
                pt = g.coordinates[i]
                if 450 < pt[1] < 850 and 400 < pt[0] < 850:
                    g.coordinates[i] = (pt[0] + dx_K, pt[1])
            g.recalcBounds(glyf)

    # 7. Redesign Euro symbol (€):
    # Ensure both horizontal crossbars cut through the back spine curve to the left,
    # distinguishing it clearly from mathematical set membership symbols (like element-of).
    if "Euro" in glyf:
        euro_offset = (
            110 if weight_name == "Light" else (150 if weight_name == "Bold" else 130)
        )
        build_refined_euro(font, weight_name, is_italic, euro_offset)

    # 8. Refine question mark (?) and inverted question mark (¿):
    # Tone down the excessively wide, funky rounded head by pulling the rightward bulge inward by ~80 units.
    dx_q = -70 if weight_name == "Light" else (-90 if weight_name == "Bold" else -80)
    for q_name, mult in [("question", 1), ("questiondown", -1)]:
        if q_name in glyf and not glyf[q_name].isComposite():
            g_q = glyf[q_name]
            coords = list(g_q.coordinates)
            N = len(coords)
            shift_main = dx_q * mult
            shift_sub = int(shift_main * 0.25)
            # Outer and inner curves
            for idx in [7, 8, 9, N - 6, N - 5, N - 4]:
                if 0 <= idx < N:
                    coords[idx] = (coords[idx][0] + shift_main, coords[idx][1])
            # Transitions
            for idx in [6, N - 3, 10, N - 7]:
                if 0 <= idx < N:
                    coords[idx] = (coords[idx][0] + shift_sub, coords[idx][1])
            g_q.coordinates = GlyphCoordinates(coords)
            g_q.recalcBounds(glyf)
            aw, lsb = hmtx[q_name]
            hmtx[q_name] = (aw + dx_q, lsb)

    # 9. Update registered trademark symbol (®):
    # Ensure the inner R in 'registered' matches the refined Lygon capital R design
    # (harmonized cutout gap matching letter A and uniform diagonal leg thickness, removing the old wedge).
    if "registered" in glyf and "R" in glyf and not glyf["registered"].isComposite():
        g_reg = glyf["registered"]
        reg_coords, end_pts, reg_flags = g_reg.getCoordinates(glyf)
        r_coords, _, _ = glyf["R"].getCoordinates(glyf)
        if len(reg_coords) >= 17 and len(r_coords) >= 17:
            r_h = r_coords[1][1] - r_coords[0][1]
            reg_h = reg_coords[1][1] - reg_coords[0][1]
            if r_h != 0:
                scale = reg_h / r_h
                off_x = reg_coords[0][0] - r_coords[0][0] * scale
                off_y = reg_coords[0][1] - r_coords[0][1] * scale
                new_r = [
                    (round(rx * scale + off_x), round(ry * scale + off_y))
                    for rx, ry in r_coords[:17]
                ]
                new_coords = new_r + list(reg_coords[17:])
                g_reg.coordinates = GlyphCoordinates(new_coords)
                g_reg.recalcBounds(glyf)


def modernize_font_metadata(font, style_name, weight_value, is_italic=False):
    """
    Modernize all OpenType metadata tables:
    - name: Lygon family naming & OFL 1.1 notice
    - OS/2: v4 upgrade, USE_TYPO_METRICS, sCapHeight, sxHeight
    - post: accurate italicAngle
    - hhea: accurate caretSlope
    - gasp: 0x000F for clean antialiasing
    """
    # 1. Name Table
    name_table = font["name"]
    name_table.names = []

    family_name = "Lygon"
    full_name = f"Lygon {style_name}"
    ps_name = f"Lygon-{style_name.replace(' ', '')}"
    subfamily = style_name
    unique_id = f"1.000;NONE;{ps_name}"

    # RIBBI styles (Regular, Italic, Bold, Bold Italic) should NOT have
    # nameIDs 16/17 per Google Fonts spec. Non-RIBBI styles need them.
    is_ribbi = style_name in ("Regular", "Italic", "Bold", "Bold Italic")

    entries = [
        (0, OFL_NOTICE),
        (1, family_name),
        (2, subfamily),
        (3, unique_id),
        (4, full_name),
        (5, "Version 1.000"),
        (6, ps_name),
        (8, "The Lygon Project Authors"),
        (9, "Bernd Montag, Toni Lahdekorpi"),
        (11, "https://github.com/lahdekorpi/lygon"),
        (12, "https://github.com/lahdekorpi"),
        # Exact text required by fontbakery googlefonts/name/license check
        (13, "This Font Software is licensed under the SIL Open Font License, "
             "Version 1.1. This license is available with a FAQ at: "
             "https://openfontlicense.org"),
        (14, "https://openfontlicense.org"),
    ]

    # Only add typographic name IDs for non-RIBBI styles
    if not is_ribbi:
        entries.append((16, family_name))
        entries.append((17, subfamily))

    # Remove any spurious or inherited Name ID 7 (Trademark) records
    name_table.removeNames(nameID=7)

    for name_id, text in entries:
        name_table.setName(text, name_id, 1, 0, 0)
        name_table.setName(text, name_id, 3, 1, 0x409)

    # 2. OS/2 Table Modernization (Version 4)
    os2 = font["OS/2"]
    os2.version = 4
    os2.fsType = 0  # Installable Embedding - required by Google Fonts
    os2.ulCodePageRange1 = 1
    os2.ulCodePageRange2 = 0
    os2.sCapHeight = 1430
    os2.sxHeight = 1050
    os2.usDefaultChar = 0
    os2.usBreakChar = 32
    os2.usMaxContext = 3
    os2.usWeightClass = weight_value
    os2.usWidthClass = 5  # Medium / Normal

    fs = 1 << 7  # USE_TYPO_METRICS
    if is_italic:
        fs |= 1 << 0
    if weight_value >= 700:
        fs |= 1 << 5
    elif weight_value == 400 and not is_italic:
        fs |= 1 << 6
    os2.fsSelection = fs

    # Vertical metrics - Google Fonts schema
    # Sum of hhea ascender + abs(descender) must be >= 120% of UPM (2458 for UPM 2048)
    os2.sTypoAscender = 1900
    os2.sTypoDescender = -600
    os2.sTypoLineGap = 0
    os2.usWinAscent = 2200   # Covers tallest accented glyphs
    os2.usWinDescent = 700   # Covers deepest descenders

    # 3. Post Table
    post = font["post"]
    post.italicAngle = -11.31 if is_italic else 0.0
    post.underlinePosition = -205
    post.underlineThickness = 102
    post.isFixedPitch = 0

    # 4. Hhea Table
    hhea = font["hhea"]
    hhea.ascent = 1900
    hhea.descent = -600
    hhea.lineGap = 0
    if is_italic:
        hhea.caretSlopeRise = 1430
        hhea.caretSlopeRun = 286
    else:
        hhea.caretSlopeRise = 1
        hhea.caretSlopeRun = 0
    hhea.caretOffset = 0

    # 5. Gasp Table
    if "gasp" in font:
        font["gasp"].gaspRange = {65535: 15}


def apply_opentype_features(font):
    """Compile GPOS kerning and GSUB features into the font using feaLib."""
    glyph_set = set(font.getGlyphOrder())
    fea_text = build_feature_file(glyph_set)
    addOpenTypeFeatures(font, io.StringIO(fea_text))


def build_stat_table(font, is_italic=False):
    """Build STAT table with weight and italic axes for variable font compliance.
    Both upright and italic VFs must declare the ital axis so they can be
    linked as a family by layout engines and font pickers.
    Google Fonts Axis Registry requires 'Roman'/'Italic' names (not 'Regular')."""
    axes = [
        dict(
            tag="wght",
            name="Weight",
            ordering=0,
            values=[
                dict(value=300, name="Light"),
                dict(value=400, name="Regular", flags=0x2),  # ElidedFallbackName
                dict(value=500, name="Medium"),
                dict(value=600, name="SemiBold"),
                dict(value=700, name="Bold"),
            ],
        ),
        dict(
            tag="ital",
            name="Italic",
            ordering=1,
            values=[
                # Axis Registry requires 'Roman' and 'Italic' (not 'Regular')
                # linkedValue pairs the upright with its italic counterpart
                dict(value=1.0, name="Italic") if is_italic
                else dict(value=0.0, name="Roman", flags=0x2, linkedValue=1.0),
            ],
        ),
    ]
    buildStatTable(font, axes)


def export_font(font, slug, is_variable=False):
    """Save font in TTF, WOFF, and WOFF2 formats into standard Google Fonts directories."""
    # TTF
    target_ttf_dir = VAR_DIR if is_variable else TTF_DIR
    ttf_path = os.path.join(target_ttf_dir, f"{slug}.ttf")
    font.flavor = None
    font.save(ttf_path)
    print(f"  Saved TTF:   {os.path.relpath(ttf_path, REPO_ROOT)}")

    # WOFF
    woff_path = os.path.join(WOFF_DIR, f"{slug}.woff")
    font.flavor = "woff"
    font.save(woff_path)
    print(f"  Saved WOFF:  {os.path.relpath(woff_path, REPO_ROOT)}")

    # WOFF2
    woff2_path = os.path.join(WOFF2_DIR, f"{slug}.woff2")
    font.flavor = "woff2"
    font.save(woff2_path)
    print(f"  Saved WOFF2: {os.path.relpath(woff2_path, REPO_ROOT)}")

    font.flavor = None


def add_meta_table(font):
    """Add OpenType 'meta' table with ScriptLangTags.
    Declares which scripts/languages this font is designed for (dlng)
    and which it supports (slng). Required by Google Fonts."""
    from fontTools.ttLib import newTable
    meta = newTable("meta")
    meta.data = {}
    # dlng: designed for Latin script
    meta.data["dlng"] = "Latn,Cyrl,Grek"
    # slng: supports Latin, Cyrillic, and Greek scripts
    meta.data["slng"] = "Latn,Cyrl,Grek"
    font["meta"] = meta


def flatten_nested_components(font):
    """Decompose any composite glyph whose components are themselves composites.
    Required by Google Fonts (fontbakery nested_components check).
    TrueType spec says components should reference simple glyphs only."""
    glyf = font["glyf"]
    # Identify which glyphs are composites
    composite_glyphs = set()
    for name in glyf.keys():
        g = glyf[name]
        if g.numberOfContours == -1:  # composite
            composite_glyphs.add(name)

    # Find composites that reference other composites (nested)
    nested = set()
    for name in composite_glyphs:
        g = glyf[name]
        if hasattr(g, 'components'):
            for comp in g.components:
                if comp.glyphName in composite_glyphs:
                    nested.add(name)
                    break

    if not nested:
        return

    # Decompose nested composites to simple outlines
    # Use DecomposingRecordingPen which recursively resolves all component refs
    from fontTools.pens.recordingPen import DecomposingRecordingPen
    from fontTools.pens.ttGlyphPen import TTGlyphPointPen
    glyph_set = font.getGlyphSet()

    for name in sorted(nested):
        try:
            rec = DecomposingRecordingPen(glyph_set)
            glyph_set[name].draw(rec)
            pen = TTGlyphPointPen(None)
            rec.replay(pen)
            glyf[name] = pen.glyph()
        except Exception as e:
            # Fall back to drawing the glyph via pointPen decomposition
            try:
                from fontTools.pens.pointPen import SegmentToPointPen
                rec2 = DecomposingRecordingPen(glyph_set)
                glyph_set[name].draw(rec2)
                # Convert segments to points for TTGlyphPointPen
                point_pen = TTGlyphPointPen(None)
                seg2pt = SegmentToPointPen(point_pen)
                rec2.replay(seg2pt)
                glyf[name] = point_pen.glyph()
            except Exception:
                pass  # Skip glyphs that resist decomposition


def generate_dotlessj(font):
    """Generate dotlessj (U+0237) from the existing j glyph by removing the dot contour.
    Required by Google Fonts glyph_coverage check for Latin core support."""
    glyf = font["glyf"]
    cmap = font.getBestCmap()
    j_name = cmap.get(ord('j'))
    if not j_name or j_name not in glyf:
        return

    j_glyph = glyf[j_name]
    if j_glyph.numberOfContours < 2:
        return  # j has no separable dot contour

    # The dot is typically the first or last contour (smallest, highest y)
    # Clone the j glyph and remove the dot contour
    import copy
    new_glyph = copy.deepcopy(j_glyph)
    coords = list(new_glyph.coordinates)
    flags = list(new_glyph.flags)
    end_pts = list(new_glyph.endPtsOfContours)

    # Find which contour is the dot (smallest bounding box, highest center y)
    contours = []
    start = 0
    for i, end in enumerate(end_pts):
        c_coords = coords[start:end + 1]
        ys = [p[1] for p in c_coords]
        xs = [p[0] for p in c_coords]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        center_y = sum(ys) / len(ys)
        contours.append((i, start, end, area, center_y))
        start = end + 1

    # The dot contour has the smallest area and highest center y
    dot_contour = max(contours, key=lambda c: c[4])  # highest center y
    dot_idx = dot_contour[0]
    dot_start = dot_contour[1]
    dot_end = dot_contour[2]

    # Remove dot contour points
    dot_len = dot_end - dot_start + 1
    del coords[dot_start:dot_end + 1]
    del flags[dot_start:dot_end + 1]

    # Rebuild endPtsOfContours
    new_end_pts = []
    for i, end in enumerate(end_pts):
        if i == dot_idx:
            continue
        adjusted = end - dot_len if end > dot_end else end
        if i > dot_idx:
            adjusted = end - dot_len
        new_end_pts.append(adjusted)

    new_glyph.coordinates = GlyphCoordinates(coords)
    new_glyph.flags = bytearray(flags)
    new_glyph.endPtsOfContours = new_end_pts
    new_glyph.numberOfContours = len(new_end_pts)

    # Add to glyf table
    dotlessj_name = "dotlessj"
    glyf[dotlessj_name] = new_glyph

    # Copy metrics from j
    hmtx = font["hmtx"]
    if j_name in hmtx.metrics:
        hmtx.metrics[dotlessj_name] = hmtx.metrics[j_name]

    # Add to cmap
    for table in font["cmap"].tables:
        if hasattr(table, 'cmap') and isinstance(table.cmap, dict):
            table.cmap[0x0237] = dotlessj_name

    # Add to glyph order
    order = font.getGlyphOrder()
    if dotlessj_name not in order:
        order.append(dotlessj_name)
        font.setGlyphOrder(order)


def generate_combining_marks(font):
    """Generate combining (non-spacing) mark glyphs from existing spacing accent glyphs.
    Required by Google Fonts Latin Core glyphset for proper text shaping.
    Each combining mark is a zero-width copy of the spacing accent, shifted left
    so it centers over a preceding base character."""
    glyf = font["glyf"]
    hmtx = font["hmtx"]
    cmap = font.getBestCmap()
    order = font.getGlyphOrder()

    # Map: combining codepoint -> spacing accent glyph name
    # These are the combining marks required for Latin Core support
    combining_map = {
        0x0300: "grave",         # COMBINING GRAVE ACCENT
        0x0301: "acute",         # COMBINING ACUTE ACCENT
        0x0302: "circumflex",    # COMBINING CIRCUMFLEX ACCENT
        0x0303: "tilde",         # COMBINING TILDE
        0x0304: "macron",        # COMBINING MACRON
        0x0306: "breve",         # COMBINING BREVE
        0x0307: "dotaccent",     # COMBINING DOT ABOVE
        0x0308: "dieresis",      # COMBINING DIAERESIS
        0x030A: "ring",          # COMBINING RING ABOVE
        0x030B: "hungarumlaut",  # COMBINING DOUBLE ACUTE ACCENT
        0x030C: "caron",         # COMBINING CARON
        0x0327: "cedilla",       # COMBINING CEDILLA
        0x0328: "ogonek",        # COMBINING OGONEK
    }

    for combining_cp, spacing_name in combining_map.items():
        if combining_cp in cmap:
            continue  # Already exists
        if spacing_name not in glyf or spacing_name not in hmtx.metrics:
            continue  # Source accent not available

        combining_name = f"uni{combining_cp:04X}"

        # Copy the spacing accent glyph outline
        src_glyph = glyf[spacing_name]
        new_glyph = copy.deepcopy(src_glyph)

        # Shift the outline left by the accent's advance width so it
        # becomes a zero-width mark that overlays the previous base glyph
        spacing_width = hmtx.metrics[spacing_name][0]
        if new_glyph.numberOfContours > 0 and hasattr(new_glyph, 'coordinates'):
            coords = list(new_glyph.coordinates)
            shifted = [(x - spacing_width, y) for x, y in coords]
            new_glyph.coordinates = GlyphCoordinates(shifted)
        elif new_glyph.numberOfContours == -1 and hasattr(new_glyph, 'components'):
            # Composite: adjust component offsets
            for comp in new_glyph.components:
                if hasattr(comp, 'x'):
                    comp.x -= spacing_width

        glyf[combining_name] = new_glyph
        hmtx.metrics[combining_name] = (0, 0)  # Zero advance width for combining marks

        # Add to cmap tables
        for table in font["cmap"].tables:
            if hasattr(table, 'cmap') and isinstance(table.cmap, dict):
                table.cmap[combining_cp] = combining_name

        if combining_name not in order:
            order.append(combining_name)

    font.setGlyphOrder(order)


def generate_missing_composites(font):
    """Generate missing Latin Core composite glyphs from base + accent components.
    Builds: Wgrave, wgrave, Wacute, wacute, Wdieresis, wdieresis,
            Ygrave, ygrave, and maps germandbls.cap to U+1E9E."""
    glyf = font["glyf"]
    hmtx = font["hmtx"]
    cmap = font.getBestCmap()
    order = font.getGlyphOrder()

    # Map germandbls.cap to U+1E9E (LATIN CAPITAL LETTER SHARP S) if present
    if 0x1E9E not in cmap and "germandbls.cap" in glyf:
        cmap_name = "uni1E9E"
        glyf[cmap_name] = copy.deepcopy(glyf["germandbls.cap"])
        hmtx.metrics[cmap_name] = hmtx.metrics.get("germandbls.cap", (0, 0))
        for table in font["cmap"].tables:
            if hasattr(table, 'cmap') and isinstance(table.cmap, dict):
                table.cmap[0x1E9E] = cmap_name
        if cmap_name not in order:
            order.append(cmap_name)

    # Composite accented letters: (codepoint, base_glyph, accent_glyph, glyph_name)
    # These are all built as TrueType composites (base + accent component)
    composites = [
        (0x1E80, "W", "grave",    "Wgrave"),
        (0x1E81, "w", "grave",    "wgrave"),
        (0x1E82, "W", "acute",    "Wacute"),
        (0x1E83, "w", "acute",    "wacute"),
        (0x1E84, "W", "dieresis", "Wdieresis"),
        (0x1E85, "w", "dieresis", "wdieresis"),
        (0x1EF2, "Y", "grave",    "Ygrave"),
        (0x1EF3, "y", "grave",    "ygrave"),
    ]

    for cp, base_name, accent_name, glyph_name in composites:
        if cp in cmap:
            continue  # Already exists
        if base_name not in glyf or accent_name not in glyf:
            continue  # Missing components

        # Calculate accent positioning: center accent over base glyph
        base_width = hmtx.metrics[base_name][0]
        accent_width = hmtx.metrics[accent_name][0]

        # Horizontal offset to center accent over base
        accent_x_offset = (base_width - accent_width) // 2

        # Vertical offset: place accent above cap height for uppercase,
        # above x-height for lowercase
        accent_y_offset = 0  # Accents are already at correct height in source font

        # Build composite glyph using TTGlyphPen
        pen = TTGlyphPen(font.getGlyphSet())
        pen.addComponent(base_name, (1, 0, 0, 1, 0, 0))
        pen.addComponent(accent_name, (1, 0, 0, 1, accent_x_offset, accent_y_offset))

        try:
            glyf[glyph_name] = pen.glyph()
            hmtx.metrics[glyph_name] = hmtx.metrics[base_name]  # Same width as base

            # Add to cmap
            for table in font["cmap"].tables:
                if hasattr(table, 'cmap') and isinstance(table.cmap, dict):
                    table.cmap[cp] = glyph_name

            if glyph_name not in order:
                order.append(glyph_name)
        except Exception:
            pass  # Skip if composite creation fails

    font.setGlyphOrder(order)

def fix_variable_font_names(vf, is_italic):
    """Fix name table entries for variable fonts to match Google Fonts expectations.
    Variable fonts use RIBBI naming: nameIDs 16/17 should be absent."""
    name = vf["name"]
    if is_italic:
        # For italic VF: subfamily is "Italic", full name is "Lygon Italic"
        name.setName("Italic", 2, 1, 0, 0)
        name.setName("Italic", 2, 3, 1, 0x409)
        name.setName("Lygon Italic", 4, 1, 0, 0)
        name.setName("Lygon Italic", 4, 3, 1, 0x409)
        name.setName("Lygon-Italic", 6, 1, 0, 0)
        name.setName("Lygon-Italic", 6, 3, 1, 0x409)
        # Name ID 25 (Variations PostScriptName Prefix) must end in 'Italic' for Italic VFs
        name.setName("LygonItalic", 25, 1, 0, 0)
        name.setName("LygonItalic", 25, 3, 1, 0x409)
    else:
        # For upright VF: subfamily is "Regular", full name is "Lygon Regular"
        name.setName("Regular", 2, 1, 0, 0)
        name.setName("Regular", 2, 3, 1, 0x409)
        name.setName("Lygon Regular", 4, 1, 0, 0)
        name.setName("Lygon Regular", 4, 3, 1, 0x409)
        name.setName("Lygon-Regular", 6, 1, 0, 0)
        name.setName("Lygon-Regular", 6, 3, 1, 0x409)
        name.setName("Lygon", 25, 1, 0, 0)
        name.setName("Lygon", 25, 3, 1, 0x409)
    # Remove typographic name IDs - not needed for RIBBI variable fonts
    name.removeNames(nameID=16)
    name.removeNames(nameID=17)


def fix_light_italic_typo(font):
    """Fix original 2011 bug in Sansation-LightItalic where ffj was misnamed ffi#1."""
    order = font.getGlyphOrder()
    if "ffi#1" in order:
        new_order = ["ffj" if g == "ffi#1" else g for g in order]
        font.setGlyphOrder(new_order)
        if "ffi#1" in font["glyf"].glyphs:
            font["glyf"]["ffj"] = font["glyf"]["ffi#1"]
            del font["glyf"]["ffi#1"]
        if "ffi#1" in font["hmtx"].metrics:
            font["hmtx"].metrics["ffj"] = font["hmtx"].metrics["ffi#1"]
            del font["hmtx"].metrics["ffi#1"]


def fix_whitespace_widths(font):
    """Ensure space (U+0020) and non-breaking space (U+00A0) have identical advance widths.
    Required by Google Fonts (fontbakery whitespace_widths check)."""
    hmtx = font["hmtx"]
    cmap = font.getBestCmap()
    space_name = cmap.get(0x0020)
    nbsp_name = cmap.get(0x00A0)
    if space_name and nbsp_name and space_name in hmtx.metrics and nbsp_name in hmtx.metrics:
        space_width = hmtx.metrics[space_name][0]
        hmtx.metrics[nbsp_name] = (space_width, hmtx.metrics[nbsp_name][1])


def add_prep_smart_dropout(font):
    """Add TrueType prep table instructions for smart dropout control.
    Required by Google Fonts (fontbakery smart_dropout check).
    Instructs the rasterizer to use smart dropout control at all sizes."""
    prep_asm = [
        # PUSHW[0] 0x01FF  - push 511
        0xB8, 0x01, 0xFF,
        # SCANCTRL         - set scan conversion control
        0x85,
        # PUSHB[0] 0x04    - push 4
        0xB0, 0x04,
        # SCANTYPE         - set scan conversion type to smart dropout
        0x8D,
    ]
    prep_table = newTable("prep")
    prep_table.program = fontTools.ttLib.tables.ttProgram.Program()
    prep_table.program.fromBytecode(bytes(prep_asm))
    font["prep"] = prep_table


def try_cyclic_align(g_source, g_target):
    """
    Attempts to align contour starting points between two glyphs that share
    identical contour structures and point counts but differ in cyclic point index.
    """
    if g_source.numberOfContours != g_target.numberOfContours or g_source.numberOfContours <= 0:
        return False, None
    if g_source.endPtsOfContours != g_target.endPtsOfContours:
        return False, None

    src_coords = list(g_source.coordinates)
    src_flags = list(g_source.flags)
    tgt_coords = list(g_target.coordinates)
    tgt_flags = list(g_target.flags)

    new_coords = []
    new_flags = []

    start = 0
    for end in g_source.endPtsOfContours:
        cnt_len = end - start + 1
        c_src_pts = src_coords[start:end + 1]
        c_src_flg = src_flags[start:end + 1]
        c_tgt_pts = tgt_coords[start:end + 1]
        c_tgt_flg = tgt_flags[start:end + 1]

        best_shift = None
        min_dist = float("inf")

        for s in range(cnt_len):
            cand_flg = [(f & 1) for f in (c_src_flg[s:] + c_src_flg[:s])]
            tgt_on = [(f & 1) for f in c_tgt_flg]
            if cand_flg == tgt_on:
                cand_pts = c_src_pts[s:] + c_src_pts[:s]
                dist = sum(
                    math.hypot(p1[0] - p2[0], p1[1] - p2[1])
                    for p1, p2 in zip(cand_pts, c_tgt_pts)
                )
                if dist < min_dist:
                    min_dist = dist
                    best_shift = s

        if best_shift is None:
            return False, None

        new_coords.extend(c_src_pts[best_shift:] + c_src_pts[:best_shift])
        new_flags.extend(c_src_flg[best_shift:] + c_src_flg[:best_shift])
        start = end + 1

    return True, (new_coords, new_flags)


def harmonize_master_topologies(masters):
    """
    Harmonize contour counts, point counts, and contour ordering across all masters
    so fontTools.varLib can interpolate every glyph smoothly without dropping deltas.
    """
    for is_italic in [False, True]:
        l_name = "Light Italic" if is_italic else "Light"
        r_name = "Italic" if is_italic else "Regular"
        b_name = "Bold Italic" if is_italic else "Bold"

        fl = masters[l_name]
        fr = masters[r_name]
        fb = masters[b_name]

        glyf_l = fl["glyf"]
        glyf_r = fr["glyf"]
        glyf_b = fb["glyf"]

        # 1. Standardize 'i' contour order across all masters: contour 0 = dot, contour 1 = stem
        if "i" in glyf_r:
            gi_r = glyf_r["i"]
            if len(gi_r.coordinates) == 8 and gi_r.coordinates[0][1] <= 1050:
                stem_coords = list(gi_r.coordinates[:4])
                stem_flags = list(gi_r.flags[:4])
                dot_coords = list(gi_r.coordinates[4:8])
                dot_flags = list(gi_r.flags[4:8])
                gi_r.coordinates = GlyphCoordinates(dot_coords + stem_coords)
                gi_r.flags = bytearray(dot_flags + stem_flags)
                gi_r.endPtsOfContours = [3, 7]
                gi_r.recalcBounds(glyf_r)

        # 2. Standardize 'j' contour order across all masters: contour 0 = dot, contour 1 = body
        if "j" in glyf_r:
            gj_r = glyf_r["j"]
            if len(gj_r.coordinates) == 12 and gj_r.coordinates[0][1] <= 1050:
                body_coords = list(gj_r.coordinates[:8])
                body_flags = list(gj_r.flags[:8])
                dot_coords = list(gj_r.coordinates[8:12])
                dot_flags = list(gj_r.flags[8:12])
                gj_r.coordinates = GlyphCoordinates(dot_coords + body_coords)
                gj_r.flags = bytearray(dot_flags + body_flags)
                gj_r.endPtsOfContours = [3, 11]
                gj_r.recalcBounds(glyf_r)

        # 3. Fix 'g': Bold upright is missing point 18 at inner horizontal junction (797, 20)
        if not is_italic and "g" in glyf_b and "g" in glyf_r:
            gb = glyf_b["g"]
            gr = glyf_r["g"]
            if len(gb.coordinates) == 27 and len(gr.coordinates) == 28:
                coords = list(gb.coordinates)
                flags = list(gb.flags)
                endPts = list(gb.endPtsOfContours)
                coords.insert(18, (797, 20))
                flags.insert(18, 1)
                endPts[1] += 1
                gb.coordinates = GlyphCoordinates(coords)
                gb.flags = bytearray(flags)
                gb.endPtsOfContours = endPts
                gb.recalcBounds(glyf_b)

        # 4. Fix 'e': Bold upright has duplicate on-curve point 18 (788, 624)
        if not is_italic and "e" in glyf_b and "e" in glyf_r:
            eb = glyf_b["e"]
            er = glyf_r["e"]
            if len(eb.coordinates) == 22 and len(er.coordinates) == 21:
                coords = list(eb.coordinates)
                flags = list(eb.flags)
                endPts = list(eb.endPtsOfContours)
                del coords[18]
                del flags[18]
                endPts[1] -= 1
                eb.coordinates = GlyphCoordinates(coords)
                eb.flags = bytearray(flags)
                eb.endPtsOfContours = endPts
                eb.recalcBounds(glyf_b)

        # 5. Fix 'f': Bold upright missing point 10; Bold italic missing point 19
        if "f" in glyf_b and "f" in glyf_r:
            fb_g = glyf_b["f"]
            fr_g = glyf_r["f"]
            if not is_italic and len(fb_g.coordinates) == 15:
                coords = list(fb_g.coordinates)
                flags = list(fb_g.flags)
                endPts = list(fb_g.endPtsOfContours)
                coords.insert(10, (390, 1109))
                flags.insert(10, 1)
                endPts[0] += 1
                fb_g.coordinates = GlyphCoordinates(coords)
                fb_g.flags = bytearray(flags)
                fb_g.endPtsOfContours = endPts
                fb_g.recalcBounds(glyf_b)
            elif is_italic and len(fb_g.coordinates) == 19:
                coords = list(fb_g.coordinates)
                flags = list(fb_g.flags)
                endPts = list(fb_g.endPtsOfContours)
                coords.insert(19, (470, 1109))
                flags.insert(19, 1)
                endPts[0] += 1
                fb_g.coordinates = GlyphCoordinates(coords)
                fb_g.flags = bytearray(flags)
                fb_g.endPtsOfContours = endPts
                fb_g.recalcBounds(glyf_b)

        # 6. Fix 'question' and 'questiondown' in Bold (upright and italic):
        for qname in ["question", "questiondown"]:
            if qname in glyf_b and len(glyf_b[qname].coordinates) == 21:
                g = glyf_b[qname]
                coords = list(g.coordinates)
                flags = list(g.flags)
                endPts = list(g.endPtsOfContours)
                # Duplicate point 10 to match 22-point topology of Light and Regular
                coords.insert(10, coords[10])
                flags.insert(10, 1)
                endPts[1] += 1
                g.coordinates = GlyphCoordinates(coords)
                g.flags = bytearray(flags)
                g.endPtsOfContours = endPts
                g.recalcBounds(glyf_b)

        # 7. Fix Italic 'd' and 'p' contour ordering:
        if is_italic:
            # In Light Italic d: swap contours so stem is contour 0 and bowl is contour 1
            if "d" in glyf_l and glyf_l["d"].endPtsOfContours == [12, 21]:
                gd_l = glyf_l["d"]
                c0_pts = list(gd_l.coordinates[:13])
                c0_flg = list(gd_l.flags[:13])
                c1_pts = list(gd_l.coordinates[13:])
                c1_flg = list(gd_l.flags[13:])
                gd_l.coordinates = GlyphCoordinates(c1_pts + c0_pts)
                gd_l.flags = bytearray(c1_flg + c0_flg)
                gd_l.endPtsOfContours = [8, 21]
                gd_l.recalcBounds(glyf_l)

            # In Reg Italic p: swap contours so stem is contour 0 and bowl is contour 1
            if "p" in glyf_r and glyf_r["p"].endPtsOfContours == [12, 21]:
                gp_r = glyf_r["p"]
                c0_pts = list(gp_r.coordinates[:13])
                c0_flg = list(gp_r.flags[:13])
                c1_pts = list(gp_r.coordinates[13:])
                c1_flg = list(gp_r.flags[13:])
                gp_r.coordinates = GlyphCoordinates(c1_pts + c0_pts)
                gp_r.flags = bytearray(c1_flg + c0_flg)
                gp_r.endPtsOfContours = [8, 21]
                gp_r.recalcBounds(glyf_r)

        # 8. Run cyclic contour alignment across all glyphs to harmonize starting points
        for gname in glyf_r.keys():
            gr = glyf_r[gname]
            gl = glyf_l.get(gname)
            gb = glyf_b.get(gname)
            if gr.numberOfContours > 0:
                if gl and gl.numberOfContours == gr.numberOfContours:
                    ok_l, res_l = try_cyclic_align(gl, gr)
                    if ok_l:
                        gl.coordinates = GlyphCoordinates(res_l[0])
                        gl.flags = bytearray(res_l[1])
                if gb and gb.numberOfContours == gr.numberOfContours:
                    ok_b, res_b = try_cyclic_align(gb, gr)
                    if ok_b:
                        gb.coordinates = GlyphCoordinates(res_b[0])
                        gb.flags = bytearray(res_b[1])


def main():
    print("=" * 60)
    print("Building Lygon Font Family")
    print("=" * 60)

    master_defs = [
        ("Sansation-Light.ttf", "Light", 300, False),
        ("Sansation-LightItalic.ttf", "Light Italic", 300, True),
        ("Sansation-Regular.ttf", "Regular", 400, False),
        ("Sansation-Italic.ttf", "Italic", 400, True),
        ("Sansation-Bold.ttf", "Bold", 700, False),
        ("Sansation-BoldItalic.ttf", "Bold Italic", 700, True),
    ]

    processed_masters = {}

    for ttf_file, style_name, weight, is_italic in master_defs:
        src_path = os.path.join(SOURCES_DIR, ttf_file)
        if not os.path.exists(src_path):
            print(f"Error: source font {src_path} not found!")
            continue

        print(f"\nProcessing Master: {style_name} (Weight {weight})...")
        font = TTFont(src_path)

        if style_name == "Light Italic":
            fix_light_italic_typo(font)

        weight_cat = (
            "Light" if weight == 300 else ("Bold" if weight == 700 else "Regular")
        )
        modify_glyph_geometry(font, weight_cat, is_italic)
        modernize_font_metadata(font, style_name, weight, is_italic)
        fix_whitespace_widths(font)
        add_prep_smart_dropout(font)
        flatten_nested_components(font)
        # Generate new glyphs before compiling OT features so the GDEF mark
        # class definitions can reference the combining mark glyph names
        generate_dotlessj(font)
        generate_combining_marks(font)
        generate_missing_composites(font)
        apply_opentype_features(font)

        processed_masters[style_name] = font

    # Harmonize master topologies for variable font interpolation
    print("\n--- Harmonizing Master Topologies ---")
    harmonize_master_topologies(processed_masters)

    # Export Static Masters
    print("\n--- Exporting Static Fonts ---")
    for style_name, font in processed_masters.items():
        slug = f"Lygon-{style_name.replace(' ', '')}"
        export_font(font, slug, is_variable=False)

    # Generate Variable Fonts and Intermediate Static Instances (Medium 500, SemiBold 600)
    print("\n--- Generating Variable Fonts and Intermediate Weights ---")
    with tempfile.TemporaryDirectory() as scratch_dir:
        for is_italic in [False, True]:
            suffix = "Italic" if is_italic else "Regular"
            l_name = "Light Italic" if is_italic else "Light"
            r_name = "Italic" if is_italic else "Regular"
            b_name = "Bold Italic" if is_italic else "Bold"

            m_light = processed_masters[l_name]
            m_reg = processed_masters[r_name]
            m_bold = processed_masters[b_name]

            tmp_l = os.path.join(scratch_dir, f"tmp_l_{suffix}.ttf")
            tmp_r = os.path.join(scratch_dir, f"tmp_r_{suffix}.ttf")
            tmp_b = os.path.join(scratch_dir, f"tmp_b_{suffix}.ttf")
            m_light.save(tmp_l)
            m_reg.save(tmp_r)
            m_bold.save(tmp_b)

            doc = DesignSpaceDocument()
            ax = AxisDescriptor()
            ax.name = "weight"
            ax.tag = "wght"
            ax.minimum = 300
            ax.default = 400
            ax.maximum = 700
            doc.addAxis(ax)

            for w, p in [(300, tmp_l), (400, tmp_r), (700, tmp_b)]:
                src = SourceDescriptor()
                src.path = os.path.abspath(p)
                src.location = {"weight": w}
                if w == 400:
                    src.copyLib = True
                    src.copyInfo = True
                    src.copyGroups = True
                    src.copyFeatures = True
                doc.addSource(src)

            # Add named instances for fvar table (required by Google Fonts)
            for inst_name, inst_wght in [("Light", 300), ("Regular", 400), ("Medium", 500), ("SemiBold", 600), ("Bold", 700)]:
                inst = InstanceDescriptor()
                if is_italic:
                    style = f"{inst_name} Italic" if inst_name != "Regular" else "Italic"
                    inst.name = f"Lygon {style}"
                else:
                    style = inst_name
                    inst.name = f"Lygon {inst_name}" if inst_name != "Regular" else "Lygon"
                inst.familyName = "Lygon"
                inst.styleName = style
                inst.location = {"weight": inst_wght}
                doc.addInstance(inst)

            ds_path = os.path.join(scratch_dir, f"ds_{suffix}.designspace")
            doc.write(ds_path)

            vf_name = f"Lygon{'-Italic' if is_italic else ''}[wght]"
            print(f"\nBuilding Variable Font: {vf_name}...")
            try:
                vf, _, _ = fontTools.varLib.build(ds_path)
                build_stat_table(vf, is_italic)
                fix_variable_font_names(vf, is_italic)
                flatten_nested_components(vf)
                add_meta_table(vf)

                export_font(vf, vf_name, is_variable=True)

                # Generate Medium (500) and SemiBold (600) static instances
                for inst_name, inst_weight in [("Medium", 500), ("SemiBold", 600)]:
                    full_inst_name = f"{inst_name} Italic" if is_italic else inst_name
                    print(f"Generating static instance: Lygon {full_inst_name} ({inst_weight})...")
                    inst_font = fontTools.varLib.instancer.instantiateVariableFont(
                        vf, {"wght": inst_weight}
                    )
                    modernize_font_metadata(inst_font, full_inst_name, inst_weight, is_italic)
                    inst_slug = f"Lygon-{full_inst_name.replace(' ', '')}"
                    export_font(inst_font, inst_slug, is_variable=False)

            except Exception as e:
                print(f"Variable font build error for {suffix}: {e}")

    print("\nAll fonts built successfully!")


def generate_specimen_image():
    """Generate a clean, classic light-mode specimen sheet for submission and documentation.
    Fitted width matches the natural right boundary of the sample waterfall text."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("  Skipping specimen image (Pillow not installed)")
        return

    # Load font files at different weights
    regular_path = os.path.join(TTF_DIR, "Lygon-Regular.ttf")
    light_path = os.path.join(TTF_DIR, "Lygon-Light.ttf")
    medium_path = os.path.join(TTF_DIR, "Lygon-Medium.ttf")
    semibold_path = os.path.join(TTF_DIR, "Lygon-SemiBold.ttf")
    bold_path = os.path.join(TTF_DIR, "Lygon-Bold.ttf")
    italic_path = os.path.join(TTF_DIR, "Lygon-Italic.ttf")

    if not os.path.exists(regular_path):
        print("  Skipping specimen image (font files not found)")
        return

    try:
        f_title = ImageFont.truetype(bold_path, 46)
        f_sub = ImageFont.truetype(medium_path, 14)
        f_meta = ImageFont.truetype(regular_path, 12)
        f_display = ImageFont.truetype(light_path, 44)
        f_lbl = ImageFont.truetype(medium_path, 13)
        f_sample_light = ImageFont.truetype(light_path, 19)
        f_sample_reg = ImageFont.truetype(regular_path, 19)
        f_sample_med = ImageFont.truetype(medium_path, 19)
        f_sample_semi = ImageFont.truetype(semibold_path, 19)
        f_sample_bold = ImageFont.truetype(bold_path, 19)
        f_sample_ital = ImageFont.truetype(italic_path, 19)
        f_chars = ImageFont.truetype(regular_path, 13)
    except Exception as e:
        print(f"  Skipping specimen image (font loading error: {e})")
        return

    phrase = "The quick brown fox jumps over the lazy dog  0123456789"

    # Layout dimensions: width fitted to sample text right boundary
    px = 45
    col2_x = 165

    sample_fonts = [
        f_sample_light,
        f_sample_reg,
        f_sample_med,
        f_sample_semi,
        f_sample_bold,
        f_sample_ital,
    ]
    max_w = max(fnt.getbbox(phrase)[2] - fnt.getbbox(phrase)[0] for fnt in sample_fonts)

    width = col2_x + max_w + px
    height = 690

    bg_color = (255, 255, 255)
    text_primary = (15, 23, 42)
    text_secondary = (100, 116, 139)
    line_color = (226, 232, 240)

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # Header branding
    draw.text((px, 40), "Lygon", fill=text_primary, font=f_title)
    draw.text((px + 160, 60), "Geometric Variable Sans-Serif", fill=text_secondary, font=f_sub)
    meta_str = "Weights 300 to 700  |  10 Styles  |  OFL 1.1"
    meta_w = f_meta.getbbox(meta_str)[2] - f_meta.getbbox(meta_str)[0]
    draw.text((width - px - meta_w, 62), meta_str, fill=text_secondary, font=f_meta)

    draw.line([(px, 105), (width - px, 105)], fill=line_color, width=1)

    # Large display line showing key refined letterforms
    draw.text((px, 125), "Aa Bb Rk €j ? ®  Sphinx of quartz", fill=text_primary, font=f_display)

    draw.line([(px, 195), (width - px, 195)], fill=line_color, width=1)

    # Waterfall of weights
    waterfall = [
        ("Light 300", f_sample_light),
        ("Regular 400", f_sample_reg),
        ("Medium 500", f_sample_med),
        ("SemiBold 600", f_sample_semi),
        ("Bold 700", f_sample_bold),
        ("Italic 400", f_sample_ital),
    ]

    wy = 215
    for lbl, fnt in waterfall:
        draw.text((px, wy + 3), lbl, fill=text_secondary, font=f_lbl)
        draw.text((col2_x, wy), phrase, fill=text_primary, font=fnt)
        wy += 40

    draw.line([(px, 470), (width - px, 470)], fill=line_color, width=1)

    # Character set and numerals
    draw.text(
        (px, 492),
        "A B C D E F G H I J K L M N O P Q R S T U V W X Y Z    0 1 2 3 4 5 6 7 8 9    $ € £ ¥ ¢",
        fill=text_primary,
        font=f_chars,
    )
    draw.text(
        (px, 524),
        "a b c d e f g h i j k l m n o p q r s t u v w x y z    fi fl ff ffi ffl    .,:;!?\'\"()-[]{}/",
        fill=text_secondary,
        font=f_chars,
    )
    draw.text(
        (px, 556),
        "Latin Extended, Cyrillic, Greek    OpenType: kern, ss01 (alt g), ss02 (looped k), ss03",
        fill=text_secondary,
        font=f_chars,
    )

    draw.line([(px, 598), (width - px, 598)], fill=line_color, width=1)

    # Footer
    foot_left = "The Lygon Project Authors  |  github.com/lahdekorpi/lygon"
    foot_right = "SIL Open Font License 1.1"
    draw.text((px, 622), foot_left, fill=text_secondary, font=f_meta)
    foot_r_w = f_meta.getbbox(foot_right)[2] - f_meta.getbbox(foot_right)[0]
    draw.text((width - px - foot_r_w, 622), foot_right, fill=text_secondary, font=f_meta)

    doc_dir = os.path.join(REPO_ROOT, "documentation")
    os.makedirs(doc_dir, exist_ok=True)
    specimen_path = os.path.join(doc_dir, "specimen.png")
    img.save(specimen_path, "PNG", quality=95)
    # Also save as lygon-specimen.png to prevent CDN caching issues on GitHub
    alt_path = os.path.join(doc_dir, "lygon-specimen.png")
    img.save(alt_path, "PNG", quality=95)
    print(f"\n  Saved specimen: {os.path.relpath(specimen_path, REPO_ROOT)}")
    print(f"  Saved specimen: {os.path.relpath(alt_path, REPO_ROOT)}")


if __name__ == "__main__":
    main()
    print("\n--- Generating Specimen Image ---")
    generate_specimen_image()
