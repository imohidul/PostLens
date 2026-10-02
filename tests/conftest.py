"""Point PostLens at a throwaway data folder before any test imports it,
so tests never touch your real ~/.postlens (or your saved keys)."""
import os
import tempfile

os.environ["POSTLENS_HOME"] = tempfile.mkdtemp(prefix="postlens-test-")
os.environ["POSTLENS_NO_UPDATE_CHECK"] = "1"  # tests never call GitHub
