

import importlib.resources

import pathlib, os.path
from string import hexdigits
from urllib.parse import urlparse
import hashlib
import tarfile, zipfile, tempfile, shutil
import warnings

import xdg.BaseDirectory
import requests
from tqdm import tqdm


def cgi_parse_header(line):
    """
    python's cgi.parse_header() is buggy. This is a correct-to-the-spec reimplementation of it.
    """
    
    def istoken(s):
        # https://tools.ietf.org/html/rfc2616#section-2.2
        return all(c.isalnum() or c in ['-', '`', '^', "'", '+', '$', '!', '*', '|', '%', '~', '#', '.', '&', '_'] for c in s)

    def istext(s):
        # I'm sort of confused by this definition
        # TEXT           = <any OCTET except CTLs, but including LWS>
        #  but it 
        #        LWS            = [CRLF] 1*( SP | HT )
        # so it's not text if the CR and the LF come independently?
        # 
        return all(c.isprintable() or c in ['\n', '\r', '\t'])


    def parse_value(s):
        """
        https://tools.ietf.org/html/rfc2616#section-3.6

       parameter               = attribute "=" value
      attribute               = token
         value                   = token | quoted-string
         returns: value, rest
         quoted strings are returned de-quoted.
        """
        if s[0] == '"':
            return parse_quotedstring(s)
        else:
            return parse_token(s)

    def parse_token(s):
        """

               token          = 1*<any CHAR except CTLs or separators>
                      separators     = "(" | ")" | "<" | ">" | "@"
                                            | "," | ";" | ":" | "\" | <">
                                                                  | "/" | "[" | "]" | "?" | "="
                                                                                        | "{" | "}" | SP | HT
        returns: token, rest
        """
        i=0
        while i<len(s) and istoken(s[i]):
            i+=1
        if i==0:
            # tokens are at least one character long
            raise ValueError(f"Not a token: {s}")
        return s[:i], s[i:]

    def parse_quotedstring(s):
        # https://tools.ietf.org/html/rfc2616#section-2.2
        """
        A string of text is parsed as a single word if it is quoted using
        double-quote marks.
        quoted-string  = ( <"> *(qdtext | quoted-pair ) <"> )
        qdtext         = <any TEXT except <">>

          The backslash character ("\") MAY be used as a single-character
              quoting mechanism only within quoted-string and comment constructs.

                                 quoted-pair    = "\" CHAR
                                 """
        i = 0
        if s[i] == '"':                                    
            i+=1
        else:
            raise ValueError("Not a quoted string")
        while s[i:]:
            if s[i] == '\\':
                # backslashes quote the following characters
                # maybe we want .decode('string_escape') here?
                print(f"skipping |{s[i:i+2]}|")
                i+=2
            elif s[i] == '"':
                i+=1
                break
            else:
                i+=1
        else:
            raise ValueError("Unterminated quoted string")

        value = s[1:i-1]
        #value = value.decode('string_escape') # from python2, no longer in python3
        # also the escaping rules are different for HTTP: a \ quotes ANY char to its literal value; in C-style \-quoting, \n, \r, etc are special, and we don't want that here.
            # is another way to think of this:
            # - drop all \s except those that are themselves preceeded by a \?
            # because that's the goal, right?
        value = ''.join([value[i] for i,_ in enumerate(value) if value[i] != '\\' or (i>0 and value[i-1] == '\\')]) # XXX is this correct? this is the sketchiest part of this code.
        return value, s[i:]


    # > Note that due to the rules for implied linear whitespace (Section 2.1
    # > of [RFC2616]), OPTIONAL whitespace can appear between words (token or
    # > quoted-string) and separator characters.
    # which means we have to call .lstrip() after every new value for line

    # 

    # special case: the *first* param isn't like the others. Maybe you can think of it as being implicitly prefixed by 'type='
    type, line = parse_token(line)
    line = line.lstrip()

    def params():
        nonlocal line
        while line and line[0] == ";":
            line = line[1:]
            line=line.lstrip()

            param, line = parse_token(line)
            line = line.lstrip()

            if line[0] == '=':
                line = line[1:]
                line.lstrip()
            else:
                raise ValueError(f"Param {param} missing =")

            # then either: a token, or a quoted string
            if line[0] == '"':
                value, line = parse_quotedstring(line)
            else:
                value, line = parse_token(line)
            print(param, value, line)
            line = line.lstrip()

            param = param.lower() # case insensitive
            yield param, value
        if line:
            raise ValueError(f"Invalid HTTP header parameters: {line}")

    type = type.lower() # case insensitive
    return type, dict(params())

