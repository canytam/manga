"""
Comic Download and PDF Conversion Tool

This script automates the process of downloading comic chapters from 8comic.com,
converting the images to PDF format, and generating a web-based content index.

Key Features:
- Automated browser navigation using Playwright
- Image URL extraction and validation
- Parallel image downloading with retry mechanisms
- Image processing and PDF conversion with size optimization
- Web content page generation with metadata
- Existing file handling and overwrite protection

Modules:
- async_playwright: For browser automation and web scraping
- BeautifulSoup: HTML parsing
- img2pdf: PDF generation from images
- requests: Image downloading with session management
- ThreadPoolExecutor: Parallel image processing
- PyPDF2: PDF metadata extraction

Usage:
python script.py --book-id <comic_id> [--overwrite] [--show-content]
"""

from playwright.async_api import async_playwright, Playwright, TimeoutError as PlaywrightTimeoutError
import asyncio
from bs4 import BeautifulSoup
import os
from urllib.parse import unquote, urlparse, quote, urljoin
import logging
import argparse
import requests
import img2pdf
from tempfile import TemporaryDirectory
from PIL import Image
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import time
from PyPDF2 import PdfReader, PdfWriter
import webbrowser
import aiohttp


def get_image_path(index, chapter_name, chapter_dir):
    """Generate standardized path for storing image URL lists
    Args:
        index: Chapter number
        chapter_name: Sanitized chapter name
        chapter_dir: Base directory for comic storage
    Returns:
        Path to chapter's image list file
    """
    return os.path.join(chapter_dir, f'{chapter_dir}-images', f'ch{index:04d} - {chapter_name}.txt')

def get_pdf_path(index, chapter_name, chapter_dir):
    """Generate standardized path for PDF files
    Args:
        index: Chapter number
        chapter_name: Sanitized chapter name
        chapter_dir: Base directory for comic storage
    Returns:
        Path to chapter's PDF file
    """
    return os.path.join(chapter_dir, f'{chapter_dir}-pdf', f'ch{index:04d} - {chapter_name}.pdf')

