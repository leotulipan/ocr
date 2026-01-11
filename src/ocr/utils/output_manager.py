"""Output manager for OCR processing results."""

import asyncio
import json
import re
import base64
import yaml
import aiohttp
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import urllib.parse

from ..models.metadata import OCRMetadata, FilenameMetadata


class OutputManager:
    """Manages output files and metadata for OCR processing."""
    
    def __init__(self, output_dir: Path = None, save_at_input_location: bool = False):
        """Initialize output manager."""
        self.output_dir = output_dir or Path.cwd() / "ocr_output"
        self.save_at_input_location = save_at_input_location
        # Don't create directory in __init__ - create it lazily when needed

    def _ensure_images_dir(self, base_dir: Path) -> Path:
        """Ensure an `images` directory exists next to the markdown file."""
        images_dir = base_dir / "images"
        images_dir.mkdir(exist_ok=True)
        return images_dir

    def _guess_ext_from_url(self, url: str, default_ext: str = ".png") -> str:
        """Guess file extension from URL path, fallback to default."""
        try:
            path = urllib.parse.urlparse(url).path
            suffix = Path(path).suffix
            if suffix:
                return suffix
        except Exception:
            pass
        return default_ext

    async def _materialize_images(self, markdown_content: str, base_dir: Path, prefix: str) -> Tuple[str, int]:
        """
        Extract embedded base64 images and download URL images referenced in markdown.
        Save them under base_dir/images with filenames prefixed by `prefix`, and rewrite
        the markdown to point to local files.

        Returns:
            updated_markdown, count_images_saved
        """
        if not markdown_content:
            return markdown_content, 0

        images_dir = None  # Create lazily only when needed
        saved_count = 0
        counter = 0

        # Optional header from adapter with an images map
        images_header_re = re.compile(r"^<!--IMAGES_MAP\n(?P<json>{[\s\S]*?})\n-->\n\n", re.MULTILINE)
        images_map = {}
        def parse_images_map(md: str) -> str:
            nonlocal images_map
            m = images_header_re.match(md)
            if not m:
                return md
            try:
                images_map = json.loads(m.group("json"))
            except Exception:
                images_map = {}
            # strip header
            return md[m.end():]

        markdown_content = parse_images_map(markdown_content)

        # Embedded data URIs
        data_uri_re = re.compile(
            r'!\[(?P<alt>.*?)\]\('
            r'(?P<mime>data:image/(?P<ext>[^;]+));base64,(?P<b64>[A-Za-z0-9+/=]+)'
            r'\)'
        )

        def replace_data_uri(m: re.Match) -> str:
            nonlocal saved_count, counter, images_dir
            alt = m.group("alt")
            ext = m.group("ext").lower().split("+")[0]
            b64 = m.group("b64")
            counter += 1
            filename = f"{prefix}_{counter}.{ext}"
            # Create images directory only when needed
            if images_dir is None:
                images_dir = self._ensure_images_dir(base_dir)
            out_path = images_dir / filename
            try:
                data = base64.b64decode(b64)
                with open(out_path, "wb") as f:
                    f.write(data)
                saved_count += 1
                print(f"saved image: images/{filename}")
                return f"![{alt}](images/{filename})"
            except Exception as e:
                print(f"Error saving data URI image {filename}: {e}")
                # Leave original if anything fails
                return m.group(0)

        updated = data_uri_re.sub(replace_data_uri, markdown_content)

        # External URLs - async download with aiohttp
        url_img_re = re.compile(
            r'!\[(?P<alt>.*?)\]\((?P<url>https?://[^\s)]+)\)'
        )

        # First pass: collect all URLs
        url_matches = list(url_img_re.finditer(updated))

        if url_matches:
            # Download all URLs concurrently
            downloaded_images = {}
            async with aiohttp.ClientSession() as session:
                download_tasks = []
                for m in url_matches:
                    url = m.group("url")
                    download_tasks.append(self._download_image(session, url))

                # Wait for all downloads to complete
                results = await asyncio.gather(*download_tasks, return_exceptions=True)

                # Map URLs to downloaded content
                for m, result in zip(url_matches, results):
                    if not isinstance(result, Exception) and result is not None:
                        downloaded_images[m.group("url")] = result

            # Second pass: replace with downloaded images
            def replace_url(m: re.Match) -> str:
                nonlocal saved_count, counter, images_dir
                alt = m.group("alt")
                url = m.group("url")

                # Check if we successfully downloaded this URL
                content = downloaded_images.get(url)
                if content is None:
                    # Download failed, leave original
                    return m.group(0)

                counter += 1
                ext = self._guess_ext_from_url(url)
                filename = f"{prefix}_{counter}{ext}"
                # Create images directory only when needed
                if images_dir is None:
                    images_dir = self._ensure_images_dir(base_dir)
                out_path = images_dir / filename
                try:
                    with open(out_path, "wb") as f:
                        f.write(content)
                    saved_count += 1
                    print(f"downloaded image: {url} -> images/{filename}")
                    return f"![{alt}](images/{filename})"
                except Exception as e:
                    print(f"Error saving image {filename}: {e}")
                    return m.group(0)

            updated = url_img_re.sub(replace_url, updated)

        # Materialize images from images_map by replacing bare filenames in links if present
        if images_map:
            file_img_re = re.compile(r'!\[(?P<alt>.*?)\]\((?P<fname>[^)\s]+)\)')

            def replace_file_link(m: re.Match) -> str:
                nonlocal saved_count, counter, images_dir
                alt = m.group("alt")
                fname = m.group("fname")
                info = images_map.get(fname)
                if not info:
                    return m.group(0)
                b64 = info.get("base64")
                mime = info.get("mime", "application/octet-stream")

                # derive extension from mime or original fname
                if "/" in mime:
                    mime_ext = mime.split("/")[-1]
                    # Convert MIME type extensions to file extensions
                    if mime_ext == "jpeg":
                        ext = ".jpg"
                    elif mime_ext == "png":
                        ext = ".png"
                    elif mime_ext == "avif":
                        ext = ".avif"
                    else:
                        ext = "." + mime_ext
                else:
                    ext = Path(fname).suffix or ".png"
                counter += 1
                filename = f"{prefix}_{counter}{ext}"
                # Create images directory only when needed
                if images_dir is None:
                    images_dir = self._ensure_images_dir(base_dir)
                out_path = images_dir / filename
                try:
                    data = base64.b64decode(b64)
                    with open(out_path, "wb") as f:
                        f.write(data)
                    saved_count += 1
                    print(f"saved image (map): images/{filename}")
                    return f"![{alt}](images/{filename})"
                except Exception as e:
                    print(f"Error saving image {filename}: {e}")
                    return m.group(0)

            updated = file_img_re.sub(replace_file_link, updated)
        return updated, saved_count

    async def _download_image(self, session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
        """Download image from URL using aiohttp."""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    print(f"Failed to download {url}: HTTP {response.status}")
                    return None
        except Exception as e:
            print(f"Error downloading {url}: {e}")
            return None
    
    async def save_text_result(self, content: str, filename: str, source_file: Path = None,
                        include_page_headlines: bool = False,
                        filename_metadata: Optional[FilenameMetadata] = None,
                        pages_processed: int = 1) -> tuple[Path, int]:
        """Save OCR text result to file and materialize image references (base64 and URLs)."""
        # Determine output location - always save in .ocr subdirectory
        if self.save_at_input_location and source_file:
            base_dir = source_file.parent
            output_dir = base_dir / ".ocr"
            # Determine filename based on page count
            if pages_processed == 1:
                output_file = output_dir / f"{source_file.stem}.pg1.md"
            else:
                output_file = output_dir / f"{source_file.stem}.md"
            prefix = source_file.stem
        else:
            output_dir = self.output_dir / ".ocr"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if pages_processed == 1:
                output_file = output_dir / f"{timestamp}_{filename}.pg1.md"
            else:
                output_file = output_dir / f"{timestamp}_{filename}.md"
            # Use provided filename as prefix when saving to common output dir
            prefix = filename

        # Create output directory if it doesn't exist
        output_dir.mkdir(parents=True, exist_ok=True)

        # Materialize images and rewrite markdown (async)
        updated_content, img_count = await self._materialize_images(content, output_dir, prefix)

        # Store original filename
        original_filename = source_file.name if source_file else None

        # Create metadata object
        metadata = OCRMetadata(
            source_file=str(source_file) if source_file else None,
            original_filename=original_filename,
            processed_at=datetime.now(),
            content_length=len(updated_content),
            include_page_headlines=include_page_headlines,
            images_saved=img_count,
            filename_metadata=filename_metadata
        )

        # Serialize to YAML frontmatter
        yaml_dict = metadata.to_yaml_dict()
        yaml_content = yaml.dump(yaml_dict, default_flow_style=False, allow_unicode=True, sort_keys=False)
        header = f"---\n{yaml_content}---\n\n"

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(header)
            f.write(updated_content)

        return output_file, img_count

    async def save_batch_results(self, results: List[str], filenames: List[str],
                          source_files: List[Path] = None, include_page_headlines: bool = False) -> List[tuple[Path, int]]:
        """Save multiple OCR results to files."""
        output_files = []
        for i, (content, filename) in enumerate(zip(results, filenames)):
            source_file = source_files[i] if source_files and i < len(source_files) else None
            output_file, img_count = await self.save_text_result(content, filename, source_file, include_page_headlines)
            output_files.append((output_file, img_count))
        return output_files
    
    def save_metadata(self, metadata: Dict[str, Any], filename: str = "processing_metadata.json") -> Path:
        """Save processing metadata to JSON file."""
        metadata_file = self.output_dir / filename
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, default=str)
        return metadata_file
