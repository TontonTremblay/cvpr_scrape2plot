#!/usr/bin/env python3
"""
CVPR Abstract Scraper - Ultra Fast Async Version (2015-2025)

This is an optimized async version using aiohttp for maximum performance.
Can be 10-20x faster than the threaded version.

Author: AI Assistant
Date: 2024
"""

import asyncio
import aiohttp
import aiofiles
from bs4 import BeautifulSoup
import time
import json
import csv
import os
import re
from urllib.parse import urljoin, urlparse
import logging
from tqdm import tqdm
import argparse
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Set
import sys
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import pickle
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cvpr_scraper_async.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class Paper:
    """Data class to represent a CVPR paper"""
    title: str
    authors: str
    abstract: str
    year: int
    url: str
    pdf_url: Optional[str] = None
    supplementary_url: Optional[str] = None

class CVPRScraperAsync:
    """Ultra-fast async scraper class for CVPR abstracts"""
    
    def __init__(self, 
                 start_year: int = 2015, 
                 end_year: int = 2025, 
                 max_concurrent: int = 100,
                 delay: float = 0.01,
                 use_cache: bool = True,
                 parallel_years: bool = True):
        self.start_year = start_year
        self.end_year = end_year
        self.max_concurrent = max_concurrent
        self.delay = delay
        self.use_cache = use_cache
        self.parallel_years = parallel_years
        self.papers = []
        self.cache_dir = Path("cvpr_cache")
        self.cache_dir.mkdir(exist_ok=True)
        
        # Connection settings optimized for speed
        self.connector_args = {
            'limit': 200,  # Total connection pool size
            'limit_per_host': 50,  # Max connections per host
            'ttl_dns_cache': 300,  # DNS cache TTL
            'use_dns_cache': True,
            'enable_cleanup_closed': True,
        }
        
        self.timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        logger.info(f"Initialized async scraper: {max_concurrent} concurrent, {delay}s delay, cache: {use_cache}")

    async def get_cached_or_fetch(self, session: aiohttp.ClientSession, url: str, cache_key: str = None) -> Optional[str]:
        """Get content from cache or fetch from URL"""
        if cache_key is None:
            cache_key = url.replace('/', '_').replace(':', '_')
        
        cache_file = self.cache_dir / f"{cache_key}.html"
        
        # Try cache first
        if self.use_cache and cache_file.exists():
            try:
                async with aiofiles.open(cache_file, 'r', encoding='utf-8') as f:
                    return await f.read()
            except Exception as e:
                logger.debug(f"Cache read error for {cache_key}: {e}")
        
        # Fetch from URL
        try:
            await asyncio.sleep(self.delay)  # Rate limiting
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.text()
                    
                    # Cache the result
                    if self.use_cache:
                        try:
                            async with aiofiles.open(cache_file, 'w', encoding='utf-8') as f:
                                await f.write(content)
                        except Exception as e:
                            logger.debug(f"Cache write error for {cache_key}: {e}")
                    
                    return content
                else:
                    logger.warning(f"HTTP {response.status} for {url}")
                    return None
                    
        except Exception as e:
            logger.error(f"Fetch error for {url}: {e}")
            return None

    async def get_paper_urls_for_year(self, session: aiohttp.ClientSession, year: int) -> List[str]:
        """Get all paper URLs for a given CVPR year"""
        logger.info(f"Getting paper URLs for CVPR {year}")
        
        # Try different URL patterns based on year
        if year <= 2015:
            base_url = f"https://www.cv-foundation.org/openaccess/content_cvpr_{year}/html/"
        else:
            base_url = f"https://openaccess.thecvf.com/CVPR{year}"
        
        content = await self.get_cached_or_fetch(session, base_url, f"cvpr_{year}_main")
        if not content:
            return []
        
        soup = BeautifulSoup(content, 'html.parser')
        paper_urls = []
        
        if year <= 2015:
            # Old CVF structure
            links = soup.find_all('a', href=True)
            for link in links:
                href = link['href']
                if href.endswith('.html') and '_' in href and not href.startswith('http'):
                    full_url = urljoin(base_url, href)
                    paper_urls.append(full_url)
        else:
            # New CVF structure - try to find paper listing
            all_papers_links = soup.find_all('a', href=True)
            papers_page_url = None
            
            for link in all_papers_links:
                text = link.get_text().strip().lower()
                if 'all papers' in text or 'papers' in text:
                    papers_page_url = urljoin(base_url, link['href'])
                    break
            
            if not papers_page_url:
                papers_page_url = f"https://openaccess.thecvf.com/CVPR{year}?day=all"
            
            # Get paper URLs from listing page
            listing_content = await self.get_cached_or_fetch(session, papers_page_url, f"cvpr_{year}_listing")
            if listing_content:
                listing_soup = BeautifulSoup(listing_content, 'html.parser')
                links = listing_soup.find_all('a', href=True)
                
                for link in links:
                    href = link['href']
                    if f'CVPR{year}' in href and 'paper.html' in href:
                        full_url = urljoin(papers_page_url, href)
                        paper_urls.append(full_url)
                    elif f'cvpr_{year}' in href and '.html' in href:
                        full_url = urljoin(papers_page_url, href)
                        paper_urls.append(full_url)
        
        # Remove duplicates and filter
        paper_urls = list(set(paper_urls))
        logger.info(f"Found {len(paper_urls)} paper URLs for CVPR {year}")
        return paper_urls

    async def scrape_paper(self, session: aiohttp.ClientSession, url: str, year: int) -> Optional[Paper]:
        """Scrape a single paper's information"""
        content = await self.get_cached_or_fetch(session, url, f"paper_{hash(url)}")
        if not content:
            return None
        
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract title
            title = ""
            title_selectors = ['title', 'h1', '.paper-title', '#papertitle']
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text().strip()
                    title = re.sub(r'CVPR\s+\d{4}.*', '', title).strip()
                    if title:
                        break
            
            # Extract authors
            authors = ""
            author_selectors = ['.authors', '.paper-authors', '#authors', '.author']
            for selector in author_selectors:
                author_elem = soup.select_one(selector)
                if author_elem:
                    authors = author_elem.get_text().strip()
                    break
            
            if not authors:
                for elem in soup.find_all(['i', 'b', 'em', 'strong']):
                    text = elem.get_text().strip()
                    if ',' in text and len(text.split(',')) > 1:
                        authors = text
                        break
            
            # Extract abstract
            abstract = ""
            abstract_selectors = [
                '.abstract', '#abstract', '.paper-abstract',
                'div:contains("Abstract")', 'p:contains("Abstract")',
                'div[id*="abstract"]', 'div[class*="abstract"]'
            ]
            
            for selector in abstract_selectors:
                abstract_elem = soup.select_one(selector)
                if abstract_elem:
                    abstract_text = abstract_elem.get_text().strip()
                    abstract = re.sub(r'^Abstract\s*:?\s*', '', abstract_text, flags=re.IGNORECASE).strip()
                    if len(abstract) > 50:
                        break
            
            # If no abstract found, look for long paragraphs
            if not abstract:
                paragraphs = soup.find_all('p')
                for p in paragraphs:
                    text = p.get_text().strip()
                    if len(text) > 200 and 'abstract' not in text.lower()[:50]:
                        abstract = text
                        break
            
            # Extract PDF and supplementary URLs
            pdf_url = ""
            supp_url = ""
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                text = link.get_text().lower()
                
                if 'pdf' in text or href.endswith('.pdf'):
                    pdf_url = urljoin(url, href)
                elif 'supp' in text or 'supplementary' in text:
                    supp_url = urljoin(url, href)
            
            if title and abstract:
                return Paper(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    year=year,
                    url=url,
                    pdf_url=pdf_url if pdf_url else None,
                    supplementary_url=supp_url if supp_url else None
                )
            else:
                logger.debug(f"Missing required fields for {url}")
                return None
                
        except Exception as e:
            logger.error(f"Error scraping paper {url}: {e}")
            return None

    async def scrape_year(self, year: int) -> List[Paper]:
        """Scrape all papers for a given year"""
        logger.info(f"Starting async scrape for CVPR {year}")
        
        connector = aiohttp.TCPConnector(**self.connector_args)
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=self.timeout,
            headers=self.headers
        ) as session:
            
            # Get paper URLs
            paper_urls = await self.get_paper_urls_for_year(session, year)
            if not paper_urls:
                logger.warning(f"No paper URLs found for CVPR {year}")
                return []
            
            # Create semaphore to limit concurrent requests
            semaphore = asyncio.Semaphore(self.max_concurrent)
            
            async def scrape_with_semaphore(url):
                async with semaphore:
                    return await self.scrape_paper(session, url, year)
            
            # Execute all scraping tasks concurrently
            tasks = [scrape_with_semaphore(url) for url in paper_urls]
            
            papers = []
            failed_count = 0
            
            # Process with progress bar
            with tqdm(total=len(tasks), desc=f"CVPR {year}") as pbar:
                for task in asyncio.as_completed(tasks):
                    paper = await task
                    if paper:
                        papers.append(paper)
                    else:
                        failed_count += 1
                    pbar.update(1)
            
            logger.info(f"CVPR {year}: {len(papers)} papers scraped, {failed_count} failed")
            return papers

    async def scrape_all_years(self) -> List[Paper]:
        """Scrape all papers for all years"""
        all_papers = []
        years = list(range(self.start_year, self.end_year + 1))
        
        if self.parallel_years and len(years) > 1:
            # Process multiple years in parallel
            logger.info(f"Processing {len(years)} years in parallel")
            tasks = [self.scrape_year(year) for year in years]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for year, result in zip(years, results):
                if isinstance(result, Exception):
                    logger.error(f"Error processing year {year}: {result}")
                else:
                    all_papers.extend(result)
                    # Save intermediate results
                    await self.save_papers_json_async(all_papers, f"cvpr_abstracts_partial_{year}.json")
        else:
            # Process years sequentially
            for year in years:
                year_papers = await self.scrape_year(year)
                all_papers.extend(year_papers)
                # Save intermediate results
                await self.save_papers_json_async(all_papers, f"cvpr_abstracts_partial_{year}.json")
        
        self.papers = all_papers
        return all_papers

    async def save_papers_json_async(self, papers: List[Paper], filename: str):
        """Async save papers to JSON file"""
        data = [asdict(paper) for paper in papers]
        
        async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))
        
        logger.info(f"Saved {len(papers)} papers to {filename}")

    def save_papers_json(self, papers: List[Paper], filename: str):
        """Sync save papers to JSON file"""
        data = [asdict(paper) for paper in papers]
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(papers)} papers to {filename}")

    def save_papers_csv(self, papers: List[Paper], filename: str):
        """Save papers to CSV file"""
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Title', 'Authors', 'Abstract', 'Year', 'URL', 'PDF_URL', 'Supplementary_URL'])
            
            for paper in papers:
                writer.writerow([
                    paper.title,
                    paper.authors,
                    paper.abstract,
                    paper.year,
                    paper.url,
                    paper.pdf_url or '',
                    paper.supplementary_url or ''
                ])
        
        logger.info(f"Saved {len(papers)} papers to {filename}")

    def get_statistics(self) -> Dict:
        """Get statistics about scraped papers"""
        if not self.papers:
            return {}
        
        stats = {
            'total_papers': len(self.papers),
            'years': sorted(list(set(paper.year for paper in self.papers))),
            'papers_per_year': {}
        }
        
        for year in stats['years']:
            year_papers = [p for p in self.papers if p.year == year]
            stats['papers_per_year'][year] = len(year_papers)
        
        return stats

