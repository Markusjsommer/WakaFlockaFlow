"""Analysis package for the synthetic batch-correction demo.

Modules:
    io        - FCS read/write and marker helpers (flowkit)
    synth     - synthetic drift injection + pseudo-batch construction
    emd       - Earth-Mover-Distance (Wasserstein) per marker
    embed     - UMAP embedding of pooled batches
    cytonorm  - CytoNorm (Docker) engine + pyComBat fallback
"""
