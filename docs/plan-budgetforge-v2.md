# BudgetForge — Plan V2 (21 avril 2026)

## État actuel (fin session 21 avril)

**88 tests verts.** Backend complet : proxy 5 providers, enforcement block/downgrade, usage tracking, history paginée. Dashboard : Overview, Projects, Activity (table pro), Settings. CORS fixé via Next.js proxy rewrites.

---

## Phases V2

### PHASE 1 — Bugs critiques (bloquants prod)

**P1.1 — Streaming support**
- Problème : le proxy lit la réponse complète avant de renvoyer → apps streaming cassées, tokens mal comptés
- Fix : SSE pass-through avec `httpx.stream()`, compter tokens sur `usage` chunk final (OpenAI) ou header (Anthropic)
- TDD : test avec mock SSE qui envoie 3 chunks + chunk final avec usage

**P1.2 — Alertes email réellement déclenchées**
- Problème : `alert_service.py` existe mais n'est jamais appelé dans le flow proxy
- Fix : appeler `alert_service.send_threshold_alert()` dans `budget_guard.py` quand `pct_used >= alert_threshold_pct`
- TDD : mock SMTP, vérifier qu'il est appelé exactement une fois par franchissement de seuil (pas à chaque call)

**P1.3 — Reset budget mensuel**
- Problème : l'usage s'accumule lifetime → budget $10/mois bloqué définitivement après 1 mois
- Fix : ajouter `reset_period` (monthly/weekly/none) + `reset_day` sur Project. Cron ou lazy reset au moment du check.
- TDD : test reset mensuel, test que les appels post-reset ne comptent pas l'historique

---

### PHASE 2 — Fonctionnalités haute valeur

**P2.1 — Cap par appel unique**
- Champ `max_cost_per_call_usd` sur Project
- Avant de forwarder : estimer coût (tokens_in connus via header ou body) → si > cap → 429
- TDD : test block si prompt trop long, test pass si en-dessous

**P2.2 — Prévision de dépassement**
- Calcul : `burn_rate = used_usd / days_elapsed` → `days_until_empty = remaining / burn_rate`
- Endpoint : inclus dans `/api/projects/{id}/usage` (champ `forecast_days`)
- Dashboard : widget "Budget épuisé dans X jours" sur la page projet et Overview

**P2.3 — Webhook alerts**
- Champ `webhook_url` sur Project (optionnel)
- POST JSON `{project, provider, model, pct_used, used_usd, budget_usd, event: "threshold"|"exceeded"}` quand seuil franchi
- Plus utile que SMTP pour les devs (Slack, Discord, n8n, etc.)

**P2.4 — Tracking par agent**
- Header optionnel `X-BudgetForge-Agent: my-agent-name` dans les appels proxy
- Stocker `agent` dans Usage (nouvelle colonne)
- Endpoint `/api/projects/{id}/usage/breakdown?group_by=agent`
- Dashboard : onglet "Agents" dans la page projet

**P2.5 — Régénération de clé API**
- Endpoint `POST /api/projects/{id}/rotate-key`
- Dashboard : bouton "Rotate key" avec confirmation modale dans la page projet
- TDD : vérifier que l'ancienne clé est invalidée

---

### PHASE 3 — Dashboard UX

**P3.1 — Page projet — breakdown provider**
- Graphique donut providers (comme Overview) mais filtré par projet
- Already designed — juste pas implémenté

**P3.2 — Filtres temporels Overview**
- Sélecteur : "Ce mois", "7 jours", "Aujourd'hui", "All time"
- Changer les API calls pour passer `date_from` en conséquence

**P3.3 — Toasts de confirmation**
- Créer projet ✓, budget sauvé ✓, clé copiée ✓, clé régénérée ✓
- Composant `<Toast>` léger (pas shadcn — custom pour rester dans l'aesthetic amber)

**P3.4 — Aucun appel / état onboarding**
- Sur Overview : si 0 projets → page d'onboarding avec snippet d'intégration 3 étapes
- Remplace les stats cards vides par un guide visuel

---

### PHASE 4 — Dette technique

**P4.1 — Alembic migrations**
- Initialiser Alembic, créer migration initiale
- Obligatoire avant deploy VPS — sinon ajout de colonnes casse les DBs existantes

**P4.2 — `datetime.utcnow()` → `datetime.now(UTC)`**
- Python 3.12+ deprecation warning sur tous les modèles
- Remplacement mécanique + test que les timestamps sont timezone-aware

**P4.3 — Rate limiting dashboard API**
- `slowapi` sur les endpoints `/api/projects` (pas les proxys — eux ont déjà enforcement budget)
- Limite : 60 req/min par IP

**P4.4 — `pydantic` class-based config → `model_config`**
- Warning V2 dans `core/config.py` — migration triviale

---

### PHASE 5 — Deploy

**P5.1 — Backend VPS port 8011**
- systemd service + venv + nginx reverse proxy
- `.env` avec vraies clés API
- Alembic `upgrade head` au démarrage

**P5.2 — Dashboard**
- `npm run build` → `next start` ou export statique
- `NEXT_PUBLIC_API_URL` → URL VPS

**P5.3 — Domaine**
- `budget.maxiaworld.app` → DNS + nginx SSL (Let's Encrypt)

---

## Priorité absolue prochaine session

```
P1.1 (streaming) → P1.2 (alertes) → P1.3 (reset) → P2.2 (forecast) → P3.1 (projet breakdown) → P3.3 (toasts)
```

---

## Compteurs

| Phase | Tests attendus | Statut |
|-------|---------------|--------|
| P1 (bugs critiques) | +20 tests | ☐ |
| P2 (features) | +35 tests | ☐ |
| P3 (UX) | 0 tests (frontend) | ☐ |
| P4 (dette) | +5 tests | ☐ |
| **Total cible** | **~148 tests** | |

Actuellement : **88 tests verts**.
