import numpy as np

# Monkey-patch
if not hasattr(np.lib, "function_base"):
    try:
        from numpy import trapz, histogram, percentile  # add 'trapz', 'histogram', 'percentile'
        np.lib.function_base = type("function_base", (), {
            "trapz": trapz,
            "histogram": histogram,
            "percentile": percentile,
        })()
    except ImportError:
        print("Error")

# Monkey-patch: add 'alltrue' to numpy if missing
if not hasattr(np, 'alltrue'):
    np.alltrue = np.all