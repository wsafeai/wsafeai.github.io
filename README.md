# WSA Site Assessment (static build)

This repository is the production static build of the WSA Site Assessment field app, published at https://wsafeai.github.io/.

The live site is a phone-friendly PWA. Assessments, photos, video, and voice notes stay in the browser on the device (IndexedDB). There is no backend and no upload.

The TypeScript source is not in this repository. It was built as a Cursor Origin draft; this repo holds the compiled `dist/` only. Changes here are patches to the built files. Merging to `main` deploys the public site.

## Local check

```bash
python3 tests/boot-recovery.py
```

That serves this folder and checks that the home screen loads, unknown routes are not a blank page, a missing assessment does not hang, and a failed first-run database setup still shows a recovery screen.
