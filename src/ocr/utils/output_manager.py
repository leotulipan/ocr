"""Output manager for OCR processing results."""

import json
import re
import base64
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import urllib.request


class OutputManager:
    """Manages output files and metadata for OCR processing."""
    
    def __init__(self, output_dir: Path = None, save_at_input_location: bool = False):
        """Initialize output manager."""
        self.output_dir = output_dir or Path.cwd() / "ocr_output"
        self.save_at_input_location = save_at_input_location
        if not save_at_input_location:
            self.output_dir.mkdir(exist_ok=True)
    
    def _extract_images_from_markdown(self, markdown_content: str) -> List[Dict[str, Any]]:
        """Extract image references from markdown content."""
        images = []
        # Look for base64 image data in markdown
        base64_pattern = r'data:image/([^;]+);base64,([^"\s]+)'
        matches = re.findall(base64_pattern, markdown_content)
        
        for i, (image_type, base64_data) in enumerate(matches):
            images.append({
                'index': i,
                'type': image_type,
                'base64_data': base64_data,
                'filename': f"image_{i}.{image_type}"
            })
        
        return images
    
    def _save_images(self, images: List[Dict[str, Any]], output_dir: Path) -> List[Path]:
        """Save images to disk and return their paths."""
        image_paths = []
        for image in images:
            try:
                # Decode base64 data
                image_data = base64.b64decode(image['base64_data'])
                
                # Save image
                image_path = output_dir / image['filename']
                with open(image_path, 'wb') as f:
                    f.write(image_data)
                
                image_paths.append(image_path)
            except Exception as e:
                print(f"Error saving image {image['filename']}: {e}")
        
        return image_paths
    
    def _update_markdown_image_references(self, markdown_content: str, image_paths: List[Path], output_dir: Path) -> str:
        """Update markdown content to reference local image files instead of base64."""
        updated_content = markdown_content
        
        # Replace base64 image references with local file references
        base64_pattern = r'data:image/([^;]+);base64,([^"\s]+)'
        
        def replace_image(match):
            image_type, base64_data = match.groups()
            # Find corresponding image path
            for i, image_path in enumerate(image_paths):
                if image_path.suffix.lstrip('.') == image_type:
                    # Use relative path from output directory
                    relative_path = image_path.relative_to(output_dir)
                    return f"![image_{i}]({relative_path})"
            return match.group(0)  # Keep original if no match found
        
        updated_content = re.sub(base64_pattern, replace_image, updated_content)
        
        return updated_content
    
    def save_text_result(self, content: str, filename: str, source_file: Path = None, 
                        include_page_headlines: bool = False) -> Path:
        """Save OCR text result to file."""
        # Determine output location
        if self.save_at_input_location and source_file:
            output_dir = source_file.parent
            output_file = output_dir / f"{source_file.stem}_ocr.md"
        else:
            output_dir = self.output_dir
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = output_dir / f"{timestamp}_{filename}.md"
        
        # Create output directory if it doesn't exist
        output_dir.mkdir(exist_ok=True)
        
        # Extract and save images if present
        images = self._extract_images_from_markdown(content)
        image_paths = []
        if images:
            image_paths = self._save_images(images, output_dir)
            content = self._update_markdown_image_references(content, image_paths, output_dir)
        
        # Add metadata header
        metadata = {
            "source_file": str(source_file) if source_file else None,
            "processed_at": datetime.now().isoformat(),
            "content_length": len(content),
            "include_page_headlines": include_page_headlines,
            "images_saved": len(image_paths)
        }
        
        header = f"<!--\n{json.dumps(metadata, indent=2)}\n-->\n\n"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(header)
            f.write(content)
        
        return output_file
    
    def save_batch_results(self, results: List[str], filenames: List[str], 
                          source_files: List[Path] = None, include_page_headlines: bool = False) -> List[Path]:
        """Save multiple OCR results to files."""
        output_files = []
        for i, (content, filename) in enumerate(zip(results, filenames)):
            source_file = source_files[i] if source_files and i < len(source_files) else None
            output_file = self.save_text_result(content, filename, source_file, include_page_headlines)
            output_files.append(output_file)
        return output_files
    
    def save_metadata(self, metadata: Dict[str, Any], filename: str = "processing_metadata.json") -> Path:
        """Save processing metadata to JSON file."""
        metadata_file = self.output_dir / filename
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, default=str)
        return metadata_file
