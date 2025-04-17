# Comic Downloader & PDF Converter

A Python tool for downloading comic chapters from 8comic.com and converting them to optimized PDF files with automatic web index generation.

<!--![Workflow Diagram](https://via.placeholder.com/800x400.png?text=Comic+Downloader+Workflow) <!-- Replace with actual diagram if available -->

## Features

- **Automated Browser Navigation** using Playwright
- **Multi-source Image Extraction** with fallback strategies
- **Parallel Image Processing** with retry mechanisms
- **Smart PDF Conversion** with image optimization:
  - Automatic resizing (max 1600px width)
  - Format normalization (JPEG conversion)
  - Valid DPI settings for PDF compatibility
- **Web-based Content Index** with metadata:
  - Chapter statistics
  - File sizes
  - Modification dates
  - Responsive design

## Prerequisites

- Python 3.7+
- Modern browser (Chromium-based recommended)
- 8comic.com member account (free registration)

## Installation

1. Clone repository:
```bash
git clone https://gitlab.com/your-username/comic-downloader.git
cd comic-downloader
```

2. Install dependencies:
```bash
pip install playwright beautifulsoup4 requests img2pdf pillow PyPDF2
```

3. Install Playwright browsers:
```bash
python -m playwright install
```

## Usage
### Basic Command
```bash
python comic_downloader.py --book-id [COMIC_ID]
```

### Full Options
```bash
python comic_downloader.py \
  --book-id 12345 \          # Comic ID from 8comic URL
  --overwrite \              # Force re-download existing content
  --show-content             # Auto-open index page when complete
```

## Example Workflow
```bash
# Download comic #88434 (will create "Comic_Name_88434" folder)
python comic_downloader.py --book-id 88434

# Generate PDFs and open index page when done
python comic_downloader.py --book-id 88434 --show-content
```

## Configuration
### Environment Variables
Create .env file for authentication:
```text
COMIC_USERNAME=your_username
COMIC_PASSWORD=your_password
```

### Directory Structure
```text
Comic_Name_ID/
├── Comic_Name_ID-images/    # Raw image URL lists
│   └── ch0001 - Chapter 1.txt
├── Comic_Name_ID-pdf/       # Generated PDFs
│   ├── ch0001 - Chapter 1.pdf
│   └── index.html           # Web content index
└── metadata.json            # Future metadata storage
```

## Troubleshooting
Common Issues
1. Timeout Errors
* Increase wait times in code (default: 15s)
* Check network connectivity to 8comic.com
2. Login Failures
* Verify account credentials
* Update CSS selectors if website changes
3. Image Conversion Failures
* Check temporary internet restrictions
* Verify image URLs in .txt files

Debugging Mode

Run with logging:
```bash
python comic_downloader.py --book-id 88434 2>&1 | tee output.log
```

# Compliance Notice
⚠️ Important Legal Considerations
* Check website terms of service before use
* Only download content you have rights to access
* Respect copyright laws in your jurisdiction
*This is a proof-of-concept - use responsibly

## Contributing
1. Fork repository
2. Create feature branch (git checkout -b feature/improvement)
3. Commit changes (git commit -am 'Add new feature')
4. Push to branch (git push origin feature/improvement)
5. Create Merge Request

## License
MIT License - See LICENSE file for details

## Key elements included:
1. Clear visual hierarchy with feature highlights
2. Step-by-step installation instructions
3. Usage examples with common scenarios
4. Directory structure visualization
5. Troubleshooting section for common issues
6. Legal compliance notice
7. Contribution guidelines
8. Responsive design considerations