import cgi
cgi.parse_header = cgi_parse_header


def tokenize_content_disp(disp):
    """
    Parse a HTTP Content-Disposition header into its parts.
    
    Returns a sequence of pairs [(param, value), ...].
    As a special case, the disposition type is returned as the first one as ("type", type)

    Bugs: doesn't handle UTF-9 properly.
    
    Bugs: this should be part of python-requests.


    # ahhhh this is cgi.parse_header()
    """
    # https://tools.ietf.org/html/rfc6266#section-4.1

    # TODO: handle UTF-8 and other encodings: https://tools.ietf.org/html/rfc5987
    

    def istoken(c):
        # https://tools.ietf.org/html/rfc2616#section-2.2
        return c.isalnum() or c in ['-', '`', '^', "'", '+', '$', '!', '*', '|', '%', '~', '#', '.', '&', '_']
    
    i,j=0,0

    # special case: the first token doesn't have an '=' in it
    while j<len(disp) and istoken(disp[j]): j+=1
    type = disp[i:j].lower() # case-insensitive
    yield ("type", type)
    
    i=j

    while j<len(disp):
        # parse a disposition-param

        if disp[j] != ";":
            raise ValueError(f"Invalid Content-Disposition header: leftover {repr(disp[i:])}")
        else:
            j+=1 # step past the 
        while j<len(disp) and not istoken(disp[j]): j+=1 # find the start of the next token
        i=j

        while j<len(disp) and istoken(disp[j]): j+=1
        param = disp[i:j]
        i=j
        if param == "type":
            raise ValueError(f"Invalid Content-Disposition header: invalid parameter {param}")

        if disp[j] != "=":
            raise ValueError(f"Invalid Content-Disposition header: leftover {repr(disp[i:])}")
        else:
            j+=1
            i=j
        
        if istoken(disp[j]):
            # it must be a token
            while j<len(disp) and istoken(disp[j]): j+=1
            value = disp[i:j]
        elif disp[j] == '"':
            # a quoted string
            j+=1
            i=j
            while j<len(disp):
                if disp[j] == "\\":
                    j+=2
                    continue
                if disp[j] == '"': break
                j+=1
            else:
                raise ValueError(f"Invalid Content-Disposition header: leftover {repr(disp[i:])}")
            value = disp[i:j]
            j+=1
            i=j
        else:
            raise ValueError("Invalid Content-Disposition header: 3")
        i=j

        yield param, value
    

        # there's some special handling we need here for UTF-8
        # but I don't know how that interacts with python, since headers are already all strings anyway?        

#print(dict(tokenize_content_disp('attachment; filename=PAM50-r20201104.zip')))
#print(dict(tokenize_content_disp('attachment; filename="PAM50-r20201104.zip"; filename*="lol"')))
#print(dict(tokenize_content_disp('babelfish; filename="PAM50-r20201104.zip"; filename*="lol"')))
#print(dict(tokenize_content_disp('babelfish; filename="PAM50-r20201104.zip"; filename*=lol"')))
#print(dict(tokenize_content_disp('babelfish; filename="PAM50-r20201104.zip"; filename*="lol')))
#raise SystemExit(0)


def tokenize_content_range(resp_range):
    # TODO: pull this to tokenize_content_range()
    range_unit, resp_range = resp_range.split(" ", 1)
    range_region, range_size = resp_range.split("/",1)
    if range_region == "*":
       range_region = None # "unknown"
    else:
        range_region = [int(e) for e in range_region.split("-")] # NB: this is a python-style range

    if range_size == "*":
        range_size = None
    else:
        range_size = int(range_size)

    if range_unit != "bytes":
        raise ValueError("Unsupported Content-Range unit: {range_unit}") # TODO: should this be up a level?
    if range_size is None and range_region is None:
        raise ValueError("Both Content-Range:'s region and size are unknown. This is supposed to be disallowed.")

    # integrity check
    if range_size is not None and range_region is not None:
        if not (range_region[1] == range_size - 1):
            raise ValueError(f"Inconsistent Content-Range: region={range_region} vs size={range_size}")
            # TODO: in theory we can handle the case where the server wants to send us a partial region and not the whole region
            # butttt that's hard.

    return range_unit, range_region, range_size


