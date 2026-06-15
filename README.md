# TianDe RETENCE vs zbytek světa

Samostatný report mimo strukturu hlavního reportingu.

## Co to dělá

- bere order fact z `reporting-v2`
- počítá denní tržby od `2026-05-01`
- rozděluje je na:
  - `RETENCE` = zákazník měl před daným dnem už dřívější objednávku
  - `zbytek světa` = první zachycená objednávka zákazníka
- drží `CZ` a `SK` zvlášť
- vylučuje `Pokladna`
- generuje:
  - `site/index.html`
  - `site/denni_trzby_retence_vs_zbytek_2026-05-01_plus_cz_sk_bez_pokladen.csv`
  - `site/denni_trzby_retence_vs_zbytek_latest.csv`
  - `site/latest.json`

## Ruční refresh

```bash
python3 scripts/build_report.py
```

## Automatický refresh

Je nastavený přes launchd každou hodinu.

Důležité: build skript po změně automaticky commitne a pushne `docs/` a `site/`, takže se GitHub Pages opravdu aktualizuje i bez ručního pushnutí.
