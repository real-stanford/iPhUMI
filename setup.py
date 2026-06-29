from setuptools import setup, find_packages

INSTALL_REQUIRES = []

setup(
    name="iphumi",
    author="Austin Patel",
    version="1.0.0",
    description="",
    keywords=[],
    include_package_data=True,
    python_requires=">=3.8",
    install_requires=INSTALL_REQUIRES,
    package_dir={"": "python_package"},
    packages=find_packages(where="python_package"),
    classifiers=[],
    zip_safe=False,
)
