#!/usr/bin/env python3
"""
CVPR Keyword Statistics Analyzer

Analyzes the scraped CVPR abstracts for specific keyword appearances per year.
Searches through titles and abstracts for robotics-related terms.

Usage: python cvpr_keyword_stats.py
"""

import json
import re
from collections import defaultdict, Counter
import os
from pathlib import Path
import argparse

def load_cvpr_data(data_file):
    """Load the scraped CVPR data from JSON file"""
    if not os.path.exists(data_file):
        print(f"❌ Data file not found: {data_file}")
        print("💡 Run the scraper first: python cvpr_abstract_scraper_async.py")
        return None
    
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ Loaded {len(data)} papers from {data_file}")
        return data
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        return None

def search_keywords_in_text(text, keywords):
    """Search for keywords in text (case-insensitive, word boundaries)"""
    if not text:
        return set()
    
    found_keywords = set()
    text_lower = text.lower()
    
    for keyword in keywords:
        # Use word boundaries to avoid partial matches
        pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
        if re.search(pattern, text_lower):
            found_keywords.add(keyword)
    
    return found_keywords

def analyze_papers(papers, keywords):
    """Analyze papers for keyword occurrences"""
    
    # Statistics storage
    year_stats = defaultdict(lambda: defaultdict(int))      # per keyword per year counts
    year_totals = defaultdict(int)                          # total papers per year
    keyword_papers = defaultdict(list)                      # list of papers per keyword
    year_any_titles = defaultdict(set)                      # titles with ANY keyword per year
    
    print(f"🔍 Analyzing {len(papers)} papers for keywords: {', '.join(keywords)}")
    
    for paper in papers:
        year = paper.get('year', 'Unknown')
        title = paper.get('title', '')
        abstract = paper.get('abstract', '')
        
        # Count total papers per year
        year_totals[year] += 1
        
        # Search in both title and abstract
        combined_text = f"{title} {abstract}"
        found_keywords = search_keywords_in_text(combined_text, keywords)
        
        # Record findings
        for keyword in found_keywords:
            year_stats[year][keyword] += 1
            keyword_papers[keyword].append({
                'year': year,
                'title': title,
                'url': paper.get('url', '')
            })
        
        # Track combined (ANY) occurrence once per paper
        if found_keywords:
            year_any_titles[year].add(title)
    
    # Compute counts of unique papers with ANY keyword per year
    year_any_counts = {yr: len(titles) for yr, titles in year_any_titles.items()}

    return year_stats, year_totals, keyword_papers, year_any_counts

def print_statistics(year_stats, year_totals, year_any_counts, keywords, keyword_papers):
    """Print formatted statistics with unique combined counts (no double counting)."""
    
    # Sort years
    sorted_years = sorted(year_totals.keys())
    
    print("\n" + "="*80)
    print("📊 CVPR KEYWORD STATISTICS ANALYSIS")
    print("="*80)
    
    # Overall summary
    total_papers = sum(year_totals.values())
    print(f"\n📋 Dataset Summary:")
    print(f"   Total papers analyzed: {total_papers:,}")
    print(f"   Years covered: {min(sorted_years)} - {max(sorted_years)}")
    print(f"   Keywords tracked: {', '.join(keywords)}")
    
    # Year-by-year table
    print(f"\n📈 Keyword Occurrences by Year:")
    print("-" * 80)
    
    # Header
    header = f"{'Year':<6} {'Total':<7}"
    for keyword in keywords:
        header += f"{keyword.capitalize():<12}"
    header += "Combined"
    print(header)
    print("-" * 80)
    
    # Data rows
    total_keyword_counts = defaultdict(int)
    
    for year in sorted_years:
        total_papers_year = year_totals[year]
        row = f"{year:<6} {total_papers_year:<7}"
        
        for keyword in keywords:
            count = year_stats[year][keyword]
            percentage = (count / total_papers_year * 100) if total_papers_year > 0 else 0
            row += f"{count:>3} ({percentage:4.1f}%)"[:11].ljust(12)
            total_keyword_counts[keyword] += count
        
        # Combined count (papers with ANY of the keywords) - unique per title
        combined_count = year_any_counts.get(year, 0)
        combined_pct = (combined_count / total_papers_year * 100) if total_papers_year > 0 else 0
        row += f"{combined_count:>3} ({combined_pct:4.1f}%)"
        
        print(row)
    
    # Summary statistics
    print("-" * 80)
    summary_row = f"{'Total':<6} {total_papers:<7}"
    for keyword in keywords:
        total_count = total_keyword_counts[keyword]
        total_pct = (total_count / total_papers * 100) if total_papers > 0 else 0
        summary_row += f"{total_count:>3} ({total_pct:4.1f}%)"[:11].ljust(12)
    print(summary_row)
    
    # Trends analysis
    print(f"\n📈 Trends Analysis:")
    for keyword in keywords:
        early_years = [year for year in sorted_years if year <= 2018]
        recent_years = [year for year in sorted_years if year >= 2020]
        
        if early_years and recent_years:
            early_total = sum(year_totals[year] for year in early_years)
            recent_total = sum(year_totals[year] for year in recent_years)
            early_keyword = sum(year_stats[year][keyword] for year in early_years)
            recent_keyword = sum(year_stats[year][keyword] for year in recent_years)
            
            early_rate = (early_keyword / early_total * 100) if early_total > 0 else 0
            recent_rate = (recent_keyword / recent_total * 100) if recent_total > 0 else 0
            trend = recent_rate - early_rate
            
            trend_emoji = "📈" if trend > 0.5 else "📉" if trend < -0.5 else "➡️"
            print(f"   {keyword.capitalize()}: {early_rate:.1f}% (2015-2018) → {recent_rate:.1f}% (2020+) {trend_emoji}")