async def main():
    parser = argparse.ArgumentParser(description='Ultra-fast async CVPR abstracts scraper')
    parser.add_argument('--start-year', type=int, default=2015, help='Starting year (default: 2015)')
    parser.add_argument('--end-year', type=int, default=2025, help='Ending year (default: 2025)')
    parser.add_argument('--concurrent', type=int, default=100, help='Max concurrent requests (default: 100)')
    parser.add_argument('--delay', type=float, default=0.01, help='Delay between requests in seconds (default: 0.01)')
    parser.add_argument('--output-dir', type=str, default='cvpr_data', help='Output directory (default: cvpr_data)')
    parser.add_argument('--format', choices=['json', 'csv', 'both'], default='both', help='Output format (default: both)')
    parser.add_argument('--no-cache', action='store_true', help='Disable caching')
    parser.add_argument('--sequential-years', action='store_true', help='Process years sequentially instead of parallel')
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Initialize scraper
    scraper = CVPRScraperAsync(
        start_year=args.start_year,
        end_year=args.end_year,
        max_concurrent=args.concurrent,
        delay=args.delay,
        use_cache=not args.no_cache,
        parallel_years=not args.sequential_years
    )
    
    # Record start time
    start_time = time.time()
    
    # Scrape papers
    logger.info(f"Starting ultra-fast async scraper for years {args.start_year}-{args.end_year}")
    papers = await scraper.scrape_all_years()
    
    # Calculate elapsed time
    elapsed_time = time.time() - start_time
    
    if papers:
        # Save results
        if args.format in ['json', 'both']:
            json_path = os.path.join(args.output_dir, 'cvpr_abstracts_all.json')
            scraper.save_papers_json(papers, json_path)
        
        if args.format in ['csv', 'both']:
            csv_path = os.path.join(args.output_dir, 'cvpr_abstracts_all.csv')
            scraper.save_papers_csv(papers, csv_path)
        
        # Print statistics
        stats = scraper.get_statistics()
        logger.info("🚀 ULTRA-FAST SCRAPING COMPLETED! 🚀")
        logger.info(f"⏱️  Total time: {elapsed_time:.1f} seconds ({elapsed_time/60:.1f} minutes)")
        logger.info(f"📊 Total papers: {stats['total_papers']}")
        logger.info(f"⚡ Speed: {stats['total_papers']/elapsed_time:.1f} papers/second")
        logger.info("Papers per year:")
        for year, count in stats['papers_per_year'].items():
            logger.info(f"  {year}: {count}")
    else:
        logger.error("No papers were scraped!")

if __name__ == "__main__":
    asyncio.run(main()) 