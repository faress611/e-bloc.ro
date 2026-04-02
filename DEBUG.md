# DEBUG.md — Ghid de depanare E-bloc România

Acest ghid te ajută să diagnostichezi și să rezolvi problemele cele mai frecvente ale integrării E-bloc România pentru Home Assistant.

---

## 1. Activarea logurilor detaliate

Adaugă în `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.ebloc: debug
```

Repornește Home Assistant. Logurile vor apărea în **Settings → System → Logs** sau în fișierul `home-assistant.log`.

Prefixul tuturor mesajelor este `[Ebloc:*]`, deci poți filtra cu:

```
[Ebloc:
```

### Prefixe specifice per modul

| Prefix | Modul | Ce loghează |
|--------|-------|-------------|
| `[Ebloc]` | `__init__.py` | Lifecycle integrare (setup, unload, heartbeat) |
| `[Ebloc:API]` | `api.py` | Request-uri HTTP, login, autodiscovery |
| `[Ebloc:Coordinator]` | `coordinator.py` | Cicluri de actualizare, erori fetch |
| `[Ebloc:Sensor]` | `sensor.py` | Creare senzori, erori în proprietăți |
| `[Ebloc:Button]` | `button.py` | Trimitere index/nr. persoane, rezultate API |
| `[Ebloc:Number]` | `number.py` | Creare number selectors |
| `[Ebloc:License]` | `license.py` | Activare, heartbeat, verificare licență |

---

## 2. Situații normale (nu sunt erori)

### Licență — heartbeat

```
[Ebloc:License] Heartbeat OK. Licența este validă (expiră: 2027-01-15).
```

**Cauza**: verificarea periodică a licenței cu serverul a reușit. Comportament normal.

---

## 3. Probleme frecvente

### 2.1 „Autentificare eșuată" la configurare

**Simptom**: ConfigFlow afișează eroarea `auth_failed`.

**Cauze posibile**:
- Email sau parolă greșite.
- Contul e-bloc.ro este blocat sau dezactivat.
- Serverul e-bloc.ro nu răspunde.

**Soluție**:
1. Verifică că poți face login în aplicația mobilă e-bloc.ro cu aceleași credențiale.
2. Verifică logurile pentru detalii: caută `[Ebloc:API]` și `async_login`.
3. Dacă serverul nu răspunde, încearcă mai târziu.

### 2.2 „Autodiscovery eșuat"

**Simptom**: ConfigFlow afișează `autodiscover_failed` sau `no_apartments`.

**Cauze posibile**:
- Contul nu are asociații/apartamente înregistrate.
- Session-ul s-a invalidat între login și autodiscovery.

**Soluție**:
1. Verifică în aplicația mobilă că ai cel puțin o asociație cu apartament.
2. Consultă logurile pentru `[Ebloc:API]` — caută `async_autodiscover`.
3. Încearcă să ștergi și să reconfigurezi integrarea.

### 2.3 Senzorii afișează „Licență necesară"

**Simptom**: Toți senzorii au starea `Licență necesară`.

**Cauze posibile**:
- Nu ai activat o cheie de licență.
- Perioada de evaluare a expirat.
- Licența a fost revocată sau fingerprint-ul nu se potrivește.

**Soluție**:
1. Mergi la **Settings → Devices & Services → E-bloc România → Configure → Licență**.
2. Verifică statusul afișat.
3. Dacă ai o cheie, introdu-o și confirmă activarea.
4. Loguri relevante: caută `[Ebloc:License]` sau `[Ebloc]`.

### 2.4 Butonul „Trimite nr. persoane" returnează eroare

**Simptom**: Logul arată `Eroare trimitere nr. persoane: {'result': 'nok'}`.

**Cauze posibile**:
- **Luna stale** — coordinatorul returnează o lună mai veche (ex. `2026-02`) dar luna curentă e `2026-03`. API-ul refuză lunile închise.
- Numărul de persoane este invalid.

**Soluție**:
Integrarea calculează luna dinamic la fiecare apăsare a butonului. Dacă problema persistă:
1. Verifică logurile: `[Ebloc:Button] Trimit nr. persoane: asoc=..., ap=..., luna=..., nr=...`
2. Confirmă că `luna` este luna curentă (ex. `2026-03`).
3. Dacă luna e stale, forțează un refresh al coordinator-ului (Developer Tools → Services → `homeassistant.update_entity`).

### 2.5 Butonul „Trimite index" nu funcționează

**Simptom**: Log arată `Nu găsesc number entity cu uid=...` sau valoare invalidă.

