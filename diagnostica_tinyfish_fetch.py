import os
import requests
import json

API_KEY = os.environ["TINYFISH_API_KEY"]

ENDPOINT = "https://api.fetch.tinyfish.ai"

URLS = [
    "https://www.farmasave.it/sun-secure-eau-solaire-spf50.html",
    "https://www.farmasave.it/supradyn-ricarica-integratore-di-vitamine-e-sali-minerali-60-compresse-rivestite.html",
    "https://www.farmasave.it/citoethyl-3fl-15ml.html"
]

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

payload = {
    "urls": URLS,
    "format": "markdown"
}

print("=" * 80)
print("DIAGNOSTICA TINYFISH FETCH")
print("=" * 80)

try:

    risposta = requests.post(
        ENDPOINT,
        headers=headers,
        json=payload,
        timeout=120
    )

    print("\nHTTP status:", risposta.status_code)
    print("Content-Type:", risposta.headers.get("content-type"))

    if risposta.status_code != 200:

        print("\nERRORE API:")
        print(risposta.text[:3000])
        raise SystemExit(1)

    dati = risposta.json()

    risultati = dati.get("results", [])
    errori = dati.get("errors", [])

    print("\nPagine recuperate:", len(risultati))
    print("Errori:", len(errori))

    for numero, pagina in enumerate(risultati, 1):

        print("\n")
        print("=" * 80)
        print(f"RISULTATO {numero}")
        print("=" * 80)

        print("URL:")
        print(pagina.get("url", ""))

        print("\nURL finale:")
        print(pagina.get("final_url", ""))

        print("\nTitolo:")
        print(pagina.get("title", ""))

        print("\nFormato:")
        print(pagina.get("format", ""))

        testo = pagina.get("text", "")

        print("\nLunghezza contenuto:", len(testo))

        print("\n--- CONTENUTO ESTRATTO ---")
        print(testo[:10000])

        print("\n--- FINE CONTENUTO ---")

    if errori:

        print("\n")
        print("=" * 80)
        print("ERRORI FETCH")
        print("=" * 80)

        for errore in errori:
            print(json.dumps(
                errore,
                indent=2,
                ensure_ascii=False
            ))

except requests.RequestException as errore:

    print("\nERRORE REQUEST:")
    print(errore)

except json.JSONDecodeError:

    print("\nERRORE: TinyFish non ha restituito JSON.")
    print(risposta.text[:3000])

print("\n")
print("=" * 80)
print("DIAGNOSTICA TERMINATA")
print("=" * 80)