def create_web_content_page(pdf_folder: str, show_content: bool = False) -> None:
    """Generate HTML index page for downloaded PDFs
    Args:
        pdf_folder: Path containing PDF files
        show_content: Automatically open in browser when True
    Generates:
        index.html with responsive design and file metadata
    """
    # Create list to store PDF information
    pdf_files = []
    
    # Collect PDF metadata
    for filename in sorted(os.listdir(pdf_folder)):
        if filename.lower().endswith('.pdf'):
            filepath = os.path.join(pdf_folder, filename)
            try:
                with open(filepath, 'rb') as f:
                    pdf = PdfReader(f)
                    info = {
                        'title': os.path.splitext(filename)[0],
                        'filename': filename,
                        'pages': len(pdf.pages),
                        'size': f"{os.path.getsize(filepath) / 1024:.1f} KB",
                        'modified': time.ctime(os.path.getmtime(filepath))
                    }
                    pdf_files.append(info)
            except Exception as e:
                print(f"Error processing {filename}: {str(e)}")
                continue

    # Generate HTML content
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PDF Content Index - {os.path.basename(pdf_folder)}</title>
    <style>
        body {{ 
            font-family: Arial, sans-serif; 
            margin: 2rem; 
            background-color: #f5f5f5;
        }}
        .header {{ 
            text-align: center; 
            margin-bottom: 2rem;
            color: #2c3e50;
        }}
        .pdf-list {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .pdf-item {{
            padding: 1rem;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .pdf-item:hover {{
            background-color: #f9f9f9;
        }}
        .pdf-info {{ color: #666; font-size: 0.9rem; }}
        a {{ 
            color: #2980b9; 
            text-decoration: none;
            font-weight: bold;
        }}
        a:hover {{ color: #3498db; }}
        .stats {{
            text-align: center;
            margin-bottom: 1.5rem;
            color: #7f8c8d;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{os.path.basename(pdf_folder)}</h1>
        <div class="stats">
            Total PDFs: {len(pdf_files)} | 
            Last Updated: {time.ctime()}
        </div>
    </div>
    
    <div class="pdf-list">
        {"".join(
            f'<div class="pdf-item">'
            f'<a href="{item["filename"]}" target="_blank">{item["title"]}</a>'
            f'<div class="pdf-info">'
            f'Pages: {item["pages"]} | '
            f'Size: {item["size"]} | '
            f'Modified: {item["modified"]}'
            f'</div></div>'
            for item in pdf_files
        )}
    </div>
</body>
</html>
"""

    # Write to HTML file
    output_path = os.path.join(pdf_folder, 'index.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    # Open in default browser
    if show_content:
        webbrowser.open(f'file://{os.path.abspath(output_path)}')

def generate_pdf_from_images(image_list_path: str, output_pdf_path: str) -> None:
    """Convert image URLs to optimized PDF
    Args:
        image_list_path: Text file containing image URLs
        output_pdf_path: Target PDF file path
    Process:
        1. Parallel image downloading with retries
        2. Image validation and format conversion
        3. Smart resizing with aspect ratio preservation
        4. PDF assembly with proper DPI settings
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)

    try:
        with open(image_list_path, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"Failed to read {image_list_path}: {str(e)}")
        raise

    if not urls:
        logger.error("No valid image URLs found")
        raise ValueError("No valid image URLs found")

    session = requests.Session()
    
    retry_strategy = requests.packages.urllib3.util.Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET"]
    )
    
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=10,
        pool_maxsize=20,
        max_retries=retry_strategy
    )
    
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br'
    }

    def download_and_process(url: str):
        MAX_DIMENSION = 65500
        MIN_DIMENSION = 4  # Set minimum size to 4 pixels (4 points at 72 DPI)
        target_width = 1600
        max_retries = 3

        for attempt in range(max_retries):
            try:
                response = session.get(url, headers=headers, timeout=20)
                response.raise_for_status()
                content = response.content

                # Verify image integrity
                with BytesIO(content) as verify_buffer:
                    with Image.open(verify_buffer) as verify_img:
                        verify_img.verify()

                # Process the image
                with BytesIO(content) as img_buffer:
                    with Image.open(img_buffer) as img:
                        # Convert color modes
                        if img.mode in ('RGBA', 'P'):
                            img = img.convert('RGB')

                        # Modified resizing logic with size constraints
                        original_width, original_height = img.size
                        
                        # Handle division by zero for invalid images
                        if original_width == 0 or original_height == 0:
                            raise ValueError("Invalid image dimensions (0 size detected)")

                        # Calculate target dimensions with aspect ratio
                        ratio = target_width / original_width
                        new_height = int(original_height * ratio)

                        # Constrain dimensions to valid ranges
                        if new_height > MAX_DIMENSION:
                            ratio = MAX_DIMENSION / original_height
                            target_width = int(original_width * ratio)
                            new_height = MAX_DIMENSION

                        if target_width > MAX_DIMENSION:
                            ratio = MAX_DIMENSION / original_width
                            target_width = MAX_DIMENSION
                            new_height = int(original_height * ratio)

                        # Apply minimum size constraints
                        target_width = max(min(target_width, MAX_DIMENSION), MIN_DIMENSION)
                        new_height = max(min(new_height, MAX_DIMENSION), MIN_DIMENSION)

                        # Final resize
                        img = img.resize(
                            (target_width, new_height),
                            Image.Resampling.LANCZOS
                        )

                        # Convert and save with explicit DPI
                        output_buffer = BytesIO()
                        if img.mode in ('RGBA', 'P'):
                            img = img.convert('RGB')
                        img.save(output_buffer, format='JPEG', quality=90, dpi=(72, 72))
                        return [output_buffer.getvalue()]

            except Exception as e:
                logger.warning(f"Attempt {attempt+1}/{max_retries} failed for {url}: {str(e)}")
                if attempt == max_retries - 1:
                    logger.error(f"Permanent failure for {url}")
                    return None
                time.sleep(2 ** attempt)  # Exponential backoff

        return None

    # Update the PDF generation image collection:
    try:
        images = []
        with ThreadPoolExecutor(max_workers=min(20, os.cpu_count())) as executor:
            futures = [executor.submit(download_and_process, url) for url in urls]
            
            for future in futures:
                result = future.result()
                if result:
                    images.extend(result)
                else:
                    logger.error("Critical image missing, aborting PDF creation")
                    raise RuntimeError("Essential images failed to download")

        # Key modification: Use implicit layout for continuous images
        pdf_bytes = img2pdf.convert(
            images,
            rotation=img2pdf.Rotation.ifvalid,
            # Add these new parameters for better control
            pagesize=None,  # Enable automatic page size
            fit=img2pdf.FitMode.into,
            border=(0, 0)  # Remove any default borders
        )

        with open(output_pdf_path, 'wb') as f:
            f.write(pdf_bytes)

        logger.info(f"Successfully generated PDF: {output_pdf_path}")

    except Exception as e:
        logger.error(f"PDF Generation Failed: {str(e)}")
        raise RuntimeError(f"PDF Generation Failed: {str(e)}") from e

async def run_xmanhua(p: Playwright, book_id: str, overwrite: bool=False) -> str:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    browser = await p.chromium.launch(headless=True, slow_mo=500)
    page = await browser.new_page()

    try:
        await page.goto(f"https://www.xmanhua.com/{book_id}/")
        body = await page.inner_html('body')
        soup = BeautifulSoup(body, 'html.parser')
        book_name = soup.find('p', class_="detail-info-title").get_text(strip=True)
        book_dir = f"{book_name}_{book_id}"
        print("Book Name: ", book_name)
        print("Book directory: ", book_dir)
        os.makedirs(book_dir, exist_ok=True)
        os.makedirs(f'{book_dir}/{book_dir}-images', exist_ok=True)

        chapters = []
        for index, a_tag in enumerate(reversed(soup.find_all('a', class_="detail-list-form-item")), start=1):
            a_tag.span.decompose()
            desired_text = a_tag.get_text(strip=True)
            #logger.info('Image Path: ' + get_image_path(index, desired_text, book_dir))
            #logger.info('PDF Path: ' + get_pdf_path(index, desired_text, book_dir))
            #logger.info('overwrite: ' + str(overwrite))
            #logger.info('exists: ' + str(os.path.exists(get_image_path(index, a_tag.get_text(strip=True), book_dir))))
            if overwrite or not os.path.exists(get_image_path(index, desired_text, book_dir)):
                chapters.append({'index': index, 'href': a_tag['href'], 'name': desired_text})
                logger.info(f"Found chapter {index}: {desired_text}")
            
        if not chapters:
            await browser.close()
            return book_dir
        
        #await page.locator(f"a href='{chapters[0]['href']}'").click()
        #await page.is_visible('div.comics-end')
        #await page.click('a.view-back')

        for chapter in chapters:
            logger.info(f"Processing chapter {chapter['index']}")
            try:
                # Retry mechanism for chapter navigation
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        await page.locator(f'a href=\"{chapter["href"]}\"').click()
                        # Wait for both container AND at least one image#{chapter["id"]
                        #await asyncio.gather(
                        #    page.wait_for_selector('div.comics-end', timeout=15000),
                        #    page.wait_for_selector('div#comics-pics img', timeout=15000)
                        #)
                        break
                    except PlaywrightTimeoutError:
                        if attempt == max_retries - 1:
                            raise
                        await page.reload()
                        logger.warning(f"Retrying chapter {chapter['index']} ({attempt+1}/{max_retries})")
                
                # Multiple fallback strategies for image extraction
                images = []
                extraction_attempts = [
                    {'selector': 'div#comics-pics img[src]', 'attr': 'src'},
                    {'selector': 'img[data-src]', 'attr': 'data-src'},
                    {'selector': 'source[srcset]', 'attr': 'srcset'}
                ]

                for strategy in extraction_attempts:
                    if not images:
                        try:
                            elements = await page.query_selector_all(strategy['selector'])
                            for element in elements:
                                src = await element.get_attribute(strategy['attr'])
                                if src:
                                    # Clean and normalize URL
                                    src = unquote(src.split('?')[0])  # Remove URL parameters
                                    if src.startswith('//'):
                                        src = f'https:{src}'
                                    elif not src.startswith('http'):
                                        src = urljoin(page.url, src)
                                    images.append(src)
                        except Exception as e:
                            logger.warning(f"Image extraction failed with {strategy}: {str(e)}")

                # Final validation before saving
                if not images:
                    logger.error(f"No images found for chapter {chapter['index']} after multiple attempts")
                    continue

                # Deduplicate while preserving order
                seen = set()
                unique_images = [x for x in images if not (x in seen or seen.add(x))]

                # Save only if we have valid URLs
                output_path = get_image_path(chapter['index'], chapter['name'], book_dir)
                with open(output_path, 'w', encoding='utf-8') as f:
                    for url in unique_images:
                        f.write(f"{url}\n")
                    logger.info(f"Saved {len(unique_images)} images to {output_path}")

                await page.click('a.view-back')

            except Exception as e:
                logger.error(f"Failed chapter {chapter['index']}: {str(e)}")
                continue

        return book_dir

    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")
        return None
    finally:
        await browser.close()
   
async def run_8comic(p: Playwright, book_id: str, overwrite: bool = False) -> str:
    """Main scraping workflow for 8comic.com
    Args:
        p: Playwright instance
        book_id: Comic identifier from URL
        overwrite: Force re-download existing content
    Returns:
        Path to downloaded content directory
    Process:
        1. Browser initialization
        2. Chapter list extraction
        3. Image URL collection with multiple fallback strategies
        4. Chapter navigation with error recovery
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    browser = await p.chromium.launch(headless=True, slow_mo=500)
    page = await browser.new_page()
    # await page.goto(f"https://www.8comic.com/member/login")
    # await page.fill('input[name="username"]', 'canytam46')
    # await page.fill('input[name="password"]', '')
    # await page.get_by_role('button', name='登入').click()
    # await page.wait_for_selector('div.member_left_menu', timeout=60000)
    #time.sleep(1)

    try:
        await page.goto(f"https://www.8comic.com/html/{book_id}.html")
        header = await page.inner_html('head')
        soup = BeautifulSoup(header, 'html.parser')
        meta_name = soup.find('meta', {'name': 'name'})
        book_name = meta_name['content'].strip() if meta_name else "Unknown Comic"
        book_dir = f"{book_name}_{book_id}"
 #await page.locator('[type="submit"]').get_by_text('登入').click()
        content_page = await page.inner_html('div#chapters')
        soup = BeautifulSoup(content_page, 'html.parser')

        os.makedirs(book_dir, exist_ok=True)
        os.makedirs(f'{book_dir}/{book_dir}-images', exist_ok=True)

        chapters = []
        for index, a_tag in enumerate(soup.find_all('a'), start=1):
            if a_tag.has_attr('id'):
                #logger.info('Image Path: ' + get_image_path(index, a_tag.get_text(strip=True), book_dir))
                #logger.info('PDF Path: ' + get_pdf_path(index, a_tag.get_text(strip=True), book_dir))
                #logger.info('overwrite: ' + str(overwrite))
                #logger.info('exists: ' + str(os.path.exists(get_image_path(index, a_tag.get_text(strip=True), book_dir))))
                if overwrite or not os.path.exists(get_image_path(index, a_tag.get_text(strip=True), book_dir)):
                    chapters.append({'index': index, 'id': a_tag['id'], 'name': a_tag.get_text(strip=True)})
                    logger.info(f"Found chapter {index}: {a_tag.get_text(strip=True)}")

        if not chapters:
            await browser.close()
            return book_dir
        
        await page.click(f"a#{chapters[0]['id']}")
        await page.is_visible('div.comics-end')
        await page.click('a.view-back')

        for chapter in chapters:
            logger.info(f"Processing chapter {chapter['index']}")
            try:
                # Retry mechanism for chapter navigation
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        await page.click(f'a#{chapter["id"]}')
                        # Wait for both container AND at least one image
                        await asyncio.gather(
                            page.wait_for_selector('div.comics-end', timeout=15000),
                            page.wait_for_selector('div#comics-pics img', timeout=15000)
                        )
                        break
                    except PlaywrightTimeoutError:
                        if attempt == max_retries - 1:
                            raise
                        await page.reload()
                        logger.warning(f"Retrying chapter {chapter['index']} ({attempt+1}/{max_retries})")

                # Multiple fallback strategies for image extraction
                images = []
                extraction_attempts = [
                    {'selector': 'div#comics-pics img[src]', 'attr': 'src'},
                    {'selector': 'img[data-src]', 'attr': 'data-src'},
                    {'selector': 'source[srcset]', 'attr': 'srcset'}
                ]

                for strategy in extraction_attempts:
                    if not images:
                        try:
                            elements = await page.query_selector_all(strategy['selector'])
                            for element in elements:
                                src = await element.get_attribute(strategy['attr'])
                                if src:
                                    # Clean and normalize URL
                                    src = unquote(src.split('?')[0])  # Remove URL parameters
                                    if src.startswith('//'):
                                        src = f'https:{src}'
                                    elif not src.startswith('http'):
                                        src = urljoin(page.url, src)
                                    images.append(src)
                        except Exception as e:
                            logger.warning(f"Image extraction failed with {strategy}: {str(e)}")

                # Final validation before saving
                if not images:
                    logger.error(f"No images found for chapter {chapter['index']} after multiple attempts")
                    continue

                # Deduplicate while preserving order
                seen = set()
                unique_images = [x for x in images if not (x in seen or seen.add(x))]

                # Save only if we have valid URLs
                output_path = get_image_path(chapter['index'], chapter['name'], book_dir)
                with open(output_path, 'w', encoding='utf-8') as f:
                    for url in unique_images:
                        f.write(f"{url}\n")
                    logger.info(f"Saved {len(unique_images)} images to {output_path}")

                await page.click('a.view-back')

            except Exception as e:
                logger.error(f"Failed chapter {chapter['index']}: {str(e)}")
                continue

        return book_dir

    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")
        return None
    finally:
        await browser.close()
   
async def main() -> None:
    """Entry point for command-line execution
    Handles:
        - Argument parsing
        - Logging configuration
        - Workflow coordination
        - Error handling
    """
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description='Download comic chapters from 8comic.com')
    parser.add_argument('--book-id', required=True, help='Comic book ID to download')
    parser.add_argument('--overwrite', action='store_true', help='Force re-download of existing chapters')
    parser.add_argument('--show-content', action='store_true', help='Show content page')
    parser.add_argument('--from_8comic', action='store_true', help='https://www.8comic.com')
    parser.add_argument('--from_xmanhua', action='store_true', help='https://www.xmanhua.com/')
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )                
    
    count = (1 if args.from_8comic else 0) + (1 if args.from_xmanhua else 0)
    if (count > 1):
        print("You must select only one source from 8comic and xmanhua.", flush=True)
        exit(1)
    
    if (count < 1):
        print("You must select one source from 8comic and xmanhua.", flush=True)
        exit(1)

    try:
        if args.from_8comic:
            async with async_playwright() as playwright:
                result = None
                while not result:
                    result = await run_8comic(playwright, args.book_id, args.overwrite)
                logging.info(f"Successfully downloaded to directory: {result}")
        elif args.from_xmanhua:
            async with async_playwright() as playwright:
                result = None
                while not result:
                    result = await run_xmanhua(playwright, args.book_id, args.overwrite)
                logging.info(f"Successfully downloaded to directory: {result}")

        for filename in os.listdir(f"{result}/{result}-images"):
            if filename.endswith(".txt"):
                #logging.info("Overwrite: " + str(args.overwrite))
                #logging.info("Exists: " + str(os.path.exists(f"{result}/{result}-pdf/{filename[:-4]}.pdf")))
                if args.overwrite or not os.path.exists(f"{result}/{result}-pdf/{filename[:-4]}.pdf"):
                    logging.info(f"Generating PDF for {filename}")
                    generate_pdf_from_images(f"{result}/{result}-images/{filename}", f"{result}/{result}-pdf/{filename[:-4]}.pdf")

        #add_pdf_navigation(f"{result}/{result}-pdf")

        create_web_content_page(f"{result}/{result}-pdf", args.show_content)
        logging.info(f"Successfully generated PDFs for directory: {result}")

    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")

if __name__ == '__main__':
    asyncio.run(main())