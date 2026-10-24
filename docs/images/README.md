# README screenshots

Captured from the unmodified 0.3.0 React production interface in browser mode,
connected through a loopback proxy to the real frozen Demucs 4.1.0 backend.
The native Windows capture helper was unavailable. Native dialogs and desktop
drag-and-drop are not demonstrated by these images.

The tracks are original generated demo audio. Packages were actually separated
using the verified modern CUDA runtime on an RTX 4060 Ti. No user music, mocked
API responses, fabricated progress or substituted UI text was used.

- `stemlab-library.png`: 1280 × 620. Six completed four-stem packages, each
  validated through the application's real Validate action.
- `stemlab-queue.png`: 1250 × 394. Directly captured queue region with two real
  CUDA jobs separating and one queued job, plus the normal pause/filter controls.
  This is a region capture of the rendered interface; pixels were not retouched.

The demo data, audio and runtime caches are temporary workspace build outputs
and are not committed. These PNGs document the interface, not separation quality
or a performance benchmark. Recapture when the interface materially changes.
