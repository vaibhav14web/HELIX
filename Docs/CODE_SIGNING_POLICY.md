# HELIX — Code Signing & Model Integrity Policy

> **Policy:** All packaged executable binaries must be code-signed using SHA-256 certificates, and all local AI model files must have their SHA-256 integrity hashes verified against a pinned manifest (`config/model_manifest.json`) at load time.

---

## 1. Binary Code Signing

1. **Certificate Standards**: Packaged executables (e.g., `helix.exe`, helper processes) must be signed using an Authenticode code-signing certificate with SHA-256 timestamping.
2. **Build System Command**:
   ```cmd
   signtool.exe sign /f "cert.pfx" /p "password" /fd SHA256 /tr "http://timestamp.digicert.com" /td SHA256 "dist\helix.exe"
   ```
3. **Verification**:
   ```cmd
   signtool.exe verify /pa /v "dist\helix.exe"
   ```

---

## 2. Model Source Pinning & Integrity Verification

1. **Manifest File**: `config/model_manifest.json` maps model filenames and paths to their expected SHA-256 cryptographic hashes.
2. **Load-Time Verification**:
   - `foundation.security.model_integrity.verify_model_integrity(path)` computes the model file's SHA-256 hash before loading weights into memory.
   - If the computed hash does not match the pinned hash in the manifest, a `ModelIntegrityError` is thrown immediately, preventing execution of modified or compromised model weights.
