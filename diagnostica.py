import requests
import re

URLS = [
    {
        "nome": "Sun Secure Eau Solaire SPF50+ 200 ml",
        "url": "https://www.trovaprezzi.it/prezzo_prodotti-solari_sun_secure_eau_solaire_spf50%242b_svr_200ml.aspx"
    },
    {
        "nome": "Supradyn Ricarica 60 compresse",
        "url": "https://www.trovaprezzi.it/prezzo_integratori-coadiuvanti_supradyn_ricarica_integratore_multivitaminico_compresse_60.aspx"
    },
    {
        "nome": "Citoethyl 3 flaconi 15 ml",
        "url": "https://www.trovaprezzi.it/prezzo_integratori-coadiuvanti_3_citozeatec_citoethyl_15ml.aspx"
    }
]

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "it-IT,it;q=0.9"
}


for prodotto in URLS:

    print("\n" + "=" * 70)
    print(prodotto["nome"])
    print("=" * 70)

    try:

        risposta = requests.get(
            prodotto["url"],
            headers=HEADERS,
            timeout=30
        )

        print("HTTP status:", risposta.status_code)
        print("Dimensione:", len(risposta.content), "byte")

        html = risposta.text

        print(
            "Farmasave presente:",
            "SI" if "Farmasave" in html else "NO"
        )

        prezzi = re.findall(
            r"\d{1,3}[,.]\d{2}\s*€",
            html
        )

        print("Prezzi trovati:", prezzi[:20])

        posizione = html.lower().find("farmasave")

        if posizione != -1:

            estratto = html[
                max(0, posizione - 1000):
                posizione + 3000
            ]

            estratto = re.sub(
                r"\s+",
                " ",
                estratto
            )

            print("\n--- ESTRATTO FARMASAVE ---")
            print(estratto[:4000])

        else:

            print(
                "\nATTENZIONE: Farmasave non trovato "
                "nel contenuto della pagina."
            )

    except requests.RequestException as errore:

        print("ERRORE:", errore)


print("\nDiagnostica completata.")
