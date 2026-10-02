# Current-state audit

Date: 2026-10-01

## What is reusable

- The React/TypeScript client already has a working upload interaction, video preview, analysis result state, and coaching chat.
- The Node service has Replicate orchestration for image-based and pose-based coaching flows.
- The repository already includes FFmpeg dependencies and understands the concept of sampling frames before inference.
- Existing coaching functionality can remain available while infrastructure is introduced alongside it.

## Confirmed technical debt

1. `server/index.js` does not extract frames. It writes five identical 1×1 PNG placeholders and submits those files to inference.
2. Upload, frame handling, model inference, response creation, and cleanup share one synchronous HTTP lifecycle.
3. The browser calls `/api/analyze-pose`, while the README documents `/api/upload`; the public API contract is inconsistent.
4. Videos, frames, processing jobs, model versions, and annotations are not persisted.
5. Upload filtering in the legacy server accepts every file type despite claiming to validate videos.
6. The production-oriented path assumes Vercel serverless constraints, which conflict with long-running video/ML work.
7. There were no automated tests or integration fixtures at the start of this milestone.
8. The frontend and backend contain deployment-trigger and debug logging that should not remain in a production service.
9. The current npm dependency trees report known vulnerabilities and use deprecated packages, including Multer 1 and `fluent-ffmpeg`. Dependency modernization should be handled as a separate, tested change.

## Migration decision

Keep the coaching product intact for now. Introduce a Python media service and worker beside it, then route future annotation and model-assisted labeling features through the persisted `videos` and `frames` abstraction.

This avoids a high-risk rewrite and creates an independently demonstrable infrastructure slice. Once annotation workflows use the new service, the placeholder path in the Node backend can be retired instead of patched into a second job system.

