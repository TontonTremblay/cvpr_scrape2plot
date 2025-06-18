#!/usr/bin/env python3
"""
Plot CVPR keyword trends in XKCD style.

This script loads the merged CVPR abstracts JSON file (default: cvpr_data/cvpr_abstracts_all.json),
counts occurrences of specified keywords per year in titles + abstracts, and then generates a fun
XKCD-style line chart showing how popular each keyword has been over the years.

Usage (default keywords: robot, robotics, embodied, embodiment):

    python plot_keyword_trends_xkcd.py
    python plot_keyword_trends_xkcd.py --keywords robot manipulation grasp --save trends.png

The plot will pop up in an interactive window and can optionally be saved to disk.
"""

import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Set

import matplotlib.pyplot as plt
from matplotlib import font_manager as _fm
import logging as _logging
import inflect

# --------------------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------------------

def load_papers(json_path: str):
    """Load the JSON list of paper dicts. Returns list or None on failure."""
    if not os.path.exists(json_path):
        print(f"❌ Data file not found: {json_path}")
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"✅ Loaded {len(data):,} papers from {json_path}")
        return data
    except Exception as e:
        print(f"❌ Error reading {json_path}: {e}")
        return None

_inflect_eng = inflect.engine()

def _keyword_variants(base: str) -> List[str]:
    """Return the base and plural form of a word using the inflect library."""
    base_l = base.lower()
    plural = _inflect_eng.plural(base_l)
    variants = {base_l}
    if plural and plural != base_l:
        variants.add(plural)
    return list(variants)

def search_keywords(text: str, keywords: List[str]) -> Set[str]:
    """Return the subset of keywords (base form) found in text, checking simple plural variants."""
    hits = set()
    if not text:
        return hits
    text_lower = text.lower()
    for kw in keywords:
        variants = _keyword_variants(kw)
        # Build combined regex of variants
        pattern = r"\b(" + "|".join(re.escape(v) for v in variants) + r")\b"
        if re.search(pattern, text_lower):
            hits.add(kw)
    return hits

def aggregate_by_year(papers: List[Dict], keywords: List[str]):
    """Count keyword occurrences and total papers per year.

    Returns three dicts:
        1. year_keyword_counts: dict[year][keyword] -> count
        2. year_totals: dict[year] -> total papers
        3. year_any_counts: dict[year] -> papers containing *any* of the keywords (no double counting)
    """
    year_keyword_counts = defaultdict(lambda: defaultdict(int))  # year -> kw -> count
    year_totals = defaultdict(int)
    year_any_titles = defaultdict(set)  # year -> set of unique paper identifiers (titles)

    for p in papers:
        year = p.get("year")
        if not isinstance(year, int):
            continue  # skip malformed year

        year_totals[year] += 1

        title = p.get("title", "").strip()
        combined_text = f"{title} {p.get('abstract', '')}"
        hits = search_keywords(combined_text, keywords)

        if hits:
            year_any_titles[year].add(title)

        for kw in hits:
            year_keyword_counts[year][kw] += 1

    # Derive counts without duplicates
    year_any_counts = {yr: len(titles) for yr, titles in year_any_titles.items()}

    return year_keyword_counts, year_totals, year_any_counts

# --------------------------------------------------------------------------------------
# Font registration (local xkcd font support)
# --------------------------------------------------------------------------------------

# If user has copied `xkcd-script.ttf` into the project (root or same folder as this script),
# register it with Matplotlib so the `plt.xkcd()` context can find it even if the OS hasn't
# installed the font system-wide.

_LOCAL_FONT_NAMES = ["xkcd-script.ttf", "xkcd_script.ttf", "xkcd-script.otf"]

