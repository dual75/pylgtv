from distutils.core import setup

setup(
      name = 'pylgtv',
      packages = ['pylgtv'],
      package_dir = {'pylgtv': 'pylgtv'},
      package_data = {'pylgtv': ['handshake.json']},
      install_requires = ['websockets'],
      zip_safe = True,
      version = '0.1.8',
      description = 'Library to control webOS based LG Tv devices',
      author = 'Dennis Karpienski',
      author_email = 'dennis@karpienski.de',
      url = 'https://github.com/dual75/pylgtv',
      download_url = 'https://github.com/dual75/pylgtv/archive/0.1.0.tar.gz',
      keywords = ['webos', 'tv'],
      classifiers = [],
)
