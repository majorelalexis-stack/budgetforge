# BudgetForge — Plan Monétisation
> 2026-04-21 | Objectif : passer de gratuit à payant avec Stripe

## État actuel (audit vérifié)
- Aucun Stripe, zéro package installé
- Aucun champ `plan` ou `tier` dans les modèles
- Architecture : 1 admin → gère des Projects (chacun avec sa propre API key)
- Pas de pricing page, pas de page d'inscription
- Members system existe mais pas lié aux Projects

## Architecture de monétisation retenue

**Le client = un Project.** Chaque acheteur crée un Project qui a son propre API key de proxy.
Il n'a pas besoin de compte dashboard pour utiliser le proxy — il utilise juste son API key.

Flow complet :
```
Visiteur → Pricing page → Stripe Checkout
→ Webhook → crée Project(plan=pro) → envoie email avec API key
→ Client configure son outil LLM → utilise /proxy/openai/...
```

Pas de compte/login client en V1. Dashboard admin reste pour Alexis seulement.

---

## Tiers

| Plan | Prix | Calls/mois | Projets | Features |
|---|---|---|---|---|
| **Free** | $0 | 5 000 | 1 | Alertes email, 1 provider |
| **Pro** | $29/mois | 100 000 | 10 | Tous providers, webhooks, export |
| **Agency** | $79/mois | 500 000 | illimités | Tout + priorité support |
| **LTD** | $69 one-time | = Pro lifetime | 10 | AppSumo — plus tard |

---

## Phase 1 — Modèle de données (1 jour)
**Priorité absolue — tout le reste dépend de ça.**

### Backend
- [ ] Migration Alembic : ajouter sur `Project`
  - `plan` VARCHAR default `"free"` (valeurs : `free` / `pro` / `agency` / `ltd`)
  - `stripe_customer_id` VARCHAR nullable
  - `stripe_subscription_id` VARCHAR nullable
  - `calls_this_month` INTEGER default 0 (compteur mensuel)
  - `calls_reset_at` DATETIME nullable
- [ ] Logique enforcement dans `proxy.py` : avant `_check_budget`, vérifier quota calls
  - Free : bloquer si calls_this_month >= 5 000
  - Pro : bloquer si calls_this_month >= 100 000
  - Agency : bloquer si calls_this_month >= 500 000
  - Reset automatique chaque 1er du mois
- [ ] Route `GET /api/projects/{id}/plan` — retourne plan + calls used + limit
- [ ] Tests TDD : quota enforced, reset mensuel, plan=agency non bloqué

### Frontend
- Rien à faire en Phase 1

---

## Phase 2 — Stripe Checkout (2 jours)
**Objectif : accepter le premier paiement.**

### Backend
- [ ] `pip install stripe` + variable env `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET`
- [ ] Créer les 2 Price IDs dans Stripe Dashboard (Pro $29/mois, Agency $79/mois)
- [ ] Route `POST /api/checkout/{plan}` (plan = `pro` | `agency`)
  - Crée une Stripe Checkout Session
  - Success URL : `https://llmbudget.maxiaworld.app/success?session={CHECKOUT_SESSION_ID}`
  - Cancel URL : `https://llmbudget.maxiaworld.app/#pricing`
  - Retourne `{checkout_url: "..."}`
- [ ] Route `POST /webhook/stripe` (pas d'auth admin, signature Stripe)
  - Event `checkout.session.completed` :
    1. Crée un nouveau Project (name=email client, plan=pro/agency)
    2. Stocke stripe_customer_id + stripe_subscription_id sur le Project
    3. Envoie email au client avec son API key (via AlertService ou SMTP direct)
  - Event `customer.subscription.deleted` : passe le Project en plan=free
  - Event `invoice.payment_failed` : log + email warning
- [ ] Tests TDD : webhook completed → project créé, webhook deleted → plan downgrade

### Frontend
- Rien ici — les boutons seront ajoutés en Phase 3

---

## Phase 3 — Pricing page (1 jour)
**Objectif : convertir les visiteurs.**

### Frontend seulement
- [ ] Section `#pricing` sur la landing page (`app/page.tsx`)
  - 3 cartes : Free / Pro $29/mois / Agency $79/mois
  - Features listées par plan
  - Bouton "Get Pro" → `POST /api/checkout/pro` → redirect vers Stripe Checkout URL
  - Bouton "Get Agency" → idem pour agency
  - Bouton "Try Free" → scroll vers section setup rapide
- [ ] Page `app/success/page.tsx`
  - Message : "Paiement reçu — vérifiez votre email pour votre API key"
  - Pas de dashboard client en V1 (trop complexe)
- [ ] Header landing : ajouter lien "Pricing" dans la nav

### Backend
- Rien de plus — les routes checkout sont déjà créées en Phase 2

---

## Phase 4 — Email d'onboarding (0.5 jour)
**Objectif : que le client sache quoi faire avec son API key.**

### Backend
- [ ] Template email d'onboarding post-paiement :
  - "Bienvenue sur BudgetForge Pro"
  - Votre API key : `bf-xxxxxxxxxxxx`
  - Comment l'utiliser : remplacer `api.openai.com` par `llmbudget.maxiaworld.app/proxy/openai`
  - Lien doc (README ou page docs)
- [ ] Envoyer depuis le webhook `checkout.session.completed`
- [ ] Test manuel : déclencher un faux webhook et vérifier l'email reçu

---

## Phase 5 — AppSumo LTD (1 jour) — PLUS TARD
> À faire après que Phase 1-4 fonctionnent et que le produit tourne en prod.

### Backend
- [ ] Modèle `LicenseCode` : `code` (unique), `plan` ("ltd"), `redeemed_by_project_id` (nullable), `redeemed_at`
- [ ] Route `POST /api/redeem` (public, pas d'auth admin)
  - Vérifie que le code existe et n'a pas été utilisé
  - Crée un Project avec plan=ltd (= Pro lifetime)
  - Envoie email avec API key
- [ ] Script `generate_codes.py` : génère N codes pour batch AppSumo

### Frontend
- [ ] Page `app/redeem/page.tsx` : formulaire email + code → POST /api/redeem → affiche API key

---

## Ordre d'exécution

```
Phase 1 (1j) → Phase 2 (2j) → Phase 3 (1j) → Phase 4 (0.5j) → go live
                                                                    ↓
                                                               Phase 5 (1j) quand AppSumo ready
```

**Total estimé : 4.5 jours de dev pour être live et payant.**

---

## Variables d'environnement à ajouter (VPS)

```
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRO_PRICE_ID=price_...
STRIPE_AGENCY_PRICE_ID=price_...
```

## Décisions techniques arrêtées
- **Stripe** (pas Lemon Squeezy) — meilleur SDK Python, webhook plus simple
- **Project = Customer** — pas de compte utilisateur séparé en V1
- **Email onboarding via SMTP** déjà configuré sur le VPS
- **Pas de customer dashboard en V1** — trop coûteux à build, ajouter en V2 si demande

## Ce plan ne fait PAS (out of scope)
- Customer dashboard (login, voir sa conso)
- Downgrade automatique du plan (just block calls, pas de changement de plan)
- Multi-seat (une personne = un projet pour l'instant)
- Facturation pro-rata ou pauses d'abonnement
