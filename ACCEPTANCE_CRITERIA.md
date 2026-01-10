# Document Data Extraction - Acceptance Criteria

This document defines the expected extraction results for document OCR processing using AI-powered extraction.

## Extraction Approach

**Method:** Prompt-based extraction using Mistral AI's `mistral-small-latest` model

Use the cli arguments and --dry-run to test
The filenames should not be marked as Amazon

## Test Files

### 1. Heunisch.pdf 
Restaurant receipt from HEUNISCH 

**Expected Filename (fuzzy):**
2022-10-24 - HEUNISCH + FREBEN - Gastrorechnung.pdf
or similiar

**Key Test:** Iso Date correctly extracted, Company Name extracted, Rechnung/Invoice or similiar text added

---

### 2. Kolarik.pdf 
Restaurant invoice from Kolariks Freizeitbetriebe GmbH

**Expected Filename (fuzzy):**
2022-10-21 - Kolarik - Restaurant.pdf
or similiar

**Actual Result:** ✅ PASS (all fields match)

**Key Test:** Iso Date correctly extracted, Company Name extracted, Rechnung/Invoice or similiar text added

---

---

### 3. Magazine-Scan.pdf
Magazine page with embedded images, text column, and data table

**Command:**
```bash
ocr ocr_test/Magazine-Scan.pdf --pages "1" --image-descriptions
```

**Expected Output:**
- Proper markdown with text content and formatted data table
- 5-6 embedded images extracted and materialized
- AI-generated descriptions for each image:
  1. **Image 1**: Two people sitting (Dr Fritsch and Mirjam Weichselbraun) - description mentions two people on tree stump in forest
  2. **Image 2**: Person with farmer and cow - description mentions young woman on rock with man and cow behind
  3. **Image 3**: Nivea Men products (or euro banknotes if present) - description mentions products or currency
  4. **Image 4**: Alvaro Alonso headshot - description mentions man with dark hair and beard
  5. **Image 5**: Iglo Ideenküche ad - description mentions vegetables, iglo brand, and IDEENKüCHE text

**Key Test:**
- Table extracted as proper markdown table format
- Image descriptions added after each image reference with "**Image Description:**" prefix
- Descriptions provide meaningful context about image content
- Images saved to `.ocr/images/` directory with local references

---

### 4. Concatenate Multiple Files (Heunisch.pdf + Kolarik.pdf)
Concatenate multiple document files into one output treating each as a page

**Command:**
```bash
ocr ocr_test/Heunisch.pdf ocr_test/Kolarik.pdf --concat
```

**Expected Output:**
- One combined markdown file: `Heunisch_combined.md` in `.ocr/` directory
- Page headers added: "### Page 1", "### Page 2"
- All images from both files extracted with unique prefixes (page1_1.jpg, page2_1.jpg)
- Image descriptions included for all images
- Metadata shows both source files and original filenames

**Key Test:**
- Files concatenated in order specified
- Each page retains its complete content (text, tables, images)
- Images saved sequentially without naming conflicts
- Output saved in `.ocr/` subdirectory of first file's location

---

### 5. Filename-Based Metadata Extraction
Test file with informative filename that should be used for extraction

**Test File:** `ocr_test/2020-10-01 Meldezettel Sompek Strasse.pdf`

**Current Behavior (v0.6.0):**
- Low confidence (~0.3) extraction from document content alone
- Misses valuable information already in filename

**Expected Behavior (v0.7.0+):**
- Filename treated as HIGH PRIORITY source for metadata
- ISO date extracted from filename: `2020-10-01`
- Location/Company extracted: `Sompek Strasse`
- Document type extracted: `Meldezettel`
- High confidence (0.8-0.9) due to filename providing clear structure

**Expected Filename (fuzzy):**
```
2020-10-01 - Sompek Strasse - Meldezettel.pdf
```

**Command:**
```bash
ocr ocr_test/2020-10-01\ Meldezettel\ Sompek\ Strasse.pdf --rename --dry-run
```

**Key Test:**
- Current filename is passed to Mistral AI for analysis
- Filename metadata ranks higher than document content for structured info
- Confidence threshold default is 0.7 (can be changed with `--confidence`)
- Output shows: `2020-10-01 - Sompek Strasse - Meldezettel (Confidence: 0.9)`

---

### 6. Concatenate Image Files (IMG_0466.JPG + IMG_0468.JPG)
Concatenate multiple image files into one output treating each as a page

**Command:**
```bash
ocr ocr_test/IMG_0466.JPG ocr_test/IMG_0468.JPG --concat
```

**Expected Output:**
- One combined markdown file: `IMG_0466.md` saved in `ocr_test/` directory (NOT in `.ocr/`)
- Individual cached OCR files saved: `ocr_test/.ocr/IMG_0466.pg1.md` and `ocr_test/.ocr/IMG_0468.pg1.md`
- Page headers added: "### Page 1", "### Page 2"
- No images directory created if no images extracted
- Metadata shows both source files and original filenames
- YAML frontmatter includes `images_saved: 0` and `include_page_headlines: true`

**Key Test:**
- Files concatenated in order specified
- Individual OCR files preserved for caching (prevents re-OCR on subsequent runs)
- Combined file saved in parent directory (not in `.ocr/` subdirectory)
- Empty `.ocr/images/` directory not created when no images exist
- Default filename is first file's stem with `.md` extension

---

## Output Format Tests

### Dry-Run Output Shows Current and New Filename

**Test:**
```bash
ocr ocr_test/Heunisch.pdf --rename --dry-run
```

**Expected Output (Simple Mode):**
```
Heunisch.pdf -> 2022-10-24 - HEUNISCH & FREUN - Rechnung.pdf (Confidence: 0.9)
```

**Expected Output (Verbose Mode):**
```bash
ocr ocr_test/Heunisch.pdf --rename --dry-run --verbose
```
```
Filename generation mode enabled
Using cached filename: 2022-10-24 - HEUNISCH & FREUN - Rechnung

DRY RUN - No files will be renamed
Current: Heunisch.pdf
New: 2022-10-24 - HEUNISCH & FREUN - Rechnung.pdf
Confidence: 0.9
```

**Key Test:**
- Shows both current filename AND suggested new filename
- Simple mode: `current.pdf -> new.pdf (Confidence: X.X)`
- Verbose mode: Separate lines for Current, New, and Confidence
- Batch mode shows all files with same format

---

## Testing Commands

```bash
# Dry Run file rename (simple output)
ocr --rename --dry-run {filename}

# Dry Run file rename with verbose output
ocr --rename --dry-run --verbose {filename}

# Dry Run file rename, force re-ocr
ocr --rename --dry-run --force {filename}

# Set custom confidence threshold (default: 0.7)
ocr --rename --dry-run --confidence 0.8 {filename}

# Batch processing with simple output
ocr *.pdf --rename --dry-run

# Batch processing with verbose output
ocr *.pdf --rename --dry-run --verbose

# OCR with image descriptions (default: enabled)
ocr {filename}

# Disable image descriptions
ocr {filename} --no-image-descriptions

# Concatenate multiple files into one document
ocr file1.pdf file2.pdf file3.pdf --concat

# Concatenate with custom output location
ocr page1.jpg page2.jpg page3.jpg --concat --output combined.md

# Concatenate with intelligent filename generation
ocr file1.pdf file2.pdf --concat --rename
```
