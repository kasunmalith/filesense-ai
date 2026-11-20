# Security and privacy

## Data handling

FileSense AI is local-first. It reads only roots the user adds, skips symlinks, and stores metadata and extracted content under per-user app data. It does not upload document contents, perform remote image analysis, or include telemetry. Optional model downloads require a user action. Optional chat sends retrieved excerpts only to `127.0.0.1:11434`.

## Threat model

Indexed content is untrusted. The application does not execute scripts, macros, embedded objects, or document links. Previews are plain text. Chat retrieval wraps excerpts as untrusted material and validates source IDs against the retrieved set. This reduces risk but does not guarantee that a local model will follow instructions or answer correctly.

The index may contain sensitive extracted content. Protect the Windows user account and app-data directory, and clear the index from Settings when appropriate. Diagnostics and duplicate CSV exports avoid extracted document text by default; paths in an explicitly exported CSV are included because they are necessary to review file locations.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for the repository where enabled, or contact the repository maintainer through a verified private channel. Include the affected version, reproduction steps, and impact. Do not attach private indexed files.

## Known limitations

The app has no OCR, code signing, cloud backup, or formal penetration test. Malformed input can still expose parser-library defects; keep dependencies updated and index files from sources you trust.
