from setuptools import setup, find_packages
import pathlib


def get_install_requirements():
    with open(pathlib.Path(__file__).parent / "requirements.txt", "r") as reqs_file:
        return reqs_file.readlines()


reqs = get_install_requirements()


setup(
    name="Alpaca",
    version="0.1.0",
    author="Oasis LMF",
    author_email="support@oasislmf.org",
    keywords='oasis lmf loss modeling framework',
    description="",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/OasisLMF/Alpaca",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=reqs,
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.12',
    ],
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'alpaca=alpaca.cli.root:main'
        ]
    }
)
