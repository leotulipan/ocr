"""Safe file renaming utilities."""

from pathlib import Path
from typing import Tuple, Optional
from rich.console import Console
from rich.prompt import Confirm


class FileRenamer:
    """Handle safe file renaming with collision detection."""

    @staticmethod
    def resolve_collision(target_path: Path) -> Path:
        """Generate unique filename if collision exists."""
        if not target_path.exists():
            return target_path

        # Add counter suffix: filename_2.ext, filename_3.ext, etc.
        stem = target_path.stem
        suffix = target_path.suffix
        parent = target_path.parent

        counter = 2
        while True:
            new_path = parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1

            # Safety limit to prevent infinite loop
            if counter > 9999:
                raise RuntimeError(f"Could not resolve collision for {target_path}")

    @staticmethod
    def rename_file_pair(
        source_file: Path,
        new_basename: str,
        dry_run: bool = False
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Rename both original file and its OCR markdown file in .ocr subdirectory.

        Returns:
            (new_source_path, new_ocr_path) or (None, None) if dry run
        """
        # Construct new path for source file
        new_source_path = source_file.parent / f"{new_basename}{source_file.suffix}"

        # Find OCR file in .ocr subdirectory
        ocr_dir = source_file.parent / ".ocr"
        ocr_file = None
        new_ocr_path = None

        if ocr_dir.exists():
            # Check for .pg1.md first, then .md
            pg1_file = ocr_dir / f"{source_file.stem}.pg1.md"
            md_file = ocr_dir / f"{source_file.stem}.md"

            if pg1_file.exists():
                ocr_file = pg1_file
                new_ocr_path = ocr_dir / f"{new_basename}.pg1.md"
            elif md_file.exists():
                ocr_file = md_file
                new_ocr_path = ocr_dir / f"{new_basename}.md"
        else:
            # Fall back to old location for backward compatibility
            old_ocr = source_file.parent / f"{source_file.stem}_ocr.md"
            if old_ocr.exists():
                ocr_file = old_ocr
                new_ocr_path = source_file.parent / f"{new_basename}_ocr.md"

        # Resolve collisions
        new_source_path = FileRenamer.resolve_collision(new_source_path)

        # If collision was resolved, update OCR path accordingly
        if new_ocr_path and new_source_path.stem != new_basename:
            if ocr_file and ocr_file.parent == ocr_dir:
                # Update OCR path in .ocr directory
                suffix = ".pg1.md" if ocr_file.name.endswith(".pg1.md") else ".md"
                new_ocr_path = ocr_dir / f"{new_source_path.stem}{suffix}"
            else:
                # Old location
                new_ocr_path = source_file.parent / f"{new_source_path.stem}_ocr.md"

        if new_ocr_path:
            new_ocr_path = FileRenamer.resolve_collision(new_ocr_path)

        if dry_run:
            return (new_source_path, new_ocr_path)

        try:
            # Rename original file
            source_file.rename(new_source_path)

            # Rename OCR file if exists
            if ocr_file and ocr_file.exists() and new_ocr_path:
                ocr_file.rename(new_ocr_path)

            return (new_source_path, new_ocr_path)

        except Exception as e:
            # Rollback if partial rename occurred
            if new_source_path.exists() and source_file != new_source_path:
                try:
                    new_source_path.rename(source_file)
                except Exception:
                    pass  # Best effort rollback
            raise RuntimeError(f"Failed to rename files: {e}") from e

    @staticmethod
    def confirm_rename(source_file: Path, new_name: str) -> bool:
        """Prompt user for rename confirmation."""
        console = Console()
        console.print(f"\n[yellow]Proposed rename:[/yellow]")
        console.print(f"  From: [cyan]{source_file.name}[/cyan]")
        console.print(f"  To:   [green]{new_name}{source_file.suffix}[/green]")

        return Confirm.ask("Proceed with rename?", default=True)
