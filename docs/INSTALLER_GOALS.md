# Full and on-demand installers

- [x] Full Windows installer includes CPU runtime, decoders, model weights and offline WebView2 setup.
- [x] On-demand installer includes the native UI and bootstraps a verified runtime/tools/model payload without requiring Python.
- [x] First-run setup provides progress, cancellation, retry and safe offline reuse.
- [x] Both variants share model cache, settings, queue and optional CUDA acceleration.
- [x] Build scripts produce distinguishable installers and checksums plus downloadable payload assets.
- [x] Validate core bootstrap behavior, frontend, Python, native builds and both installer artifacts; record remaining publication/clean-machine gates.
- [ ] Publish release assets and perform clean-machine install/upgrade/uninstall and signing checks.
