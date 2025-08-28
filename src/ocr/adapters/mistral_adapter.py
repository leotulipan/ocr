"""Mistral AI adapter for OCR processing."""

import base64
from pathlib import Path
from typing import List, Optional, Set
from mistralai import Mistral, OCRResponse

from ..protocols.ocr_service import OCRService
from ..models.settings import Settings
from ..utils.page_parser import PagePatternParser


class MistralOCRAdapter(OCRService):
    """Mistral AI OCR service adapter."""
    
    def __init__(self, settings: Settings):
        """Initialize the Mistral OCR adapter."""
        self.client = Mistral(api_key=settings.mistral_api_key.get_secret_value())
        self.settings = settings
    
    def _encode_file(self, file_path: Path) -> str:
        """Encode file to base64."""
        try:
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
    
    def _generate_markdown(self, response: OCRResponse, page_pattern: Optional[str] = None, 
                          include_page_headlines: bool = False) -> str:
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
            return "No pages match the specified pattern."
        
        markdown_parts = []
        for i in pages_to_process:
            page_num = i + 1  # Convert to 1-indexed
            page_content = response.pages[i].markdown
            
            if include_page_headlines:
                markdown_parts.append(f"### Page {page_num}\n{page_content}")
            else:
                markdown_parts.append(page_content)
        
        return "\n\n".join(markdown_parts)
    
    async def process_file(self, file_path: Path, page_pattern: Optional[str] = None, 
                          include_page_headlines: bool = False) -> str:
        """Process a single file and return extracted text."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Validate page pattern if provided
        if page_pattern and not PagePatternParser.validate_pattern(page_pattern):
            raise ValueError(f"Invalid page pattern: {page_pattern}")
        
        # Encode file to base64
        base64_content = self._encode_file(file_path)
        document_type = self._get_document_type(file_path)
        mime_type = self._get_mime_type(file_path)
        
        # Create document URL with base64 content
        document_url = f"data:{mime_type};base64,{base64_content}"
        
        # Process with Mistral OCR
        response: OCRResponse = self.client.ocr.process(
            model="mistral-ocr-latest",
            document={
                "type": document_type,
                "document_url": document_url,
            },
            include_image_base64=True
        )
        
        # Generate markdown with optional filtering and headlines
        markdown = self._generate_markdown(response, page_pattern, include_page_headlines)
        
        return markdown
    
    async def process_files(self, file_paths: List[Path], page_pattern: Optional[str] = None,
                           include_page_headlines: bool = False) -> List[str]:
        """Process multiple files and return extracted text for each."""
        results = []
        for file_path in file_paths:
            try:
                result = await self.process_file(file_path, page_pattern, include_page_headlines)
                results.append(result)
            except Exception as e:
                # Log error but continue with other files
                print(f"Error processing {file_path}: {e}")
                results.append(f"Error processing {file_path}: {e}")
        return results
    
    async def process_folder(self, folder_path: Path, page_pattern: Optional[str] = None,
                            include_page_headlines: bool = False) -> List[str]:
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
