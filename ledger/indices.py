"""Spectral indices. Pure functions over numpy arrays — no I/O, no side effects.

All functions accept float arrays in surface reflectance (0..1) and a boolean
clear-mask (True = usable pixel). They return per-pixel index arrays with NaN
where the input is unusable, so downstream code can average honestly.
"""
from __future__ import annotations

import numpy as np


def _safe_divide(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.true_divide(num, den)
    out[~np.isfinite(out)] = np.nan
    return out


def _apply_mask(index: np.ndarray, clear: np.ndarray) -> np.ndarray:
    index = index.astype(float)
    index[~clear] = np.nan
    return index


def ndvi(nir: np.ndarray, red: np.ndarray, clear: np.ndarray) -> np.ndarray:
    """Vegetation greenness. Healthy grass ~0.4-0.8; bare soil ~0.1-0.2."""
    return _apply_mask(_safe_divide(nir - red, nir + red), clear)


def ndmi(nir: np.ndarray, swir: np.ndarray, clear: np.ndarray) -> np.ndarray:
    """Vegetation/soil moisture. Tracks with recovery, independent of greenness."""
    return _apply_mask(_safe_divide(nir - swir, nir + swir), clear)


def bare_soil_index(swir: np.ndarray, red: np.ndarray,
                    nir: np.ndarray, blue: np.ndarray,
                    clear: np.ndarray) -> np.ndarray:
    """Bare-soil signal. High values = exposed earth, the reclamation enemy."""
    num = (swir + red) - (nir + blue)
    den = (swir + red) + (nir + blue)
    return _apply_mask(_safe_divide(num, den), clear)


def mean_or_nan(index: np.ndarray) -> float | None:
    """Honest average: NaN if no usable pixels, never a silent zero."""
    with np.errstate(invalid="ignore"):
        m = float(np.nanmean(index))
    return None if np.isnan(m) else m


def clear_fraction(clear: np.ndarray) -> float:
    return float(np.mean(clear)) if clear.size else 0.0
