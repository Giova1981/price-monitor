import os
import requests
import json

API_KEY = os.environ["TINYFISH_API_KEY"]

URL = "https://api.search.tinyfish.ai"

RICERCHE = [
    'site:farmasave.it "Sun Secure Eau Solaire SPF50"',
    'site:farmasave.it "Supradyn Ricarica" "60 compresse"',
    'site:farmasave.it "Citoethyl"'
]

headers = {
    "X-API-Key": API_KEY
}

for ricerca in RICERCHE:

    print("\n" + "=" * 80)
    print("RICERCA:")
    print(ricerca)
    print("=" * 80)

    try:

        risposta = requests.get(
            URL,
            headers=headers,
            params={"query": ricerca},
            timeout=30
        )

        print("HTTP status:", risposta.status_code)
        print("Content-Type:", risposta.headers.get("content-type"))

        if risposta.status_code != 200:
            print("ERRORE:")
            print(risposta.text[:1000])
            continue

        dati = risposta.json()

        risultati = dati.get("results", [])

        print("Risultati ricevuti:", len(risultati))

        for i, risultato in enumerate(risultati[:10], 1):

            print("\n--- RISULTATO", i, "---")

            print("Titolo:")
            print(risultato.get("title", ""))

            print("\nSito:")
            print(risultato.get("site_name", ""))

            print("\nURL:")
            print(risultato.get("url", ""))

            print("\nSnippet:")
            print(risultato.get("snippet", ""))

    except requests.RequestException as errore:

        print("ERRORE REQUEST:", errore)

    except json.JSONDecodeError:

        print("ERRORE: la risposta non è JSON")
        print(risposta.text[:1000])

print("\n" + "=" * 80)
print("DIAGNOSTICA TINYFISH TERMINATA")
print("=" * 80)
