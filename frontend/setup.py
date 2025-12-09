import subprocess
import os
import shutil
from setuptools import setup
from setuptools.command.build_py import build_py

class BuildFrontend(build_py):
    def run(self):
        # Run npm build
        if not os.path.exists('node_modules'):
            self.spawn(['npm', 'install'])
        self.spawn(['npm', 'run', 'build'])

        # Copy dist to package
        target_dir = os.path.join(self.build_lib, 'turbodrone_frontend_server', 'dist')
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        shutil.copytree('dist', target_dir)

        super().run()

setup(
    cmdclass={
        'build_py': BuildFrontend,
    },
    packages=['turbodrone_frontend_server'],
    package_data={
        'turbodrone_frontend_server': ['dist/**/*', 'dist/*'],
    },
    include_package_data=True,
)
