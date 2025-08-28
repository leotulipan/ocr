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

-------------------------------------------------------------------------------------------------------------------------------
## In Progress Tasks
-------------------------------------------------------------------------------------------------------------------------------


-------------------------------------------------------------------------------------------------------------------------------
## Future Tasks
------------------------------------------------------------------------------------------------------------------------------



-------------------------------------------------------------------------------------------------------------------------------
## Implementation Plan
-------------------------------------------------------------------------------------------------------------------------------
