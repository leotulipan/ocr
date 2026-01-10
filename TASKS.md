-------------------------------------------------------------------------------------------------------------------------------
## Done Tasks
-------------------------------------------------------------------------------------------------------------------------------

[x] rename the git project to OCR
[x] commit the basic project structure
[x] create the first ocr implementation
  [x] use docs\base_implementation.py and docs\basic_ocr.md as the base Mistral SDK information
  [x] implement a file, folder, files command line parameter
  [x] Use MISTRAL_API_KEY from .env
[x] make printing the page as markdown headline an optional command line parameter (default off)
[x] save the markdown at the location of the input file
[x] make sure the images as mentioned in the markdown also get downloaded and saved with the markdown
[x] cli params when doing one file to specify a pages pattern to first only extract those from the pdf and then send to ocr. use a pattern as can be done in Adobe or other apps, i.e. (1-3 or 5- or 4,5,8,10-12 etc)
[x] Implement image materialization helper:
  [x] Extract embedded base64 images from markdown and save to disk
  [x] Download linked images (HTTP/HTTPS) and save to disk
  [x] Prefix all saved image filenames with the source basename
  [x] Rewrite markdown image references to local files under `images/`
  [x] Integrate into save flow so it runs automatically on save
  [x] Count and record images in metadata
  [x] Display API image count and saved image count to stdout
[x] Build and install OCR tool globally for Windows 11
  [x] Create proper package structure for distribution
  [x] Add build configuration to pyproject.toml
  [x] Build wheel package with `uv build --wheel`
  [x] Install globally using `uv tool install dist/ocr-0.1.0-py3-none-any.whl`
  [x] Test global `ocr` command from any terminal - SUCCESS!
  [x] Create uninstall instructions using `uv tool uninstall ocr`
  [x] Document installation process in README.md
  [x] Resolve OneDrive permission issues by moving project to local directory
  [x] Update shell PATH with `uv tool update-shell`

-------------------------------------------------------------------------------------------------------------------------------
## In Progress Tasks
-------------------------------------------------------------------------------------------------------------------------------

[x] ocr --rename --dry-run => we need to show the current AND the new filename not just the new filename
[x] ocr --rename (without dry-run) does not do anything currently - VERIFIED WORKING
[ ] --confirm as well does not ask y/n for each file only for the overall folder
[ ] Start work on async with a flag --concurrent which defaults to 3 to have 3 OCR tasks running at the same time to speed up folder processing.
[ ] Add to filename prompt: Dates older than 10 years ago (e.g. 2015) are most likely DOB. Especially for medical records look for a "sample taking date" or the like and only use the date of birth if no other (current) date can be found
[ ] when running in a target folder an empty "ocr_output" is generated. remove that feature entirely

-------------------------------------------------------------------------------------------------------------------------------
## Future Tasks
-------------------------------------------------------------------------------------------------------------------------------

-------------------------------------------------------------------------------------------------------------------------------
## Implementation Plan
-------------------------------------------------------------------------------------------------------------------------------

### Global Installation Steps for Windows 11:

1. **Build the package:**
   ```bash
   uv build --wheel
   ```

2. **Install globally using uv tool:**
   ```bash
   uv tool install dist/ocr-0.1.0-py3-none-any.whl
   ```

3. **Update shell PATH:**
   ```bash
   uv tool update-shell
   ```

4. **Verify installation:**
   ```bash
   ocr --help
   ```

5. **Test from any directory:**
   ```bash
   ocr process-file --file path/to/document.pdf
   ```

### Alternative: Development Installation
For development, use:
```bash
uv pip install -e .
```

### Uninstall:
```bash
uv tool uninstall ocr
```

### Notes:
- ✅ Global installation works with `uv tool install`
- ✅ `ocr` command available from any terminal
- ✅ OneDrive permission issues resolved by using local directory
- ✅ Shell PATH automatically updated with `uv tool update-shell`
- ✅ Tool installed to `C:\Users\leona\.local\bin\ocr.exe`