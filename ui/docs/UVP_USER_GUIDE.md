# UVP — unos i ponovno korištenje recepta

Na početnoj stranici otvori **Recipes**. Uređivanje nosi naziv **Procedure Builder**;
UVP ostaje interni razvojni naziv, a tekstovi aplikacije su na engleskom.

1. Odaberi **New recipe**, upiši naziv i po potrebi bilješku te sadržaj boca B1/B2/S.
2. Odaberi radnju i klikni **Add step**. Upiši količinu u mL ili trajanje u sekundama.
3. Strelicama promijeni redoslijed. Korak možeš duplicirati ili ukloniti.
4. Klikni **Save recipe**. To sprema novu verziju u backend biblioteku bez pokretanja.
5. Klikni **Review procedure**. Backend provjerava zadane količine i redoslijed.
   Spremanje provjerava oblik i parametre recepta; ne potvrđuje izvedivost redoslijeda.
   Primjer: dodavanje 2 mL pa prijenos 3 mL može se spremiti, ali pregled ga odbija.
   Backend ponavlja provjeru prije izvršavanja.
6. Pregledaj redoslijed, unesi operatera i novu bilješku o sadašnjoj pripremi te označi potvrde.
7. Tek **Start reviewed procedure** traži izvršavanje kroz postojeći backend.
   Ako adapter traži svježe reference uređaja, slijedi njegov postojeći operaterski obrazac.
8. Prati korak i stanje ispod. STOP, pauza čekanja, nastavak, oporavak i ispiranje koriste postojeće kontrole.

Za ponavljanje odaberi spremljeni recept iz **My Recipes**, ponovno provjeri i
unesi svježe potvrde. **Copy recipe** otvara zaseban nacrt; spremi ga da
postane novi recept. Izmjena parametara uklanja prethodni pregled i potvrde.
Kod konflikta verzije ili sadržaja osvježi biblioteku i ponovno otvori recept.
Pregled i pokretanje provjeravaju i verziju i identitet sadržaja; izmijenjeni recept
ne može se pokrenuti kao prethodno pregledani recept.
Ako skupljanje frakcija traži svježe reference kolone i karusela, pregled to navodi.
Nakon zasebnog pokretanja ispuni postojeći obrazac za sadašnje reference. Bez
poznatih referenci procedura neće početi. Ako izvršni sustav nema put za unos tih
referenci ni potvrđenu spremnost, skupljanje je označeno nedostupnim i Start je blokiran.
Nespremljeni nacrt nije trajno spremljen i gubi se pri izlasku ili osvježavanju stranice.

Sadašnje radnje: dodavanje B1/B2/S u reaktor, pasivno čekanje, prijenos reaktor→SF,
miješanje i taloženje u SF-u, prijenos SF→kolona i vremensko skupljanje frakcija.
Miješanje koristi fiksni profil. Skupljanje frakcija mora biti posljednji korak.
Količine su zadane; stroj nema mjerenje njihova stvarnog protoka ili isporuke.
Svaka nova procedura zahtijeva prazne/pripremljene posude i odgovarajuće boce i posude za frakcije.

Ovaj checkpoint provjeren je softverski s lažnim transportima. Zadana produkcijska
aplikacija ne uključuje izvršni adapter. Postojeći `tests.browser_check` harness
može prikazati UVP s lažnim transportima. Fizičko izvođenje zahtijeva zasebno
odobrenje i pripremljeni profil; provjera s tekućinom ostaje odgođena.

Biblioteka recepata sada koristi shemu v2 s provjerom integriteta sadržaja. Starija
shema v1 ostaje sačuvana i odbija se bez automatske migracije ili popravka. Ako je
već korištena, potrebno je zasebno dogovoriti prijenos sadržaja; nemoj brisati bazu.
Sam oblik procedure i dalje koristi `schema_version: 1`.
