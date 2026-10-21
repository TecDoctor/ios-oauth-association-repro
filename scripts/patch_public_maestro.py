"""Experimental public-source driver patch; never changes the private SDK."""
import hashlib
from pathlib import Path
import sys
import zipfile

SOURCE_REVISION = '14a408335e17a090df1e26bdbeaf80d8122a8fd8'
RELATIVE_SOURCE = 'maestro-ios-xctest-runner/maestro-driver-iosUITests/Routes/Handlers/ViewHierarchyHandler.swift'
BUILD_SCRIPT = 'maestro-ios-xctest-runner/build-maestro-ios-runner.sh'
OLD_BUILD = 'ARCHS="$ARCHS" ${DEVELOPMENT_TEAM_OPT}'
NEW_BUILD = 'ARCHS="$ARCHS" IPHONEOS_DEPLOYMENT_TARGET=15.0 ${DEVELOPMENT_TEAM_OPT}'
OLD = '''        let isRunning = safariWebService.state == .runningForeground || safariWebService.state == .runningBackground
        guard isRunning else {'''
NEW = '''        let safariState = safariWebService.state
        NSLog("[Safari foreground probe] application state: \\(safariState.rawValue)")
        // A dismissed background service must not be queried for WebViews.
        guard safariState == .runningForeground else {'''
RESOURCES = (
    'driver-iPhoneSimulator/Debug-iphonesimulator/maestro-driver-iosUITests-Runner.zip',
    'driver-iPhoneSimulator/Debug-iphonesimulator/maestro-driver-ios.zip',
    'driver-iPhoneSimulator/maestro-driver-ios-config.xctestrun',
)


def patch(source):
    path = source / RELATIVE_SOURCE
    text = path.read_text()
    build = source / BUILD_SCRIPT
    build_text = build.read_text()
    if text.count(OLD) != 1 or build_text.count(OLD_BUILD) != 1:
        raise ValueError('Expected pinned upstream guard and build invocation exactly once')
    path.write_text(text.replace(OLD, NEW))
    # Xcode 27 no longer accepts the upstream driver's iOS 14 minimum.
    build.write_text(build_text.replace(OLD_BUILD, NEW_BUILD))


def package(source, jar):
    resources = source / 'maestro-ios-driver/src/main/resources'
    replacements = {name: (resources / name).read_bytes() for name in RESOURCES}
    temporary = jar.with_suffix('.patched.jar')
    with zipfile.ZipFile(jar) as original, zipfile.ZipFile(temporary, 'w') as output:
        names = original.namelist()
        if any(names.count(name) != 1 for name in RESOURCES):
            raise ValueError('Unexpected release resource layout')
        if any(name.startswith('META-INF/') and name.endswith(('.SF', '.RSA', '.DSA')) for name in names):
            raise ValueError('Refusing to rewrite a signed archive')
        for entry in original.infolist():
            output.writestr(entry, replacements.get(entry.filename, original.read(entry)))
    temporary.replace(jar)
    print('Experimental public XCTest runner installed; SHA256=' + hashlib.sha256(jar.read_bytes()).hexdigest())


if __name__ == '__main__':
    if sys.argv[1] == 'patch':
        patch(Path(sys.argv[2]))
    elif sys.argv[1] == 'package':
        package(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit('Expected patch or package')