def sanitize_path(path):
    """
    Sanitize a path against directory traversals
    """
    # https://stackoverflow.com/questions/13939120/sanitizing-a-file-path-in-python ?? -> none of these seem quite right
    # this one works by:
    # - pretending to chroot to the current directory
    # - cancelling all redundant paths (/.. = /)
    # - making the path relative
    return os.path.relpath(os.path.normpath(pathlib.Path("/")/path), "/")


def resp_attachment_filename(resp):
    # get response filename 
    # i.e. behave like curl -OJ
    #

    if v := resp.headers.get('Content-Disposition'):
        print(v)
        import time; time.sleep(1)
        print()
        type, params = cgi.parse_header(v)
        if type == "attachment":
            if 'filename' in params:
                params['filename'] = os.path.basename(sanitize_path(params['filename']))
                return params['filename']
            # XXX what about filename*=UTF-8 ??


def download(url, path, remote_filenames=False, progress=True, overwrite='skip'):
    """
    Download the file from url to folder path

    Supports HTTP resuming and a progress bar.
    """

    
    path = pathlib.Path(path)

    # make an HEAD request in order to figure out the filename the server wants to use
    # this is like curl -O
    # TODO: make this optional? we can just extract it from the input url
    filename = None
    if remote_filenames:
        with requests.head(url, allow_redirects=True) as resp:
            resp.raise_for_status()
            filename = resp_attachment_filename(resp)
    if filename is None:
        # if the remote server
        filename = os.path.basename(urlparse(url).path)


    # we download to .part, and only move it to the real name when it's finished
    target_file = (path/filename)
    partial_file = pathlib.Path(str(path/filename)+(".part"))

    if os.path.exists(target_file):
        if overwrite == True:
            pass
        if overwrite == 'skip':
            return target_file
        elif overwrite == False:
            raise ValueError(f"File exists: {target_file}. Pass overwrite=True to redownload, or overwrite='skip' to ignore this.") # IOError? or something?
        else:
            raise ValueError(f"Invalid parameter: overwrite={overwrite}")

    os.makedirs(path, exist_ok=True)
    with open(partial_file, "ab") as f:
        if f.tell() > 0:
            # resumption: https://stackoverflow.com/a/22894873/2898673
            headers = {'Range': f'bytes={f.tell():d}-'}
        else:
            headers = {}

        with requests.get(url, headers=headers, stream=True) as resp:
            range_size = None

            if (resp_range := resp.headers.get('Content-Range', None)) is not None:
                _, range_region, range_size = tokenize_content_range(resp_range)
            elif (range_size := resp.headers.get('Content-Length', None)) is not None:
                # server doesn't support Range: or we didn't ask for it, so fall back on Content-Length
                if f.tell() > 0:
                    warnings.warn(f"{urlparse(resp.url).netloc} doesn't support byte ranges. Cannot resume.")
                    f.truncate(0) # and erase any previous work

                range_size = int(range_size)
                range_region = 0, range_size-1
            else:
                # we have no idea how much we're downloading
                range_region = None

            if range_region is not None and range_region[0] != f.tell():
                # a malicious server could be trying to get us to write somewhere we're not expecting
                # or    
                # XXX this error is can be misleading: if a server responds with Content-Range when we didn't *ask* for it
                #     in that case, this will read 'we requested 0- but the server tried to write to (N,M)'
                raise ValueError(f"Range mismatch: we requested {f.tell()}- but the server tried to write to {range_region}")

            with tqdm(
                desc=filename,
                unit="B",
                unit_scale=True,
                unit_divisor=1024, # why is 1024 the right number here??
                initial=range_region[0] if range_region else 0,
                total=range_size,
                disable=not progress,
            ) as bar:
                for chunk in resp.iter_content(chunk_size=(2<<12)):
                    size=f.write(chunk)
                    bar.update(size) # tqdm doesn't count bytes right unless via .update()

        # 
        if os.stat(partial_file).st_size == range_size or range_size is None:
            os.rename(partial_file, target_file)


    return target_file


# This file is gigabytes large, too large to include directly in the package.
# track https://github.com/pypa/warehouse/issues/7852 for better ideas.
#download('http://www.nltk.org/images/authors.png', '.')
download('https://www.dropbox.com/s/pwokjjnrexg0zl6/cohenadad_cv__20190424.pdf?dl=1', '.')
 # sha256:4a3bdc0e81e30be9e91603bf4395e1dc17beb469c33dc563795391f382a1904b
