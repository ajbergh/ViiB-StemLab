SCHEMA_VERSION = 1
PACKAGE_SUFFIX = ".viibstems"
GENERATOR_NAME = "ViiB-StemLab"
DEFAULT_MODEL = "htdemucs_6s"
CANONICAL_STEMS = ("vocals", "drums", "bass", "guitar", "piano", "other")
SUPPORTED_INPUT_EXTENSIONS = (".wav", ".flac", ".mp3", ".ogg")

# ViiB Stem Package v1 layouts (docs/VIIB_STEM_PACKAGE_V1.md). StemLab writes
# the six-stem layout; readers accept both.
LAYOUT_STEMS = {
    "four": ("vocals", "drums", "bass", "other"),
    "six": CANONICAL_STEMS,
}
STEM_LAYOUT = "six"

# v1 stem files are WAV PCM16 or IEEE float32, mono or stereo.
SUPPORTED_STEM_EXTENSIONS = (".wav", ".wave")
SUPPORTED_STEM_ENCODINGS = ("pcm_s16le", "float32le")
