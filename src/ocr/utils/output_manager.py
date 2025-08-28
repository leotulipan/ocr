"""Output manager for OCR processing results."""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


class OutputManager:
    """Manages output files and metadata for OCR processing."""
    
    def __init__(self, output_dir: Path = None):
        """Initialize output manager."""
        self.output_dir = output_dir or Path.cwd() / "ocr_output"
        self.output_dir.mkdir(exist_ok=True)
    
    def save_text_result(self, content: str, filename: str, source_file: Path = None) -> Path:
        """Save OCR text result to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"{timestamp}_{filename}.md"
        
        # Add metadata header
        metadata = {
            "source_file": str(source_file) if source_file else None,
            "processed_at": datetime.now().isoformat(),
            "content_length": len(content)
        }
        
        header = f"<!--\n{json.dumps(metadata, indent=2)}\n-->\n\n"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(header)
            f.write(content)
        
        return output_file
    
    def save_batch_results(self, results: List[str], filenames: List[str], 
                          source_files: List[Path] = None) -> List[Path]:
        """Save multiple OCR results to files."""
        output_files = []
        for i, (content, filename) in enumerate(zip(results, filenames)):
            source_file = source_files[i] if source_files and i < len(source_files) else None
            output_file = self.save_text_result(content, filename, source_file)
            output_files.append(output_file)
        return output_files
    
    def save_metadata(self, metadata: Dict[str, Any], filename: str = "processing_metadata.json") -> Path:
        """Save processing metadata to JSON file."""
        metadata_file = self.output_dir / filename
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, default=str)
        return metadata_file
