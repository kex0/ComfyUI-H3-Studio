"""Spectrum v0.2.15+ Interop API v1. Same payload Continuum emits; no Continuum dependency."""

SPECTRUM_JOIN_PREFIX = {
    "api": 1,
    "active": True,
    "min_actual_prefix_steps": 2,
}


def attach_spectrum_join_prefix(guider, enabled: bool):
    """Keep the first two Spectrum steps as real H3 evals after a new AV context.

    Copies ``model_options`` so the shared MODEL is not mutated. Clip 1 stays
    on Spectrum's normal schedule. Missing Spectrum is a no-op.
    """
    if not enabled:
        return guider
    options = dict(getattr(guider, "model_options", None) or {})
    transformer = dict(options.get("transformer_options") or {})
    transformer["h3_continuum"] = dict(SPECTRUM_JOIN_PREFIX)
    options["transformer_options"] = transformer
    guider.model_options = options
    return guider
