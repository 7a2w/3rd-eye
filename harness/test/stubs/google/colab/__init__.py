"""Test stand-in for google.colab so the notebook can run outside Colab.

files.upload() hands back files listed in TE_UPLOADS (os.pathsep separated, one batch per call, batches split by ';;').
userdata.get() reads TE_SECRET_<NAME>.
output.eval_js() returns a base64 recording from TE_MIC_FILE.
"""
