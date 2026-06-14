import os
import glob
import re

COLOR_MAP = {
    # Light -> Dark Base
    '#f4f5f7': '#080808',
    '#333333': '#FFFFFF',
    '#ffffff': '#111111',
    '#eaeaea': '#1E1E1E',
    '#111111': '#FFFFFF',
    '#555555': '#888888',
    '#999999': '#555555',
    
    # Neutral Boxes
    '#f9f9f9': '#1a1a1a',
    '#eeeeee': '#2a2a2a',
    
    # Success/Positive Box
    '#f0fdf4': 'rgba(14, 203, 129, 0.1)',
    '#bbf7d0': '#0ECB81',
    '#166534': '#0ECB81',
    
    # Error/Negative Box
    '#dc3545': '#F6465D',
    '#fdf2f2': 'rgba(246, 70, 93, 0.1)',
    '#f8d7da': '#F6465D',
    '#842029': '#F6465D',
}

template_dir = r'c:\Users\USER\Desktop\WORK STATION\PYTHON\swift-folder\swift\backend\templates\emails'
files = glob.glob(os.path.join(template_dir, '*.html'))

for file in files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    def replacer(match):
        hex_color = match.group(0).lower()
        if hex_color in COLOR_MAP:
            return COLOR_MAP[hex_color]
        return match.group(0)

    content = re.sub(r'#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}', replacer, content)
        
    with open(file, 'w', encoding='utf-8') as f:
        f.write(content)
        
print("Updated all emails!")