download('https://github.com/sct-data/PAM50/releases/download/r20201104/PAM50-r20201104.zip', '.')


def unpack(archive, path):
    formats = {'.zip': zipfile.ZipFile,
               '.tar.gz': tarfile.open,
               '.tgz': tarfile.open,
               '.tar.xz': tarfile.open,
               '.tar.bz2': tarfile.open}
    _, format = os.path.splitext(archive)
    # TODO: https://docs.python.org/3/library/shutil.html#shutil.unpack_archive
    
    try:
        format = formats[format]
    except KeyError:
        raise ValueError(f"Unsupported archive format: {format}")

    with format(archive) as archive:
        archive.extractall(path)

# ---------------

APP = None

if APP is None:
    warnings.warn("You should set humbugga.APP = 'your-app-name'; or, set humbugga.APP = '_auto' to take the app name from how it is called by the OS (sys.argv[0]).")
if APP == '_auto':
    import sys
    APP = sys.argv[0]


def install(url, checksum=None, pkg=None):
    """
    

    
    """

    # TODO:
    # - if given pkg= then we can support versioning:
    # - check metadata/"pkg"/pkg/source; is it the same as URL? if not, download the new one
    #   - probably wanna be careful to not *uninstall* the old one until the new one is downloaded and checksummed

    # 1. Check if url is already installed. If so, skip.
    # 2. If not, download it
    #   -> check the *cache* first, and check for partially downloaded files too.
    #   -> there 
    #  downloading means:
    #  1. do
    #  2. check the checksum
    #  
    # why is the flow so tangly here?
    # download:
    # -> if the file doesn't exist in the cache, call download()
        # -> difficult case: there's more than one cache to check
    # -> assert the file does exist in the cache now (or else download() gave an exception)
    # -> check its checksum (if bad give an exception)
       # -> if no checksum: assume good?
    # 
    # 3. unpack and install
    # -> 
    # -> write to the database
    #   -> catch: there's more than one database to check

    # how do I know if I file is installed from its URL?
    # -> by looking in the database for something marked from this specific URL

    # the error messages could be better

    # 

    # argument parsing
    # TODO: validate url? or should we just leave that up to requests?
    if checksum is not None:
        if ':' not in checksum:
            raise ValueError(f"Invalid checksum: missing 'algorithm:' specifier: '{checksum}'")
        
        algorithm, checksum = checksum.split(":", 1)
        try:
            algorithm = getattr(hashlib, algorithm) # ...?hackable?
        except AttributeError:
            raise ValueError(f"Invalid checksum: unknown algorithm {algorithm}")

        if not (len(checksum) == len(algorithm().hexdigest()) and all(c in hexdigits for c in checksum)):
            raise ValueError(f"Invalid checksum: incorrect checksum format for '{algorithm}': {C}. I")

        checksum = checksum.lower() # case-insensitive

    # skip if installed
    if (pkg is not None and installed(pkg)) or (pkg is None and installed(url)):
        if _get(pkg or url)['source'] == url:
            warnings.warn(f"{url} already installed.")
            return

    # set up the cache
    cache = xdg.BaseDirectory.save_cache_path(os.path.join(APP,'humbugga')) # TODO: add /var/lib/$APP or /var/cache to the cache paths, and use it if we have write access to it
    encoded_url = urlkey(url)
    subcache = encoded_url
    subcache = os.path.join(subcache[:2], subcache[2:4], subcache[4:])
    cache = os.path.join(cache, subcache)
    os.makedirs(subcache, exist_ok=True)

    # download the package to the cache
    file = download(url, cache)

    if checksum is not None:
        C = algorithm() # initialize the checksum algorithm
        with open(file,'rb') as f:
            print("checksumming",file) # DEBUG
            while buf := f.read(2<<12):
                C.update(buf) # this is probably really really slow
        if C.hexdigest() != checksum:
            raise ValueError(f"Invalid checksum: {file}")
    else:
        warnings.warn(f"Integrity check disabled for {url}.")

    # unpack
    # *if* the folder contained a single folder, like a polite package, use that folder as its package name; but if it doesn't, use its archive name
    # we unpack to a temporary folder *first* and then rename instead of deciding which mode to use and unpacking directly because zipfile lacks
    # a clean API to determine what's in each folder: https://stackoverflow.com/questions/58888465/python-zipfile-get-top-level-directory-within-the-zipfile
    # (plus this way avoids buggy partial installs)

    data = pathlib.Path(xdg.BaseDirectory.save_data_path(APP)) # TODO: consider .load_data_paths(APP)
    subdata = pathlib.Path(tempfile.mkdtemp(suffix=".part", dir=data))

    # TODO: if we just don't do this we could maybe support non-archive files too, like a large image or something
    unpack(file, subdata)

    if len(os.listdir(subdata))==1 and os.path.isdir(subdata/(os.listdir(subdata)[0])):
        if pkg is None:
            pkg = os.listdir(subdata)[0]
        # uninstall the previous version
        # at this point we know, either:
        # - pkg is None and not installed(url) or
        # - pkg is not None and installed(pkg) # -> need to uninstall
        if (pkg is not None and installed(pkg)):
            uninstall(pkg)
        os.rename(subdata/(os.listdir(subdata)[0]), data/pkg) # this should be atomic since it's on the same filesystem since one is a subdir of the other.
        os.rmdir(subdata)
    else:
        if pkg is None:
            pkg = os.path.basename(file) # name for the pkg; used as a shortname, later; sort of janky that the *server* gets to pick this.
            pkg, _ = os.path.splitext(pkg)

        # uninstall the previous version
        # at this point we know, either:
        # - pkg is None and not installed(url) or
        # - pkg is not None and installed(pkg) # -> need to uninstall
        # TODO: merge
        if (pkg is not None and installed(pkg)):
            uninstall(pkg)

        os.rename(subdata, data/pkg)


    # write record of installation
    metadata = pathlib.Path(xdg.BaseDirectory.save_data_path(os.path.join(APP, 'humbugga')))
    
    os.makedirs(metadata/"pkgs"/pkg, exist_ok=True)
    with open(metadata/"pkgs"/pkg/"source","w") as source:
        print(url, file=source)
    
    # index by source url
    os.makedirs(metadata/"sources", exist_ok=True)
    with open(metadata/"sources"/encoded_url,"w") as s:
        print(pkg, file=s)

    # TODO: walk the installed files and checksum each of them individually, the way pip does.
    # and add a .integrity(pkg) call that
    # maybe slip it into .path() to autoprotect everything.


