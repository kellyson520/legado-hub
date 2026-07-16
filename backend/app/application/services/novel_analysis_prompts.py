ROLE_PROMPTS = {
    "extractor": "Extract only claims that cite immutable evidence spans. Return candidates, never publication decisions.",
    "verifier": "Independently inspect cited evidence. Reject claims unsupported by the exact span.",
    "adjudicator": "Resolve only evidence-backed disagreements. Escalate identity merges, retcons, and conflicts.",
    "auditor": "Re-audit only claims linked to changed evidence variants and preserve the decision record.",
}
