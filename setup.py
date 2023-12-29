from setuptools import setup, find_packages
from setuptools.command.install import install
import os
import shutil

VERSION = '0.4.0'
DESCRIPTION = 'DradisMD is CLI utility for exporting and importing Dradis projects to local files.'

class PostInstallCommand(install):
    def run(self):
        # Call parent run method
        install.run(self)
       
        # Copy sample_config.ini to ~/.config/dradismd/ after installation
        config_dir = os.path.expanduser('~/.config/dradismd')
        package_files = ['config.ini','evidence_template.textile','issue_template.textile']
        print(f'Copying packages files in {config_dir}')
        print(self.install_lib)
        if not os.path.exists(self.install_lib):
            print('self.install_lib not exist')
            os.makedirs(config_dir)
        for item in package_files:
            item_path = os.path.join(self.install_lib, 'dradismd', item)
            if not os.path.exists(os.path.join(config_dir, item)):
                shutil.copy(item_path, config_dir)

       



# Setting up
setup(
    # the name must match the folder name 'verysimplemodule'
    name="dradismd",
    version=VERSION,
    author="Elliot Rasch",
    description=DESCRIPTION,
    url="https://github.com/T0ille/DradisMD",
    packages=find_packages(),
    package_data={"dradismd": ["*.ini", "*.textile"]},
    include_package_data=True,
    install_requires=['dradis-api@git+https://github.com/NorthwaveSecurity/dradis-api@master',
                      'rich',
                      'pypandoc',
                      'timeago',
                      'requests',
                      'setuptools'],
    keywords=["dradis api", "markdown"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
    entry_points={
    'console_scripts': [
        'dradismd = dradismd.dradismd:main',
    ],
    },
    cmdclass={
        'install': PostInstallCommand,
    },
)