def urlkey(url):
    """
    Get an encoded key from a URL
    This is used to index downloads on disk safely.
    """
    return hashlib.sha256(url.encode("utf-8")).hexdigest() # uhhh is this what I want? this seems kind of nasty



def _get(pkg):
    """
    Find if pkg is installed

    pkg can be:
    - the installed pkg name
    - the source url
    - the *encoded* source url
        # check both by URL
        # XXX is there a risk of namespace collisions here? could someone exploit it by crafting a URL to look a certain way?
    """
    metadatas = xdg.BaseDirectory.load_data_paths(os.path.join(APP, 'humbugga'))
    for metadata in metadatas:
        metadata = pathlib.Path(metadata)

        if (metadata/"pkgs"/pkg).exists():
            # pkg specified as package name
            with open(metadata/"pkgs"/pkg/"source") as s:
                source = s.readline().strip()
            encoded_url = urlkey(source)

            # integrity check
            with open(metadata/"sources"/encoded_url) as s:
                pkg_ = s.readline().strip()
                assert pkg == pkg_

        elif (metadata/"sources"/(encoded_url:=pkg)).exists():
            # pkg specified as encoded source url
            with open(metadata/"sources"/encoded_url) as s:
                pkg = s.readline().strip()

            # integrity check
            with open(metadata/"pkgs"/pkg/"source") as s:
                source = s.readline().strip()
                assert urlkey(source) == encoded_url
        elif (metadata/"sources"/(encoded_url:=urlkey(pkg))).exists():
            # pkg specified as source url
            source = pkg
            with open(metadata/"sources"/encoded_url) as s:
                pkg = s.readline().strip()

            # integrity check
            with open(metadata/"pkgs"/pkg/"source") as s:
                source_ = s.readline().strip()
                assert source == source_
        else:
            continue

        data = pathlib.Path(xdg.BaseDirectory.save_data_path(APP)) # TODO: consider .load_data_paths(APP)
        path = data / pkg
        
        return {'name': pkg, 'source': source, 'encoded_url': encoded_url, 'path': path}
    raise KeyError(f'{pkg} is not installed')
    
    
