#!/bin/bash

###
# Create a .deb package from Python library in the current working directory
#   with CodeMeter-encrypted bytecode.
#
# NOTE: this is a work in progress that has been tested on Santoku 0.4 and
#   currently requires the following:
#
#   - sudo apt-get install dpkg-dev debhelper python-all-dev
#   - sudo pip install stdeb  # (outside of virtualenv)
#   - viaForensics pycEncrypt utility available in executable path
#
# IMPORTANT: deactivate any active virtualenv before you run this script.
#
# Example:
#   ./create_encrypted_deb_pkg.sh 5000342 2000 124 /my_path/versionkeys/RSApublic-v1.key

FIRM_CODE=$1
PRODUCT_CODE=$2
MEM_LOCATION=$3
PUBLIC_KEY_LOCATION=$4

CUR_DIR=`pwd`
MODIFY_PKG_SCRIPT="${CUR_DIR}/bin/buildtools/modify_deb_pkg.sh"

if [[ ! -f $PUBLIC_KEY_LOCATION ]]; then
    echo "[!] Public key for CodeMeter bytecode encryption not found"
    exit 1
fi
KEY_PATH=`realpath ${PUBLIC_KEY_LOCATION}`

# build package
echo "==> Building package"
python setup.py --command-packages=stdeb.command sdist_dsc
if [[ -f $MODIFY_PKG_SCRIPT ]]; then
    ${MODIFY_PKG_SCRIPT}
fi
cd deb_dist/datagrid-gtk3-*
dpkg-buildpackage -uc -us

# unpackage .deb pkg and modify it for codemeter encryption
# FIXME: obviously ideally this wouldn't be necessary, but packaging tools
#   seem to have a need to introspect Python files, which is broken by our
#   CodeMeter dependency -- how else to fix?
echo "==> Processing package for CodeMeter encryption"
BUILD_DIR="/tmp/datagrid-gtk3_build"
cd $CUR_DIR
DEB_NAME=`find ./deb_dist -type f -name "python-datagrid-gtk3*.deb" | xargs basename`
rm -rf $BUILD_DIR
mkdir $BUILD_DIR
echo "==> Processing package: ${DEB_NAME}"
cp deb_dist/$DEB_NAME $BUILD_DIR
cd $BUILD_DIR
dpkg-deb -x $DEB_NAME .
dpkg-deb -e $DEB_NAME
rm $DEB_NAME
cd $BUILD_DIR/usr/lib/python2.7/dist-packages
# remove pyshared-related items
find datagrid-gtk3 -type l -exec bash -c 'ln -f "$(readlink -m "$0")" "$0"' {} \;
find datagrid-gtk3*.egg-info -type l -exec bash -c 'ln -f "$(readlink -m "$0")" "$0"' {} \;
rm -rf $BUILD_DIR/usr/share/pyshared
rm -rf $BUILD_DIR/usr/lib/python2.7/dist-packages/datagrid-gtk3*.egg-info/requires.txt
rm -rf $BUILD_DIR/DEBIAN/md5sums
# compile and encrypt source
find datagrid-gtk3 -type f -name "*.pyc" -exec rm {} \;
python -m compileall datagrid-gtk3
find datagrid-gtk3 -type f -name "*.py" -exec rm {} \;
find datagrid-gtk3 -type f -name "*.pyc" -exec pycEncrypt e f${FIRM_CODE} p${PRODUCT_CODE} R${MEM_LOCATION} ${KEY_PATH} {} {} \;

# rebuild package
cd $BUILD_DIR
dpkg-deb -b . /tmp/$DEB_NAME
mv /tmp/$DEB_NAME $CUR_DIR
rm -rf $BUILD_DIR