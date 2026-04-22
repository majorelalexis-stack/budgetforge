"""
Landing polish — 7 améliorations pricing (TDD RED→GREEN)

Source : memory/project_budgetforge_landing_todo.md (22 avril 2026)

Priorité 1 — impression d'inachevé :
  L1.1 — bouton "Redirecting…" remplacé par spinner inline ou garde "Get Pro →"
  L1.2 — Agency enrichi (≥ 4 features : custom rate limits, white-label, SLA, Ollama)

Priorité 2 — impact conversion :
  L2.1 — tagline remplacée par "One flat price. Full control over your LLM spend."
  L2.2 — /month même lisibilité que le prix (pas de text-sm séparé, ou taille explicite)
  L2.3 — Ollama mentionné dans CHAQUE plan (Free/Pro/Agency)

Priorité 3 — trust & polish :
  L3.1 — trust signals (logo Stripe + logos providers) sous la grille
  L3.2 — annual billing toggle ("Annual — save 20%", même grisé)
"""
import os
import re
import pytest


BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_ROOT)
DASHBOARD_ROOT = os.path.join(REPO_ROOT, "dashboard")


def _read_dashboard_file(*rel_path: str) -> str:
    path = os.path.join(DASHBOARD_ROOT, *rel_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def pricing_src() -> str:
    return _read_dashboard_file("components", "pricing-section.tsx")


# ──────────────────────────────────────────────────────────────────────────────
# L1.1 — bouton "Redirecting…" : remplacer ou accompagner d'un spinner
# État : texte "Redirecting…" seul → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestL11RedirectingButton:
    def test_no_bare_redirecting_text(self, pricing_src):
        """Le label 'Redirecting…' seul ne doit plus apparaître comme contenu unique du bouton.

        Accepté : spinner SVG/CSS pendant loading, ou garder le texte CTA + disabled.
        """
        # Cherche le label dans le contexte du bouton Stripe
        match = re.search(
            r'loading\s*===\s*plan\.id\s*\?\s*[\"\']Redirecting…?[\"\']',
            pricing_src,
        )
        assert not match, (
            "Le bouton affiche 'Redirecting…' en texte pur — remplacer par un "
            "spinner inline (SVG animé) ou garder le CTA + disabled."
        )

    def test_spinner_or_loading_indicator_present(self, pricing_src):
        """Un indicateur visuel (spinner SVG, Loader icon, animate-spin) doit exister."""
        patterns = [
            r"animate-spin",               # Tailwind spinner class
            r"<svg[^>]*className=[\"'][^\"']*animate-spin",
            r"Loader2?\b",                 # lucide-react icons
            r"<Loader",
        ]
        found = any(re.search(p, pricing_src) for p in patterns)
        assert found, (
            "pricing-section.tsx doit contenir un indicateur visuel de chargement "
            "(animate-spin, <Loader/>, SVG spinner) pour l'état loading."
        )


# ──────────────────────────────────────────────────────────────────────────────
# L1.2 — Agency : ≥ 4 features spécifiques
# ──────────────────────────────────────────────────────────────────────────────

class TestL12AgencyEnriched:
    def test_agency_has_custom_rate_limits(self, pricing_src):
        """Agency doit mentionner 'Custom rate limits per project'."""
        # Extraire le bloc agency (entre id:"agency" et le closing })
        m = re.search(
            r'id:\s*[\"\']agency[\"\'].*?features:\s*\[(.*?)\]',
            pricing_src,
            re.DOTALL,
        )
        assert m, "Bloc Agency introuvable dans PLANS."
        features = m.group(1).lower()
        assert "custom rate" in features or "rate limit" in features, (
            "Agency doit inclure une feature 'Custom rate limits per project'."
        )

    def test_agency_has_white_label(self, pricing_src):
        m = re.search(
            r'id:\s*[\"\']agency[\"\'].*?features:\s*\[(.*?)\]',
            pricing_src,
            re.DOTALL,
        )
        assert m
        features = m.group(1).lower()
        assert "white" in features or "label" in features, (
            "Agency doit inclure 'White-label proxy URL'."
        )

    def test_agency_has_sla(self, pricing_src):
        m = re.search(
            r'id:\s*[\"\']agency[\"\'].*?features:\s*\[(.*?)\]',
            pricing_src,
            re.DOTALL,
        )
        assert m
        features = m.group(1).lower()
        assert "sla" in features or "dedicated support" in features, (
            "Agency doit inclure 'Dedicated support SLA'."
        )

    def test_agency_features_count_min_4(self, pricing_src):
        m = re.search(
            r'id:\s*[\"\']agency[\"\'].*?features:\s*\[(.*?)\]',
            pricing_src,
            re.DOTALL,
        )
        assert m
        features = m.group(1)
        items = [x for x in re.findall(r"[\"\']([^\"\']+)[\"\']", features) if len(x) > 3]
        assert len(items) >= 4, (
            f"Agency doit avoir au moins 4 features concrètes, trouvé {len(items)} : {items}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# L2.1 — Tagline
# État : "No seat fees. No per-token charges. Just monthly call quotas." → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestL21Tagline:
    def test_new_tagline_present(self, pricing_src):
        """La nouvelle tagline 'One flat price. Full control over your LLM spend.' doit être présente."""
        assert "One flat price" in pricing_src and "LLM spend" in pricing_src, (
            "La tagline doit être 'One flat price. Full control over your LLM spend.' "
            "(cf. project_budgetforge_landing_todo.md P2.1)."
        )

    def test_old_tagline_removed(self, pricing_src):
        """L'ancienne tagline 'No seat fees' ne doit plus être présente."""
        assert "No seat fees" not in pricing_src, (
            "L'ancienne tagline 'No seat fees...' doit être remplacée."
        )


# ──────────────────────────────────────────────────────────────────────────────
# L2.2 — /month même lisibilité que le prix
# ──────────────────────────────────────────────────────────────────────────────

class TestL22PricePeriodReadability:
    def test_period_not_text_sm_muted(self, pricing_src):
        """/month ne doit plus être en text-sm + couleur #c8d8e8 (grisé peu lisible)."""
        # Cherche le motif : la période est dans un <span> avec text-sm ET la couleur grisée
        pattern = r"<span[^>]*text-sm[^>]*#c8d8e8[^>]*>\s*\{plan\.period\}"
        assert not re.search(pattern, pricing_src, re.DOTALL), (
            "/month ne doit plus être text-sm + color #c8d8e8. Passer text-base "
            "ou au moins supprimer le gris pour une meilleure lisibilité."
        )


# ──────────────────────────────────────────────────────────────────────────────
# L2.3 — Ollama dans chaque plan
# État : seul Free mentionne Ollama → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestL23OllamaInEveryPlan:
    @pytest.mark.parametrize("plan_id", ["free", "pro", "agency"])
    def test_plan_mentions_ollama(self, pricing_src, plan_id):
        """Chaque plan doit mentionner Ollama dans ses providers."""
        m = re.search(
            rf'id:\s*[\"\']{plan_id}[\"\'].*?features:\s*\[(.*?)\]',
            pricing_src,
            re.DOTALL,
        )
        assert m, f"Bloc {plan_id} introuvable."
        features = m.group(1).lower()
        assert "ollama" in features, (
            f"Plan '{plan_id}' doit mentionner Ollama (local LLMs, free)."
        )


# ──────────────────────────────────────────────────────────────────────────────
# L3.1 — Trust signals
# État : aucun logo → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestL31TrustSignals:
    def test_stripe_mentioned_outside_checkout_context(self, pricing_src):
        """Stripe doit être mentionné visuellement (logo ou 'Payments secured by Stripe')."""
        # "Payments secured by Stripe" existe déjà — on exige un visuel en plus (logo/img)
        assert re.search(r"stripe", pricing_src, re.IGNORECASE), (
            "pricing-section.tsx doit mentionner Stripe (au moins le texte)."
        )
        # Exige un logo : <img src contenant 'stripe' OU un composant dédié
        has_logo = re.search(
            r"<(?:img|Image)[^>]*(?:stripe|Stripe)[^>]*>|TrustLogos|StripeLogo",
            pricing_src,
        )
        assert has_logo, (
            "pricing-section.tsx doit inclure un logo Stripe visuel "
            "(<Image src='.../stripe...' /> ou composant TrustLogos)."
        )

    def test_provider_logos_present(self, pricing_src):
        """Les providers (OpenAI, Anthropic, Google, DeepSeek, Ollama) doivent être affichés
        sous la grille pricing comme trust signals (pills texte, logos, ou constante PROVIDERS)."""
        required = ["OpenAI", "Anthropic", "Google", "DeepSeek", "Ollama"]
        missing = [p for p in required if p not in pricing_src]
        assert not missing, (
            f"Providers manquants dans pricing-section.tsx : {missing}. "
            "Ajouter une ligne de trust signals sous la grille pricing."
        )


# ──────────────────────────────────────────────────────────────────────────────
# L3.2 — Annual billing toggle
# État : absent → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestL32AnnualBillingToggle:
    def test_annual_toggle_present(self, pricing_src):
        """Un toggle Monthly/Annual doit exister (même grisé / coming soon)."""
        has_annual = re.search(r"\bannual\b", pricing_src, re.IGNORECASE)
        assert has_annual, (
            "pricing-section.tsx doit contenir un toggle 'Monthly / Annual' "
            "(même grisé 'coming soon') pour positionner le produit sérieusement."
        )

    def test_annual_mentions_savings(self, pricing_src):
        """Le toggle Annual doit mentionner une économie ('save 20%' ou similaire)."""
        has_savings = re.search(
            r"(save\s*\d+%|\d+%\s*off|20%)",
            pricing_src,
            re.IGNORECASE,
        )
        assert has_savings, (
            "Le toggle Annual doit mentionner l'économie ('Annual — save 20%')."
        )
