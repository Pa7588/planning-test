# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta
import re
import json

# ─── CONFIG ───────────────────────────────────────────────────────────────────

CIBLES_URG = [
    "M. Belhomme De Franqueville",
    "L. Okoyi Ossouka Mapangou",
    "E. Beros",
    "P. Messina",
    "J. Peyres",
    "S. Niane",
    "C. Vasseur",
    "J. Blanc",
    "A. Khadraoui",
    "M. Harhour",
    "E. Perthuisot",
    "R. Pebay",
    "I. Mokhtari",
    "A. Ponton",
    "E. Macabiau",
    "J. Langlois",
    "A. Wilhelm",
    "C. Viola",
]

CIBLES_GERIA = [
    "P. Lorette",
    "Y. Esteves",
    "E. Salgues",
    "S. Kassou",
    "T. Bourot",
    "M. Gratesac",
    "C. Gorra",
]

CIBLES = CIBLES_URG + CIBLES_GERIA

PLANNINGS = {
    "gardes_purpan":   "https://app.planning.lifen.health/external/plannings/513b393c3c6a11e88b24",
    "gardes_rangueil": "https://app.planning.lifen.health/external/plannings/647003302b22a53d19c1",
    "urgences":        "https://app.planning.lifen.health/external/plannings/d9620e86592712e23672",
    "urgences_jf":     "https://app.planning.lifen.health/external/plannings/78ef22ade246745d3835",
    "sauv":            "https://app.planning.lifen.health/external/plannings/bfe39d8a0bc17b5e8906",
    "geriatrie":       "https://app.planning.lifen.health/external/plannings/55ed4e1c59041a69a363",
}

# URL planning-medical pour les seniors
PM_URL = "https://www.planning-medical.com/p.php?s=532babfe6f45ec233bac467f086a3f8a&b={offset}"

