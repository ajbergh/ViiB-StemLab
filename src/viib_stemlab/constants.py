SCHEMA_VERSION = 1
PACKAGE_SUFFIX = ".viibstems"
GENERATOR_NAME = "ViiB-StemLab"
DEFAULT_MODEL = "htdemucs_ft"
CANONICAL_STEMS = ("vocals", "drums", "bass", "other")
SUPPORTED_INPUT_EXTENSIONS = (".wav", ".flac", ".mp3", ".ogg")

# ViiB Stem Package v1 layouts (docs/VIIB_STEM_PACKAGE_V1.md). StemLab writes
# the four-stem layout by default; readers accept both.
LAYOUT_STEMS = {
    "four": CANONICAL_STEMS,
    "six": ("vocals", "drums", "bass", "guitar", "piano", "other"),
}
STEM_LAYOUT = "four"

# Compressed stems require the compressed-stems-v1 reader capability.
SUPPORTED_STEM_EXTENSIONS = (".wav", ".wave", ".ogg", ".mp3")
COMPRESSED_STEMS_FEATURE = "compressed-stems-v1"
SUPPORTED_STEM_ENCODINGS = ("pcm_s16le", "float32le", "vorbis", "mp3")