def installed(pkg):
    """
    """
    try:
         _get(pkg)
         return True
    except KeyError:
        return False


def clean(unused=True):
    """
    Erase cache

    unused: if True, keep installed packages. If False, erase everything.
    """
    raise NotImplemented


def uninstall(pkg):
    """
    pkg: either the package name or the pkg's original source url
    """
    p = _get(pkg)

    data = pathlib.Path(xdg.BaseDirectory.save_data_path(APP)) # TODO: consider .load_data_paths(APP)
    shutil.rmtree(data/p['name'])
    metadata = pathlib.Path(xdg.BaseDirectory.save_data_path(os.path.join(APP, 'humbugga')))
    shutil.rmtree(metadata/"pkgs"/p['name'])
    os.unlink(metadata/"sources"/p['encoded_url'])


def path(pkg):
    """
    Get the path to the given package.

    This is analogous to importlib.resources in python. It is a lot simpler though, because our packages only ever have one root folder.
    """
    # this is in *most* 
    p = _get(pkg)
    return pathlib.Path(p['path'])


def list(): # XXX namespace collision oops
    """
    Get the list of packages installed for the current app.
    """
    def _list():
        metadatas = xdg.BaseDirectory.load_data_paths(os.path.join(APP, 'humbugga'))
        for metadata in metadatas:
            metadata = pathlib.Path(metadata)
            for pkg in os.listdir(metadata/"pkgs"):
                yield pkg
    return sorted(_list())


APP='glove'
#install('http://nlp.stanford.edu/data/glove.840B.300d.zip', 'sha256:c06db255e65095393609f19a4cfca20bf3a71e20cc53e892aafa490347e3849f')
#install('https://github.com/sct-data/PAM50/releases/download/r20201104/PAM50-r20201104.zip', 'sha256:db50286e268f4886335fb1edc83b431cae40a9e05487360628c46b3002dd0918')
install('https://github.com/sct-data/PAM50/releases/download/r20201104/PAM50-r20201104.zip', pkg='PAM50')
install('https://github.com/sct-data/PAM50/releases/download/r20191029/20191029_pam50.zip', pkg='PAM50')
#install('http://www.nltk.org/images/authors.png')
#install('https://www.dropbox.com/s/pwokjjnrexg0zl6/cohenadad_cv__20190424.pdf?dl=1', '.')
p = path('https://github.com/sct-data/PAM50/releases/download/r20201104/PAM50-r20201104.zip')
os.system(f'ls -l {p}')
p = path('sct-data-PAM50-13be1fe')
os.system(f'ls -l {p}')

import pprint; pprint.pprint(list())

raise SystemExit(1)

if __name__ == '__main__':
    # usage demos:
    import humbugga
    humbugga.APP = '_auto'
    (humbugga
      .requires('https://github.com/sct-data/PAM50/releases/download/r20201104/PAM50-r20201104.zip', 'sha256:db50286e268f4886335fb1edc83b431cae40a9e05487360628c46b3002dd0918')
      .requires(...))
    humbugga.install()

    dataset = humbugga.path('https://github.com/sct-data/PAM50/releases/download/r20201104/PAM50-r20201104.zip') # this part isn't good; it's okay for some datasets but bad for versioned datasets.
    # and yet this is okay for arch's makepkg. why? because... they are taking someone's code and repacking it?<C-b>
    fname = dataset/"atlas"/"PAM50_atlas_02.nii.gz"
    # method one for handling versioning woes:
    # - we could refer to installations by their basename:
    fname = humbugga.path('PAM50.zip')/"atlas"/"PAM50_atlas_02.nii.gz"
    # but this doesn't work if you've put versioning into your filename.
    #  - well we can just tell people not to do that. and if you're using someone *elses* dataset, well, tough luck. if it's someone else's dataset it's probably not versioned anyway.
    # - on osf.io
    # - should we ...use the filename it came down as?
    # - should I be keying on basename or full URL? In practice, mostly there's only a single mirror (or at least only a single URL; some people have CDNs)
    #   how to handle mirrors, then? hmm. maybe a single package can take multiple mirrors? but then we can't use that URL to refer to it anymore.
    #   unless we consider all of them synonyms?
    humbugga.list() # view installed packages - {basename: (url, install_path)}