def _register_local_xkcd_font():
    for fname in _LOCAL_FONT_NAMES:
        for search_dir in [Path(__file__).parent, Path.cwd()]:
            font_path = search_dir / fname
            if font_path.exists():
                try:
                    _fm.fontManager.addfont(str(font_path))
                    # Rebuild font cache so the new font is available.
                    if hasattr(_fm, "_rebuild"):
                        _fm._rebuild()
                    else:
                        # Trigger a rebuild by asking findfont to rebuild cache if missing
                        _fm.findfont("xkcd Script", rebuild_if_missing=True)
                    # Set default font family to use it
                    import matplotlib as mpl
                    mpl.rcParams["font.family"] = ["xkcd Script"]
                    print(f"✅ Registered local XKCD font: {font_path}")
                    return
                except Exception as e:
                    print(f"⚠️  Failed to register local font {font_path}: {e}")
    # No local font found; nothing to register

_register_local_xkcd_font()

# Silence noisy "findfont" INFO messages from Matplotlib
_logging.getLogger("matplotlib.font_manager").setLevel(_logging.ERROR)

# --------------------------------------------------------------------------------------
# Plotting
# --------------------------------------------------------------------------------------

def plot_trends(year_keyword_counts, year_totals, year_any_counts, keywords, metric="percentage", include_combined=False, save_path=None):
    """Plot keyword trends over years in xkcd style.

    metric: "percentage" or "count".
    """
    years = sorted(year_totals.keys())
    if not years:
        print("❌ No year data to plot!")
        return

    with plt.xkcd():
        fig, ax = plt.subplots(figsize=(12, 6))

        for kw in keywords:
            if kw == "embodiment":
                continue
                
            y_values = []
            for y in years:
                kw_count = year_keyword_counts[y].get(kw, 0)
                if metric == "percentage":
                    total = year_totals[y]
                    val = kw_count / total * 100 if total else 0
                else:
                    val = kw_count
                y_values.append(val)
            ax.plot(years, y_values, marker="o", linewidth=2, linestyle="-", label=kw)

        if include_combined:
            # Combined (ANY) line
            combined_values = []
            for y in years:
                if metric == "percentage":
                    total = year_totals[y]
                    val = year_any_counts.get(y, 0) / total * 100 if total else 0
                else:
                    val = year_any_counts.get(y, 0)
                combined_values.append(val)

            ax.plot(years, combined_values, marker="s", linewidth=3, linestyle="--", color="black", label="Any")

        ax.set_xlabel("Year")
        ylabel = "% of papers" if metric == "percentage" else "# Papers"
        ax.set_ylabel(ylabel)
        ax.set_title("JONATHAN TREMBLAY @ CVPR")
        ax.legend()
        ax.grid(True, linestyle="-", alpha=0.25)
        fig.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300)
            print(f"💾 Plot saved to {save_path}")
        plt.show()

# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Plot CVPR keyword trends in XKCD style")
    parser.add_argument("--data-file", default="cvpr_data/cvpr_abstracts_all.json",
                        help="Path to the merged CVPR abstracts JSON file")
    parser.add_argument("--keywords", nargs="+", default=["robot", "robotics", "embodied", "embodiment"],
                        help="Keywords to plot")
    parser.add_argument("--metric", choices=["percentage", "count"], default="percentage",
                        help="Plot percentages or raw counts")
    parser.add_argument("--combined", action="store_true", help="Include a line showing papers with ANY of the keywords")
    parser.add_argument("--save", metavar="PATH", help="Save the figure to this path instead of just showing")
    args = parser.parse_args()

    papers = load_papers(args.data_file)
    if papers is None:
        return

    year_keyword_counts, year_totals, year_any_counts = aggregate_by_year(papers, args.keywords)
    if not year_keyword_counts:
        print("❌ No data to plot after aggregation!")
        return

    plot_trends(
        year_keyword_counts,
        year_totals,
        year_any_counts,
        args.keywords,
        metric=args.metric,
        include_combined=args.combined,
        save_path=args.save,
    )

    print("✅ Plotting complete!")

if __name__ == "__main__":
    main() 