def find_interesting_papers(keyword_papers, keywords, limit=3):
    """Find some interesting papers for each keyword"""
    
    print(f"\n🔍 Sample Papers by Keyword:")
    print("-" * 80)
    
    for keyword in keywords:
        papers = keyword_papers.get(keyword, [])
        if papers:
            print(f"\n🤖 {keyword.upper()} ({len(papers)} total papers):")
            
            # Show recent papers first, limited
            recent_papers = [p for p in papers if p['year'] >= 2020]
            sample_papers = recent_papers[:limit] if recent_papers else papers[:limit]
            
            for paper in sample_papers:
                print(f"   [{paper['year']}] {paper['title']}")
            
            if len(papers) > limit:
                print(f"   ... and {len(papers) - limit} more papers")

def save_detailed_stats(year_stats, year_totals, keywords, output_file):
    """Save detailed statistics to a CSV file"""
    
    import csv
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Header
        header = ['Year', 'Total_Papers'] + [f'{kw.capitalize()}_Count' for kw in keywords] + [f'{kw.capitalize()}_Percentage' for kw in keywords]
        writer.writerow(header)
        
        # Data
        for year in sorted(year_totals.keys()):
            total = year_totals[year]
            row = [year, total]
            
            # Counts
            for keyword in keywords:
                row.append(year_stats[year][keyword])
            
            # Percentages
            for keyword in keywords:
                count = year_stats[year][keyword]
                percentage = (count / total * 100) if total > 0 else 0
                row.append(f"{percentage:.2f}")
            
            writer.writerow(row)
    
    print(f"\n💾 Detailed statistics saved to: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Analyze CVPR abstracts for keyword statistics')
    parser.add_argument('--data-file', default='cvpr_data/cvpr_abstracts_all.json', 
                       help='Path to the scraped CVPR data JSON file')
    parser.add_argument('--keywords', nargs='+', 
                       default=['robot', 'robotics', 'embodied', 'embodiment'],
                       help='Keywords to search for')
    parser.add_argument('--save-csv', type=str, help='Save detailed stats to CSV file')
    parser.add_argument('--sample-papers', type=int, default=3, 
                       help='Number of sample papers to show per keyword')
    
    args = parser.parse_args()
    
    # Load data
    papers = load_cvpr_data(args.data_file)
    if not papers:
        return
    
    # Analyze
    year_stats, year_totals, keyword_papers, year_any_counts = analyze_papers(papers, args.keywords)
    
    # Display results
    print_statistics(year_stats, year_totals, year_any_counts, args.keywords, keyword_papers)
    find_interesting_papers(keyword_papers, args.keywords, args.sample_papers)
    
    # Save CSV if requested
    if args.save_csv:
        save_detailed_stats(year_stats, year_totals, args.keywords, args.save_csv)
    
    print(f"\n✅ Analysis complete!")

if __name__ == "__main__":
    main() 