**Cauze posibile**:
- Number selector-ul nu a fost creat (contorul nu are `right_edit_index = 1`).
- Valoarea din selector e `0` sau `unknown`.

**Soluție**:
1. Verifică că number entity-ul există: `number.ebloc_{UserID}_index_{titlu}_selector`.
2. Setează o valoare validă (mai mare decât indexul vechi) înainte de a apăsa butonul.
3. Verifică `Drept editare = Da` în atributele senzorului index corespunzător.

### 2.6 Senzorul „Citire permisă" arată „Nu" deși ar trebui „Da"

**Simptom**: Știi că e perioadă de citire dar senzorul e pe `Nu`.

**Cauze posibile**:
- Datele `indecsi_start` / `indecsi_end` din API nu acoperă data curentă.
- Diferență de fus orar.

**Soluție**:
1. Verifică atributele senzorului: `Perioadă start` și `Perioadă sfârșit`.
2. Compară cu data curentă a serverului HA.
3. Dacă datele lipsesc, se folosește fallback-ul `can_edit_index` din API.

### 2.7 Coordinator eșuează la actualizare

**Simptom**: Loguri cu `UpdateFailed` sau `Eroare neașteptată`.

**Cauze posibile**:
- Sesiunea API a expirat și re-autentificarea a eșuat.
- Serverul e-bloc.ro e indisponibil.
- Probleme de rețea.

**Soluție**:
1. Verifică logurile: `[Ebloc:Coordinator]` și `[Ebloc:API]`.
2. Dacă e problemă de sesiune, integrarea încearcă re-autentificarea automat.
3. Dacă serverul e-bloc.ro e down, așteaptă — coordinatorul va reîncerca la următorul interval.

### 2.8 Licență invalidă

**Simptom**: Toți senzorii arată `Licență necesară` deși ai introdus o cheie.

**Cauze posibile**:
- Cheia de licență este greșită sau incompletă.
- Perioada de evaluare a expirat și nu ai activat o licență.
- Licența a fost revocată.
- Fingerprint-ul dispozitivului nu se potrivește.

**Rezolvare**:
1. Mergi la **Settings → Devices & Services → E-bloc România → Configure → Licență**.
2. Verifică statusul afișat (Evaluare X zile / Licență activă / Licență expirată).
3. Dacă a expirat perioada de evaluare, achiziționează o licență de la [hubinteligent.org/licenta/ebloc](https://hubinteligent.org/licenta/ebloc).
4. Dacă ai o licență dar arată ca invalidă, reintroduceți cheia și confirmă.

---

## 4. Diagnosticare integrată

Home Assistant oferă export de diagnosticare automat:

**Settings → Devices & Services → E-bloc România → ⋮ → Download diagnostics**

Fișierul JSON conține:
- Informații licență (fingerprint, status — fără cheia completă).
- Starea coordinator-ului (ultimul update, interval, apartamente).
- Lista entităților active (senzori, butoane, number entities).
- Email mascat (ex. `u*********@exemplu.ro`).

Atașează acest fișier la orice issue pe GitHub.

---

## 5. Resetarea completă

Dacă integrarea este într-o stare irecuperabilă:

1. **Settings → Devices & Services → E-bloc România → ⋮ → Delete**.
2. Repornește Home Assistant.
3. Adaugă integrarea din nou: **Settings → Devices & Services → Add Integration → E-bloc România**.

Aceasta va:
- Elimina toate entitățile asociate.
- Notifica serverul de licențiere despre dezinstalare.
- Curăța datele runtime complet.

---

## 6. Verificări rapide prin Developer Tools

### Starea unui senzor
**Developer Tools → States** → caută `ebloc`

### Forțare actualizare
**Developer Tools → Services** → `homeassistant.update_entity` → selectează entitatea dorită.

### Apelarea unui buton
**Developer Tools → Services** → `button.press` → `button.ebloc_{UserID}_trimite_index_...`

### Verificare number selector
**Developer Tools → States** → caută `number.ebloc_` → verifică `state` (valoarea curentă).

---

## 7. Raportarea unui bug

Deschide un issue pe [GitHub](https://github.com/cnecrea/e-bloc.ro/issues) cu:

1. **Versiunea integrării** (din `manifest.json` → `version`).
2. **Versiunea Home Assistant** (Settings → About).
3. **Fișierul de diagnosticare** (vezi secțiunea 3).
4. **Logurile relevante** (cu `debug` activat — vezi secțiunea 1).
5. **Pași de reproducere** — ce ai făcut, ce te așteptai, ce s-a întâmplat.

Nu include parole, chei de licență sau date personale în raport.
