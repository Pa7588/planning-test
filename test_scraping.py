import requests
from bs4 import BeautifulSoup
import re

url = "https://www.planning-medical.com/p.php?s=532babfe6f45ec233bac467f086a3f8a&b=0"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

r = requests.get(url, headers=headers, timeout=15)
soup = BeautifulSoup(r.text, 'html.parser')
table = soup.find('table')
rows = table.find_all('tr')

print(f"Nombre de lignes: {len(rows)}")
print()

# Afficher le contenu brut des 3 premières lignes complètes
for i, row in enumerate(rows[:3]):
    cells = row.find_all('td')
    print(f"=== LIGNE {i} ({len(cells)} cellules) ===")
    for j, cell in enumerate(cells):
        txt = cell.get_text(separator='|', strip=True)
        if txt:
            print(f"  cell[{j}]: {repr(txt[:120])}")
    print()
    
