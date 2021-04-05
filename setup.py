from setuptools import setup, find_packages, find_namespace_packages
import pathlib

here = pathlib.Path(__file__).parent.resolve()

# workaround a bug introduced by pyproject.toml
# https://github.com/pypa/pip/issues/7953#issuecomment-645133255
import site, sys; site.ENABLE_USER_SITE = True

setup(
  name='humbugga',
  version='0.0.1',
  description='App-local package manager',
  long_description=(here / 'README.md').read_text(encoding='utf-8'),
  long_description_content_type='text/markdown',
  author='kousu',
  author_email='kousu@kousu.ca',
  url='https://github.com/kousu/humbugga',
  license='MIT', # TODO: is this the right shorttag for this license?
  # use a src/ layout: https://blog.ionelmc.ro/2014/05/25/python-packaging/#the-structure
  
  # we intend to distribute this as a *part* of the infersent package
  # but to not conflict with what's in that package, we need to make sure to only provide files in a subpath of it
  #
  packages=find_namespace_packages('src/'), # https://setuptools.readthedocs.io/en/latest/userguide/package_discovery.html#using-find-namespace-or-find-namespace-packages
  package_dir={"":"src/"},        # but workaround a bug with it https://stackoverflow.com/a/64207669/2898673
  package_data={'': ['*']},  # include everything in the folder at the time of packaging
  #include_package_data=True,# include only things under git; requires setuptools_scm
  python_requires='>=3.6,<=3.10', # TODO: actually test these
  setup_requires=[ # pyproject.toml::build-system.requires is supposed to supersede this, but it's still very new so we duplicate it.
    'setuptools',
    #'setuptools_scm',
  ],
  install_requires=[
    'tqdm',
    'requests',
    #'xdg',
    'pyxdg',
  ],
)

