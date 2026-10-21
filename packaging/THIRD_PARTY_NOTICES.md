# StemLab runtime notices

The desktop distribution includes Python, Demucs, PyTorch, torchaudio, SoundFile/libsndfile, their dependencies, and FFmpeg/FFprobe. License texts discovered in installed Python distribution metadata are copied beside this file. `python-environment.json` records the build environment inventory; it is a superset of bundled components, not a legal determination.

`DECODER_NOTICES.txt` must accompany the exact decoder binaries used for the build, including their license, build configuration, upstream source location, and applicable source-offer information. FFmpeg licensing depends on enabled codecs and build flags. Review redistribution obligations for the selected binaries before publishing installers.

The Full installer bundles verified htdemucs_6s model weights. The On-demand installer downloads the CPU runtime, decoders and weights during setup. See MODEL_NOTICES.md in the processing payload for checkpoint provenance. Demucs model source and license information: https://github.com/facebookresearch/demucs and https://github.com/facebookresearch/demucs/blob/main/LICENSE . Keep applicable model notices with any offline weight distribution.

Tauri/Rust and frontend dependency inventories are generated separately by the desktop CI. Before a public release, review the complete inventory, include required notices for transitive/native libraries, and resolve any missing license metadata. Automatic inventory collection does not replace that review.
