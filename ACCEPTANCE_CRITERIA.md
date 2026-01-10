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

## Testing Commands

```bash
# Dry Run file rename
ocr --rename --dry-run {filename}

# Dry Run file rename, force re-ocr
ocr --rename --dry-run --force {filename}

# OCR with image descriptions (default: enabled)
ocr {filename}

# Disable image descriptions
ocr {filename} --no-image-descriptions

# Concatenate multiple files into one document
ocr file1.pdf file2.pdf file3.pdf --concat

# Concatenate with custom output location
ocr page1.jpg page2.jpg page3.jpg --concat --output combined.md
```
