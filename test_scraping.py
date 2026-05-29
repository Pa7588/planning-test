import requests
from bs4 import BeautifulSoup

url = "https://www.planning-medical.com/p.php?s=532babfe6f45ec233bac467f086a3f8a&b=0"

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

print("=== TEST SCRAPING PLANNING-MEDICAL ===")
print(f"URL: {url}")

try:
    r = requests.get(url, headers=headers, timeout=15)
    print(f"Status: {r.status_code}")
    print(f"Taille réponse: {len(r.text)} caractères")
    print(f"Content-Type: {r.headers.get('content-type', 'inconnu')}")
    print()
    print("=== 500 PREMIERS CARACTÈRES ===")
    print(r.text[:500])
    print()
    
    soup = BeautifulSoup(r.text, 'html.parser')
    table = soup.find('table')
    print(f"=== TABLEAU TROUVÉ: {table is not None} ===")
    
    if table:
        rows = table.find_all('tr')
        print(f"Nombre de lignes: {len(rows)}")
        print("Première ligne:")
        if rows:
            cells = rows[0].find_all('td')
            for c in cells[:3]:
                print(f"  {repr(c.get_text(strip=True)[:80])}")
    else:
        # Chercher d'autres structures
        divs = soup.find_all('div')
        print(f"Nombre de divs: {len(divs)}")
        scripts = soup.find_all('script')
        print(f"Nombre de scripts: {len(scripts)}")
        
except Exception as e:
    print(f"ERREUR: {e}")
