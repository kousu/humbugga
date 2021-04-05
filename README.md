# humbugga

This is a package manager that manages pre-existing zip files and tarballs, without repacking them, without adding any metadata to them.

It is better to use pip or conda than this if you can.
However, certain datasets, especially in, say, the machine learning community, are too large to handle easily with those tools,
and anyway would need extra maintenance.

Two major simplifying assumptions are that packages are isolated to a particular app, and that within that app each package is isolated
to its own unique folders.

## Usage

## Bugs

* Does **not** support versioning. Most datasets.
* If datasets have conflicting files, conflicts
* ensure-subdir??
* remove the isolated-folder restriction?
* there's no file locking. there should probably be file locking.
* uses xdg so probably not windows-friendly?

* add a CLI mode so non-python apps can use it? there's no reason it needs to be python-only.

## Related Work

* https://github.com/nltk/nltk/blob/develop/nltk/downloader.py
* something in the tensorflow scene?
* 
