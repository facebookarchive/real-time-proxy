from distutils.core import setup

setup(  name = 'fbproxy',
        version = '1.0',
        description = 'Realtime-invalidated Facebook Graph Proxy',
        author = 'Facebook, Inc.',
        author_email = 'yuliyp@facebook.com',
        url = 'http://www.facebook.com/',
        packages = ['fbproxy'],
        scripts = ['start_proxy'],
        data_files = [('.', ['config.sample'])],
        requires = ['cherrypy.wsgiserver'],
        provides = ['fbproxy']
    )
