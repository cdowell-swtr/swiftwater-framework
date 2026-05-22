"""Framework integrity engine — verifies generated-project scaffolding is intact.

Lives in the installed CLI (not in scaffolded project code) so a builder cannot
disable the check by editing project files (spec §17).
"""
