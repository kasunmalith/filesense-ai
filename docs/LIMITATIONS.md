# Limitations

- Scanned/image-only PDF pages are detected but OCR is not implemented.
- Supported text formats are PDF, DOCX, TXT, Markdown, CSV, LOG, and optional XLSX. Legacy `.doc`, RTF, email archives, archives, code execution, and OCR are not indexed.
- MiniLM is an English-oriented embedding model. Sinhala and Tamil display is supported by Qt, but semantic accuracy for those languages is not promised.
- CLIP results are approximate and may miss objects, context, or unusual image content. Image vectors require the optional model and CPU time.
- The semantic vector scan is suitable for moderate collections and can become slow on very large chunk counts. No FAISS acceleration is currently bundled.
- Indexing is manual by default. Permission failures and corrupt files are reported per scan; locked files may need a later retry.
- Duplicate similarity uses perceptual hash suggestions; it can group visually similar but distinct images or miss changed versions. Cleanup is review-only.
- Ollama must be installed and running locally with a model. Answers can be wrong even when citations are present. Retrieved passages are untrusted and prompt-injection defenses are not a formal guarantee.
- There is no cloud sync, backup, OCR, code signing, or automatic update service.
- The local core onedir executable was built and smoke-launched on Windows. The optional MiniLM and OpenCLIP dependencies and model weights were not included in that local build. The AI-inclusive GitHub Actions workflow has not been run, and the app is unsigned.
