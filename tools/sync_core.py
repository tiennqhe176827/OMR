"""Refresh the Android engine from the desktop source without copying user data."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
source = root.parent / 'cdtd/omr_system'
target = root / 'app/src/main/python'
for file in (source / 'omr').glob('*.py'):
    shutil.copy2(file, target / 'omr' / file.name)
shutil.copy2(source / 'config.py', target / 'config.py')
for name in ('real_sheet_experimental.json', 'real_sheet_experimental_reference.png',
             'thpt_cv1239_4digit.json', 'thpt_cv1239_4digit_reference.png'):
    shutil.copy2(source / 'templates' / name, target / 'templates' / name)
print('Synced OMR core and template. Rebuild APK to apply changes.')