MOIS_FR = ["Janvier","Février","Mars","Avril","Mai","Juin",
           "Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
MOIS_NUM = {m: i+1 for i, m in enumerate(MOIS_FR)}

NON_ATTRIBUE = {"non attribué", "r. planning urg toulouse"}
JOURS_SEMAINE = {"lun","mar","mer","jeu","ven","sam","dim"}

PARASITES = {
    "lifen planning", "créez votre compte", "voir les échanges",
    "télécharger", "du", "au", "actions", "ajouter vos indisponibilités",
    "plannings", "actifs", "terminés", "publié et disponible",
    "© 2014", "centre d'aide", "contacter le support", "suggérer une évolution",
    "fr", "en", "tableau de bord", "agenda", "échanges", "disponibilités",
}

POSTES_GERIA = {
    "garonne-soins palliatifs", "garonne-soins palliatifs-pum",
    "pug-albarède", "pug albarède", "pug rangueil", "pug-rangueil jf",
}

JOURS_FERIES = {
    date(2026, 5,  8),
    date(2026, 5, 14),
    date(2026, 5, 25),
    date(2026, 7, 14),
    date(2026, 8, 15),
    date(2026, 11, 1),
}

DEBUG = True

# ─── CORRESPONDANCES INTERNE → SENIOR(S) ──────────────────────────────────────
# Clé : fragment du poste interne (lowercase)
# Valeur : liste de clés dans le dict seniors du jour
# Les clés seniors correspondent aux noms de colonnes dans planning-medical

def seniors_pour_poste(poste):
    """Retourne la liste des clés seniors pour un poste interne donné."""
    p = poste.lower()
    nuit = 'nuit' in p or '13h-8' in p or '13 - 8' in p or '18h-8' in p or '13h - 8' in p

    # Rangueil
    if 'amct 1' in p:
        return ['MAO NUIT'] if nuit else ['MAO']
    if 'amct 2' in p:
        return ['AMCT NUIT'] if nuit else ['AMCT']
    if 'cmct' in p:
        return ['MAO NUIT', 'SAUV R NUIT'] if nuit else ['MAO', 'SAUV R']
    if 'uhcd r' in p or ('uhcd' in p and 'purpan' not in p):
        return [] if nuit else ['UHCD R', 'MAO', 'SAUV R']
    if 'sauv r' in p or ('sauv' in p and 'purpan' not in p and 'rangueil' not in p and 'nuit' not in p):
        return ['SAUV R NUIT'] if nuit else ['SAUV R']

    # Purpan
    if 'hub 1' in p:
        return ['AMT HUB 1 Nuit'] if nuit else ['AMT HUB 1 Purpan']
    if 'hub 2' in p:
        return ['AMT HUB 2 Nuit'] if nuit else ['AMT HUB 2 Purpan']
    if 'hub 3' in p:
        return ['AMT HUB 3 Nuit'] if nuit else ['AMT HUB 3 Purpan']
    if 'sauv' in p and ('purpan' in p or 'tfc' in p):
        return ['SAUV/MCO/TFC Nuit'] if nuit else ['SAUV/TFC Purpan']
    if 'ua' in p and ('jour' in p or 'rééval' in p):
        return ['AMT Med Rev Purpan']
    if 'ua' in p and 'nuit' in p:
        return ['AMT Med Rev Soir Purpan']

    # LDS → personne
    if 'lds' in p:
        return []

    return []

# ─── HELPERS DATE ─────────────────────────────────────────────────────────────

def est_ferie(d):            return d in JOURS_FERIES
def est_samedi(d):           return d.weekday() == 5
def est_dimanche_ou_ferie(d): return d.weekday() == 6 or est_ferie(d)

# ─── CATÉGORISATION ───────────────────────────────────────────────────────────

def categoriser_urg(poste):
    p = poste.lower()
    if re.search(r'\blds\b', p):
        return ('violet', 'lds')
    if 'nuit' in p:
        return ('jaune', 'garde')
    if re.search(r'13\s*h?\s*[-–]\s*8\s*h?', p) or '13-8' in p or '13 - 8' in p:
        return ('jaune', 'garde')
    if re.search(r'18\s*h?\s*[-–]\s*8\s*h?', p) or '18-8' in p or '18h-8h' in p:
        return ('jaune', 'garde')
    if re.search(r'8\s*h?\s*[-–]\s*13\s*h?', p) or '8-13' in p:
        return ('jaune', 'demi-garde')
    if re.search(r'13\s*h?\s*[-–]\s*18\s*h?', p) or '13-18' in p or '13h-18' in p:
        return ('jaune', 'demi-garde')
    return ('rouge', 'jour')

def categoriser_geria(poste, jour_date):
    p = poste.lower()
    if 'jf' in p:
        return ('rouge', 'geria-jf')
    if est_dimanche_ou_ferie(jour_date):
        return ('rouge', 'geria-dim')
    elif est_samedi(jour_date):
        return ('jaune', 'geria-sam')
    else:
        return ('orange', 'geria-semaine')

def repos_apres_garde_urg(poste, type_poste):
    if type_poste == 'demi-garde':
        return False
    p = poste.lower()
    if 'nuit' in p: return True
    if re.search(r'13\s*h?\s*[-–]\s*8\s*h?', p) or '13-8' in p or '13 - 8' in p: return True
    if re.search(r'18\s*h?\s*[-–]\s*8\s*h?', p) or '18-8' in p or '18h-8h' in p: return True
    if re.search(r'\blds\b', p): return True
    return False

def est_poste_geria(poste):
    return poste.lower().strip() in POSTES_GERIA

# ─── FETCH LIFEN ──────────────────────────────────────────────────────────────

def fetch_planning(nom, url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        texte = soup.get_text('\n')
        if DEBUG:
            with open(f"debug_{nom}.txt", "w", encoding="utf-8") as f:
                f.write(texte)
        return texte
    except Exception as e:
        print(f"  ⚠ Erreur fetch {url}: {e}")
        return ""

# ─── FETCH SENIORS (planning-medical) ─────────────────────────────────────────

def fetch_seniors():
    """
    Scrape planning-medical.com.
    Format cellule : "POSTE|Nom Initiale." (sep=|, xa0=espace insecable)
    Date dans la derniere cellule : "Jeu|28/05/2026"
    """
    print("  -> Scraping planning-medical pour les seniors...")
    seniors = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    for offset in range(0, 190, 10):
        url = PM_URL.format(offset=offset)
        try:
            r = requests.get(url, timeout=15, headers=headers)
            r.raise_for_status()
        except Exception as e:
            print(f"    offset {offset}: {e}")
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table")
        if not table:
            continue

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            # Date dans la derniere cellule : "Jeu|28/05/2026"
            last_txt = cells[-1].get_text(separator="|", strip=True)
            m = re.search(r"(\d{2}/\d{2}/\d{4})", last_txt)
            if not m:
                continue
            try:
                jour_date = datetime.strptime(m.group(1), "%d/%m/%Y").date()
            except Exception:
                continue

            date_iso = jour_date.isoformat()
            if date_iso not in seniors:
                seniors[date_iso] = {}

            # Format : "POSTE|Nom\xa0Initiale."
            for cell in cells:
                txt = cell.get_text(separator="|", strip=True)
                if not txt or "pourvoir" in txt.lower():
                    continue
                parts = txt.split("|")
                parts = [p.replace("\xa0", " ").strip() for p in parts if p.strip()]
                if len(parts) >= 2:
                    poste_senior = parts[0].strip()
                    nom_senior = parts[-1].strip()
                    if poste_senior and nom_senior:
                        seniors[date_iso][poste_senior] = nom_senior

    nb_jours = len(seniors)
    print(f"    {nb_jours} jours de seniors charges")
    if nb_jours > 0:
        first_date = sorted(seniors.keys())[0]
        print(f"    Exemple {first_date}: {list(seniors[first_date].items())[:3]}")
    return seniors

# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta
import re
import json

# ─── CONFIG ───────────────────────────────────────────────────────────────────

CIBLES_URG = [
    "M. Belhomme De Franqueville",
    "L. Okoyi Ossouka Mapangou",
    "E. Beros",
    "P. Messina",
    "J. Peyres",
    "S. Niane",
    "C. Vasseur",
    "J. Blanc",
    "A. Khadraoui",
    "M. Harhour",
    "E. Perthuisot",
    "R. Pebay",
    "I. Mokhtari",
    "A. Ponton",
    "E. Macabiau",
    "J. Langlois",
    "A. Wilhelm",
    "C. Viola",
]

CIBLES_GERIA = [
    "P. Lorette",
    "Y. Esteves",
    "E. Salgues",
    "S. Kassou",
    "T. Bourot",
    "M. Gratesac",
    "C. Gorra",
]

CIBLES = CIBLES_URG + CIBLES_GERIA

PLANNINGS = {
    "gardes_purpan":   "https://app.planning.lifen.health/external/plannings/513b393c3c6a11e88b24",
    "gardes_rangueil": "https://app.planning.lifen.health/external/plannings/647003302b22a53d19c1",
    "urgences":        "https://app.planning.lifen.health/external/plannings/d9620e86592712e23672",
    "urgences_jf":     "https://app.planning.lifen.health/external/plannings/78ef22ade246745d3835",
    "sauv":            "https://app.planning.lifen.health/external/plannings/bfe39d8a0bc17b5e8906",
    "geriatrie":       "https://app.planning.lifen.health/external/plannings/55ed4e1c59041a69a363",
}

# URL planning-medical pour les seniors
PM_URL = "https://www.planning-medical.com/p.php?s=532babfe6f45ec233bac467f086a3f8a&b={offset}"

MOIS_FR = ["Janvier","Février","Mars","Avril","Mai","Juin",
           "Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
MOIS_NUM = {m: i+1 for i, m in enumerate(MOIS_FR)}

NON_ATTRIBUE = {"non attribué", "r. planning urg toulouse"}
JOURS_SEMAINE = {"lun","mar","mer","jeu","ven","sam","dim"}

PARASITES = {
    "lifen planning", "créez votre compte", "voir les échanges",
    "télécharger", "du", "au", "actions", "ajouter vos indisponibilités",
    "plannings", "actifs", "terminés", "publié et disponible",
    "© 2014", "centre d'aide", "contacter le support", "suggérer une évolution",
    "fr", "en", "tableau de bord", "agenda", "échanges", "disponibilités",
}

POSTES_GERIA = {
    "garonne-soins palliatifs", "garonne-soins palliatifs-pum",
    "pug-albarède", "pug albarède", "pug rangueil", "pug-rangueil jf",
}

JOURS_FERIES = {
    date(2026, 5,  8),
    date(2026, 5, 14),
    date(2026, 5, 25),
    date(2026, 7, 14),
    date(2026, 8, 15),
    date(2026, 11, 1),
}

DEBUG = True

# ─── CORRESPONDANCES INTERNE → SENIOR(S) ──────────────────────────────────────
# Clé : fragment du poste interne (lowercase)
# Valeur : liste de clés dans le dict seniors du jour
# Les clés seniors correspondent aux noms de colonnes dans planning-medical

def seniors_pour_poste(poste):
    """Retourne la liste des clés seniors pour un poste interne donné."""
    p = poste.lower()
    nuit = 'nuit' in p or '13h-8' in p or '13 - 8' in p or '18h-8' in p or '13h - 8' in p

    # Rangueil
    if 'amct 1' in p:
        return ['MAO NUIT'] if nuit else ['MAO']
    if 'amct 2' in p:
        return ['AMCT NUIT'] if nuit else ['AMCT']
    if 'cmct' in p:
        return ['MAO NUIT', 'SAUV R NUIT'] if nuit else ['MAO', 'SAUV R']
    if 'uhcd r' in p or ('uhcd' in p and 'purpan' not in p):
        return [] if nuit else ['UHCD R', 'MAO', 'SAUV R']
    if 'sauv r' in p or ('sauv' in p and 'purpan' not in p and 'rangueil' not in p and 'nuit' not in p):
        return ['SAUV R NUIT'] if nuit else ['SAUV R']

    # Purpan
    if 'hub 1' in p:
        return ['AMT HUB 1 Nuit'] if nuit else ['AMT HUB 1 Purpan']
    if 'hub 2' in p:
        return ['AMT HUB 2 Nuit'] if nuit else ['AMT HUB 2 Purpan']
    if 'hub 3' in p:
        return ['AMT HUB 3 Nuit'] if nuit else ['AMT HUB 3 Purpan']
    if 'sauv' in p and ('purpan' in p or 'tfc' in p):
        return ['SAUV/MCO/TFC Nuit'] if nuit else ['SAUV/TFC Purpan']
    if 'ua' in p and ('jour' in p or 'rééval' in p):
        return ['AMT Med Rev Purpan']
    if 'ua' in p and 'nuit' in p:
        return ['AMT Med Rev Soir Purpan']

    # LDS → personne
    if 'lds' in p:
        return []

    return []

# ─── HELPERS DATE ─────────────────────────────────────────────────────────────

def est_ferie(d):            return d in JOURS_FERIES
def est_samedi(d):           return d.weekday() == 5
def est_dimanche_ou_ferie(d): return d.weekday() == 6 or est_ferie(d)

# ─── CATÉGORISATION ───────────────────────────────────────────────────────────

def categoriser_urg(poste):
    p = poste.lower()
    if re.search(r'\blds\b', p):
        return ('violet', 'lds')
    if 'nuit' in p:
        return ('jaune', 'garde')
    if re.search(r'13\s*h?\s*[-–]\s*8\s*h?', p) or '13-8' in p or '13 - 8' in p:
        return ('jaune', 'garde')
    if re.search(r'18\s*h?\s*[-–]\s*8\s*h?', p) or '18-8' in p or '18h-8h' in p:
        return ('jaune', 'garde')
    if re.search(r'8\s*h?\s*[-–]\s*13\s*h?', p) or '8-13' in p:
        return ('jaune', 'demi-garde')
    if re.search(r'13\s*h?\s*[-–]\s*18\s*h?', p) or '13-18' in p or '13h-18' in p:
        return ('jaune', 'demi-garde')
    return ('rouge', 'jour')

def categoriser_geria(poste, jour_date):
    p = poste.lower()
    if 'jf' in p:
        return ('rouge', 'geria-jf')
    if est_dimanche_ou_ferie(jour_date):
        return ('rouge', 'geria-dim')
    elif est_samedi(jour_date):
        return ('jaune', 'geria-sam')
    else:
        return ('orange', 'geria-semaine')

def repos_apres_garde_urg(poste, type_poste):
    if type_poste == 'demi-garde':
        return False
    p = poste.lower()
    if 'nuit' in p: return True
    if re.search(r'13\s*h?\s*[-–]\s*8\s*h?', p) or '13-8' in p or '13 - 8' in p: return True
    if re.search(r'18\s*h?\s*[-–]\s*8\s*h?', p) or '18-8' in p or '18h-8h' in p: return True
    if re.search(r'\blds\b', p): return True
    return False

def est_poste_geria(poste):
    return poste.lower().strip() in POSTES_GERIA

# ─── FETCH LIFEN ──────────────────────────────────────────────────────────────

def fetch_planning(nom, url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        texte = soup.get_text('\n')
        if DEBUG:
            with open(f"debug_{nom}.txt", "w", encoding="utf-8") as f:
                f.write(texte)
        return texte
    except Exception as e:
        print(f"  ⚠ Erreur fetch {url}: {e}")
        return ""

# ─── FETCH SENIORS (planning-medical) ─────────────────────────────────────────

def fetch_seniors():
    """
    Scrape planning-medical.com sur toute la période été.
    Retourne un dict : seniors[date_iso][poste_senior] = "Nom Prenom"
    """
    print("  → Scraping planning-medical pour les seniors...")
    seniors = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # Couvrir mai → novembre 2026 (~185 jours, par pages de 10)
    for offset in range(0, 190, 10):
        url = PM_URL.format(offset=offset)
        try:
            r = requests.get(url, timeout=15, headers=headers)
            r.raise_for_status()
        except Exception as e:
            print(f"    ⚠ offset {offset}: {e}")
            continue

        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find('table')
        if not table:
            continue

        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if not cells:
                continue

            # Première cellule = date (ex: "Jeu (Jeudi) 28/05/2026")
            date_txt = cells[0].get_text(strip=True)
            m = re.search(r'(\d{2}/\d{2}/\d{4})', date_txt)
            if not m:
                continue
            try:
                jour_date = datetime.strptime(m.group(1), "%d/%m/%Y").date()
            except:
                continue

            date_iso = jour_date.isoformat()
            if date_iso not in seniors:
                seniors[date_iso] = {}

            # Parcourir toutes les cellules pour extraire poste + senior
            for cell in cells[1:]:
                txt = cell.get_text(strip=True)
                if not txt or 'À pourvoir' in txt:
                    continue
                # Format : "POSTE   Nom P." ou "POSTE\nNom P."
                # On cherche le dernier mot qui ressemble à un nom (Initiale. Nom)
                # En fait le format est "Libellé poste   Prénom N." ou "Libellé poste   N. Prénom"
                # D'après ce qu'on a vu : "MAO   Guerrero F." → split sur espaces multiples
                parts = re.split(r'\s{2,}|\n', txt)
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) >= 2:
                    poste_senior = parts[0]
                    nom_senior = parts[-1]
                    seniors[date_iso][poste_senior] = nom_senior

    nb_jours = len(seniors)
    print(f"    ✓ {nb_jours} jours de seniors chargés")
    return seniors

# ─── PARSER LIFEN ─────────────────────────────────────────────────────────────

def est_nom_personne(s):
    return bool(re.match(r'^[A-Z]\.\s+[A-Z][a-zA-ZÀ-ÿ\s\-]+$', s))

def est_poste_urg(s):
    mots = s.lower()
    return any(k in mots for k in [
        'hub', 'amct', 'cmct', 'lds', 'sauv', 'ua ', 'ua/', 'uhcd',
        'nuit', 'jour', 'sam ', 'we/', 'week-end', 'rééval',
        '8h', '13h', '18h', '8-13', '13-8', '18-8',
    ])

def est_poste_valide(s):
    return est_poste_urg(s) or est_poste_geria(s)

def parse_texte(texte):
    lignes = [l.strip() for l in texte.splitlines() if l.strip()]
    resultats = []
    mois_courant = None
    jour_courant = None
    poste_courant = None

    for ligne in lignes:
        ligne_low = ligne.lower()
        if ligne_low in PARASITES:
            continue
        if any(ligne_low.startswith(p) for p in [
            "du ", "au ", "© ", "gardes urg", "urgences", "sauv été",
            "hopital", "hôpital", "chu ", "gardes gér",
        ]):
            continue
        if re.match(r'^\d+\s+nouvelles?\s+', ligne_low):
            continue
        if ligne in MOIS_FR:
            mois_courant = ligne
            poste_courant = None
            continue
        if mois_courant is None:
            continue
        if re.match(r'^\d{1,2}$', ligne):
            jour_courant = int(ligne)
            poste_courant = None
            continue
        if ligne_low in JOURS_SEMAINE:
            continue
        if est_nom_personne(ligne):
            if poste_courant and jour_courant and mois_courant:
                if ligne.lower() not in NON_ATTRIBUE:
                    resultats.append({
                        "mois": mois_courant,
                        "jour": jour_courant,
                        "poste": poste_courant,
                 
