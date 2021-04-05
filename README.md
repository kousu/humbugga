# humbugga

This is a package manager that manages pre-existing zip files and tarballs, without repacking them or adding any metadata to them.

Metadata is kept entirely in your own code.

If it is possible for you **do not use this**. Use pip or conda or nix or your language's built in package manager.

It's just that certain datasets, especially in, say, the machine learning community, are too large to handle easily with those tools,
and anyway would need extra maintenance to wrap them up in each packaging format.

By lett
There's no reason this only works with datasets, but that is what it is best suited to. It might also be good for distributing large 3d models.
This takes the opposite approach: instead of asking dataset providers.

## Limitations

Two major simplifying assumptions are:

1. Packages are isolated to a particular app.
2. Within that app each package is isolated to its own unique folder.

So unlike most linux or langauge package managers, data or code installed with humbugga cannot be reused.
(well, you could do it, but it's not meant for that you shouldn't)


## Usage

### Installing Packages

```
import humbugga
humbugga.APP = 'your-app'
humbugga.install('http://nlp.stanford.edu/data/glove.840B.300d.zip')
```

Files are downloaded to `~/.cache/your-app/humbugga` and after you've downloaded a file once you can use `sha256sum` on it:

```
$ sha256sum ~/.cache/your-app/humbugga/c0/6d/b255e65095393609f19a4cfca20bf3a71e20cc53e892aafa490347e3849f/glove.840B.300d.zip 
c06db255e65095393609f19a4cfca20bf3a71e20cc53e892aafa490347e3849f  /home/kousu/.cache/your-app/humbugga/c0/6d/b255e65095393609f19a4cfca20bf3a71e20cc53e892aafa490347e3849f/glove.840B.300d.zip 
```

and then improve the integrity of your code by adding it:

```
humbugga.install('http://nlp.stanford.edu/data/glove.840B.300d.zip', 'sha256:c06db255e65095393609f19a4cfca20bf3a71e20cc53e892aafa490347e3849f')
```



### Accessing Contents

```
fname = humbugga.path('glove.840B.300d') / "glove.840B.300d.txt"
with open(fname) as data:
    for line in data:
        print(line)
```

If you are unsure what name a package will get, you can be sure about it by:

```
pkg = humbugga.install('http://nlp.stanford.edu/data/glove.840B.300d.zip')
data = humbugga.path(pkg) / "glove.840B.300d.txt"
```

### Versioning


To upgrade a dataset or other package to a new version, upload the new copy somewhere with a new name --
 Github, https://osf.io, Dropbox will all give you unique URLs for each version of a file -- then just run `install()` with the new link.

humbugga determines an internal package name

 ... is this even necessary? i could just download datasets to a folder named by their `urlkey()`, and forget the `pkg` label entirely
then users simply say: `data = require('https://whatever.com')/"myfile.csv"` and it Just Works.

If your datasets are not packaged with consistent internal names, you can override their top-level name with `pkg=`: 

```
# install the first version of the dataset
install('https://github.com/sct-data/PAM50/releases/download/r20191029/20191029_pam50.zip', pkg='PAM50')
# .. do some computation ..
# .. time passes, grass grows ..
# update the dataset
install('https://github.com/sct-data/PAM50/releases/download/r20201104/PAM50-r20201104.zip', pkg='PAM50')
```

### Integrity Checking

```
TODO
```

## Bugs

* add more logging
* display the checksum to the user if they didn't pass it so they can add it easily
* remove the isolated-folder restriction?
* there's no file locking. there should probably be file locking.
* uses xdg so probably not windows-friendly?
  * `pip cache dir` apparently does the right thing: https://stackoverflow.com/a/48956368/2898673

* add a CLI mode so non-python apps can use it? there's no reason it needs to be python-only.
* compute `pkg` from
  * but then we *must* redownload everything all the time, don't we?
  * fg
* figure out if we need to reinstall
* make install() return path() to the package?
* rename install() to require()?
* special-cases for ? :
  - datasets with a single file (path should return the file directly)
  - non-archive datasets (again, path should return the file directly)
* automatic integrity checking
    * should probably not be on by default because if your datasets are too large for pip then they are too large to be checksummed everytime you run your app
* unpacking to the current directory for certain packages (like stata's `. net get`)
* symlinks? unpack to ~/.local/share/humbugga/$(urlkey), and symlink everything to it
    * actually what's the harm in letting apps share packages?
    * the harm is the uninstall step. hm.
    * but if we...just...never uninstall...
    * i mean the only reason it's such a pain with pip is that it needs to arrange for python's sys.path to be sane, because there's a disconnect between what you say in install_requires and what happens when you say 'import'
    * if you could just `import https://somethingfromtheweb@v4.2.2` and have it automatically just appear. you don't even need virtualenvs then, maybe.
* add some in-process caching to prevent rechecking for `remote_names`? how fast is calling install() a bunch of times in a row for the same data anyway?
 

## Related Work

* https://github.com/nltk/nltk/blob/develop/nltk/downloader.py
* something in the tensorflow scene?
* 
