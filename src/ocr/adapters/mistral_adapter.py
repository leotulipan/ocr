"""Mistral AI adapter for OCR processing."""

import base64
from pathlib import Path
from typing import List, Optional, Set
from mistralai import Mistral, OCRResponse
import json

from ..protocols.ocr_service import OCRService
from ..models.settings import Settings
from ..utils.page_parser import PagePatternParser


class MistralOCRAdapter(OCRService):
    """Mistral AI OCR service adapter."""
    
    def __init__(self, settings: Settings):
        """Initialize the Mistral OCR adapter."""
        self.client = Mistral(api_key=settings.mistral_api_key.get_secret_value())
        self.settings = settings
    
    def _validate_image_file(self, file_path: Path) -> bool:
        """Validate that the file is a valid image file."""
        try:
            with open(file_path, "rb") as file:
                header = file.read(10)  # Read first 10 bytes
                
            ext = file_path.suffix.lower()
            if ext in ['.jpg', '.jpeg']:
                # Check for JPEG header: FF D8 FF
                return header.startswith(b'\xff\xd8\xff')
            elif ext == '.png':
                # Check for PNG header: 89 50 4E 47 0D 0A 1A 0A
                return header.startswith(b'\x89PNG\r\n\x1a\n')
            elif ext == '.avif':
                # Check for AVIF header: 00 00 00 20 66 74 79 70 61 76 69 66
                return header.startswith(b'\x00\x00\x00 ftypavif')
            else:
                # For other formats, assume valid
                return True
        except Exception:
            return False
    
    def _encode_file(self, file_path: Path) -> str:
        """Encode file to base64."""
        try:
            # Validate image files before encoding
            if file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.avif']:
                if not self._validate_image_file(file_path):
                    raise ValueError(f"Invalid or corrupted image file: {file_path}")
            
            with open(file_path, "rb") as file:
                return base64.b64encode(file.read()).decode('utf-8')
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {file_path}")
        except Exception as e:
            raise Exception(f"Error encoding file {file_path}: {e}")
    
    def _get_document_type(self, file_path: Path) -> str:
        """Determine document type based on file extension."""
        ext = file_path.suffix.lower()
        if ext in ['.pdf', '.pptx', '.docx']:
            return "document_url"
        elif ext in ['.png', '.jpg', '.jpeg', '.avif']:
            return "image_url"
        else:
            raise ValueError(f"Unsupported file type: {ext}")
    
    def _get_url_field_name(self, file_path: Path) -> str:
        """Get the correct URL field name based on document type."""
        doc_type = self._get_document_type(file_path)
        if doc_type == "document_url":
            return "document_url"
        elif doc_type == "image_url":
            return "image_url"
        else:
            raise ValueError(f"Unsupported document type: {doc_type}")
    
    def _get_mime_type(self, file_path: Path) -> str:
        """Get MIME type based on file extension."""
        ext = file_path.suffix.lower()
        mime_types = {
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.avif': 'image/avif',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
        return mime_types.get(ext, 'application/octet-stream')
    
    def _filter_pages_by_pattern(self, response: OCRResponse, page_pattern: Optional[str] = None) -> OCRResponse:
        """Filter OCR response pages based on pattern."""
        if not page_pattern:
            return response
        
        # Parse the page pattern
        total_pages = len(response.pages)
        selected_pages = PagePatternParser.parse_pattern(page_pattern, total_pages)
        
        # Create a new response with only selected pages
        # Note: We can't modify the original response, so we'll return the filtered pages
        # The actual filtering will be done in the markdown generation
        return response
    
    def _collect_images_map(self, response: OCRResponse, pages_to_process: list[int]) -> tuple[dict, int]:
        """Collect a mapping of image filename -> {mime, base64} from the OCR response pages."""
        images_map = {}
        total_images = 0
        for i in pages_to_process:
            page = response.pages[i]
            images = getattr(page, "images", []) or []
            total_images += len(images)
            for j, img in enumerate(images):
                # Try different attribute names for OCRImageObject
                filename = getattr(img, "filename", None) or getattr(img, "name", None) or getattr(img, "id", None)
                # According to Mistral documentation, image data is in image_base64 attribute
                b64 = getattr(img, "image_base64", None) or getattr(img, "base64", None)
                mime = getattr(img, "mime", None) or getattr(img, "content_type", None)
                # Extract base64 data from data URL if present
                if b64 and b64.startswith('data:'):
                    if ';base64,' in b64:
                        b64 = b64.split(';base64,', 1)[1]
                    else:
                        continue
                
                if not b64:
                    continue
                # Generate filename if not present
                if not filename:
                    # Use MIME type to determine extension
                    if mime and "/" in mime:
                        mime_ext = mime.split("/")[-1]
                        if mime_ext == "jpeg":
                            ext = "jpg"
                        elif mime_ext == "png":
                            ext = "png"
                        elif mime_ext == "avif":
                            ext = "avif"
                        else:
                            ext = mime_ext
                    else:
                        ext = "jpg"  # Default to jpg
                    filename = f"img-{j}.{ext}"
                if not mime:
                    if filename.lower().endswith((".jpg", ".jpeg")):
                        mime = "image/jpeg"
                    elif filename.lower().endswith(".png"):
                        mime = "image/png"
                    elif filename.lower().endswith(".avif"):
                        mime = "image/avif"
                    else:
                        mime = "image/jpeg"  # Default to jpeg
                images_map[filename] = {"mime": mime, "base64": b64}
        return images_map, total_images

    def _generate_markdown(self, response: OCRResponse, page_pattern: Optional[str] = None, 
                          include_page_headlines: bool = False) -> tuple[str, int]:
        """Generate markdown from OCR response with optional filtering and headlines."""
        if not page_pattern:
            # Process all pages
            pages_to_process = list(range(len(response.pages)))
        else:
            # Filter pages based on pattern
            total_pages = len(response.pages)
            selected_pages = PagePatternParser.parse_pattern(page_pattern, total_pages)
            pages_to_process = [i for i in range(len(response.pages)) if i + 1 in selected_pages]
        
        if not pages_to_process:
            return "No pages match the specified pattern.", 0
        
        markdown_parts = []
        for i in pages_to_process:
            page_num = i + 1  # Convert to 1-indexed
            page_content = response.pages[i].markdown
            if include_page_headlines:
                markdown_parts.append(f"### Page {page_num}\n{page_content}")
            else:
                markdown_parts.append(page_content)

        markdown_body = "\n\n".join(markdown_parts)
        # Prepend images map as an HTML comment block for OutputManager to consume
        images_map, total_images = self._collect_images_map(response, pages_to_process)
        if images_map:
            header = f"<!--IMAGES_MAP\n{json.dumps(images_map)}\n-->\n\n"
            return header + markdown_body, total_images
        return markdown_body, total_images
    
    async def process_file(self, file_path: Path, page_pattern: Optional[str] = None, 
                          include_page_headlines: bool = False) -> tuple[str, int]:
        """Process a single file and return extracted text."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Validate page pattern if provided
        if page_pattern and not PagePatternParser.validate_pattern(page_pattern):
            raise ValueError(f"Invalid page pattern: {page_pattern}")
        
        # Encode file to base64
        base64_content = self._encode_file(file_path)
        document_type = self._get_document_type(file_path)
        url_field = self._get_url_field_name(file_path)
        mime_type = self._get_mime_type(file_path)
        
        # Create data URL with base64 content
        data_url = f"data:{mime_type};base64,{base64_content}"
        
        # Process with Mistral OCR
        document_dict = {"type": document_type}
        document_dict[url_field] = data_url
        
        response: OCRResponse = self.client.ocr.process(
            model="mistral-ocr-latest",
            document=document_dict,
            include_image_base64=True
        )
        
        # Generate markdown with optional filtering and headlines
        markdown, total_images = self._generate_markdown(response, page_pattern, include_page_headlines)
        
        return markdown, total_images

    async def process_first_page(self, file_path: Path,
                                 include_page_headlines: bool = False) -> tuple[str, int]:
        """Process only first page for filename generation analysis."""
        return await self.process_file(file_path, page_pattern="1",
                                      include_page_headlines=include_page_headlines)

    async def process_files(self, file_paths: List[Path], page_pattern: Optional[str] = None,
                           include_page_headlines: bool = False) -> List[tuple[str, int]]:
        """Process multiple files and return extracted text for each."""
        results = []
        for file_path in file_paths:
            try:
                result = await self.process_file(file_path, page_pattern, include_page_headlines)
                results.append(result)
            except Exception as e:
                # Log error but continue with other files
                print(f"Error processing {file_path}: {e}")
                results.append((f"Error processing {file_path}: {e}", 0))
        return results
    
    async def process_folder(self, folder_path: Path, page_pattern: Optional[str] = None,
                            include_page_headlines: bool = False) -> List[tuple[str, int]]:
        """Process all supported files in a folder and return extracted text."""
        if not folder_path.exists():
            raise FileNotFoundError(f"Folder not found: {folder_path}")
        
        if not folder_path.is_dir():
            raise ValueError(f"Path is not a directory: {folder_path}")
        
        # Supported file extensions
        supported_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.avif', '.pptx', '.docx'}
        
        # Find all supported files
        files = [
            f for f in folder_path.iterdir() 
            if f.is_file() and f.suffix.lower() in supported_extensions
        ]
        
        return await self.process_files(files, page_pattern, include_page_headlines)
