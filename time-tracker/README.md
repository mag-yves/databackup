# Suivi du temps — DataBackup

Journal des sessions de développement, tenu avec la commande `devtime`.

## Fichiers

- `log.json` — source de vérité : liste des sessions (une entrée par session).

## Format

```json
{
  "project": "databackup",
  "sessions": [
    {
      "id": "S-2026-01-01-01",
      "start": "2026-01-01T09:00:00+01:00",
      "end": "2026-01-01T11:30:00+01:00",
      "seconds": 9000,
      "note": "objet de la session"
    }
  ]
}
```

- Une session **en cours** a `"end": null` (et `"seconds": null`).
- Heures en heure locale, au format ISO 8601 avec décalage.
- Plusieurs sessions par jour : autant d'entrées que nécessaire.
- La note reprend le titre de session (`databackup · <objet>`), pour la traçabilité.

## Usage

Depuis OpenCode (commandes projet) :

- `/time-start` — ouvre une session
- `/time-stop` — clôt la session ouverte
- `/time-status` — session en cours + total du jour
- `/time-report` — totaux par jour

En ligne de commande : `devtime start|stop|status|report`.
