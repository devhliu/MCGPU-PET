# MCGPU-PET Design Document: From Imaging to Dosimetry

**Version:** 1.0  
**Date:** 2026-02-24  
**Status:** Reference Design  
**Codebase:** MCGPU-PET v0.1 (based on MC-GPU v1.3)

---

## 1. Introduction

MCGPU-PET occupies a unique position at the intersection of **PET imaging simulation** and **internal dosimetry**. While its primary purpose is to generate realistic PET detector data (sinograms and phase space files), it simultaneously tracks photon energy deposition, providing the foundation for absorbed dose computation. This document describes how both capabilities coexist, the current limitations of each, and the technical pathway for evolving into a full dosimetry platform.

---

## 2. Dual-Purpose Architecture

```
                   ┌─────────────────────────────────┐
                   │     VOXELIZED PHANTOM            │
                   │  material + density + activity   │
                   └──────────────┬──────────────────┘
                                  │
                   ┌──────────────▼──────────────────┐
                   │     POSITRON ANNIHILATION        │
                   │  511 keV back-to-back photon pair│
                   └──────────────┬──────────────────┘
                                  │
                   ┌──────────────▼──────────────────┐
                   │     PHOTON TRANSPORT (GPU)       │
                   │  Woodcock + Compton/Rayleigh/PE  │
                   └──────┬───────────────┬──────────┘
                          │               │
              ┌───────────▼───┐   ┌───────▼──────────┐
              │  IMAGING PATH │   │  DOSIMETRY PATH  │
              │               │   │                  │
              │ • Escape det. │   │ • Interaction    │
              │ • Energy blur │   │ • Energy deposit │
              │ • Coincidence │   │ • Voxel tally    │
              │ • PSF/Sinogram│   │ • Material tally │
              └───────────────┘   └──────────────────┘
```

Both pathways are evaluated during every photon transport step. They are not mutually exclusive — every simulated photon contributes to both imaging and dosimetry tallies.

---

## 3. The Imaging Path

### 3.1 Current Capabilities

The imaging pipeline produces detector-level data that can feed reconstruction algorithms:

| Feature | Implementation | Status |
|---|---|---|
| Annihilation source | Per-voxel activity sampling, exponential decay | ✅ Complete |
| Acollinearity | Gaussian (σ=0.21276°) | ✅ Complete |
| Photon transport | Woodcock delta-scattering | ✅ Complete |
| Energy resolution | Gaussian blurring at detection | ✅ Complete |
| Energy window | User-defined [Elow, Ehigh] | ✅ Complete |
| Coincidence detection | Sequential 2-photon tracking | ✅ Complete |
| True/Scatter separation | Scatter state tracking (index1) | ✅ Complete |
| PSF output | Full coincidence event list | ✅ Complete |
| Sinogram output | Binned (radial × angular × axial) | ✅ Complete |
| Back-projected image | LOR midpoint image | ✅ Complete |
| Time-of-flight | Travel time recorded in PSF | ✅ Partial |
| Randoms estimation | Background mode (flag=0) | ✅ Complete |

### 3.2 Detector Model

The detector is modeled as a simple cylinder with no explicit crystal structure:

```
Cylindrical shell:
  Radius:  PSF_radius (e.g., 32.8 cm)
  Height:  PSF_height (e.g., 12.656 cm)
  Center:  PSF_center (x, y, z)
  
  Rows:    num_rows (e.g., 80 rings)
  Columns: crystals_per_ring (e.g., 336 crystals)
```

Photon detection occurs when the photon trajectory intersects the cylinder surface. The intersection point determines the crystal index (row from z-coordinate, column from azimuthal angle).

### 3.3 Sinogram Geometry

The sinogram uses Michelogram compression with configurable:
- **SPAN**: Axial compression factor (odd integer ≥ 1)
- **MRD**: Maximum ring difference
- **Radial bins**: Transaxial sampling
- **Angular bins**: Azimuthal sampling

---

## 4. The Dosimetry Path

### 4.1 Current Capabilities

| Feature | Implementation | Status |
|---|---|---|
| KERMA approximation | Energy deposited at interaction site | ✅ Complete |
| Voxel-level dose | 3D dose map with uncertainty | ✅ Complete |
| Material-level dose | Per-material average dose | ✅ Complete |
| ROI selection | Configurable dose tally region | ✅ Complete |
| Statistical uncertainty | Relative error per voxel | ✅ Complete |
| Compton dose | Electron KE deposited locally | ✅ Complete |
| Photoelectric dose | Full photon energy deposited | ✅ Complete |

### 4.2 KERMA Dose Model (Current)

The current dose model uses the **KERMA (Kinetic Energy Released per unit MAss)** approximation:

```
For each photon interaction:
  ┌──────────────────────────────────────────────────────┐
  │ Compton: E_deposited = E_photon_in - E_photon_out   │
  │          (= kinetic energy of recoil electron)       │
  │                                                      │
  │ Photoelectric: E_deposited = E_photon                │
  │          (full absorption)                           │
  │                                                      │
  │ Rayleigh: E_deposited = 0                            │
  │          (elastic, no energy transfer)               │
  └──────────────────────────────────────────────────────┘
  
  Dose_voxel += E_deposited                  (eV)
  Dose_material += E_deposited / mass        (eV/g)
```

### 4.3 KERMA Limitations

The KERMA approximation is valid when:
- Secondary electron ranges are short compared to voxel dimensions
- Charged particle equilibrium (CPE) exists locally

For 511 keV photons:
- Compton electrons have maximum energy ~341 keV
- Electron CSDA range in water at 341 keV ≈ 0.9 mm
- For voxel sizes ≥ 1 mm, KERMA is reasonable for bulk tissue
- At tissue interfaces (bone/air, tissue/lung), KERMA breaks down

| Scenario | KERMA Validity | Notes |
|---|---|---|
| Uniform soft tissue | Good | CPE approximately holds |
| Large voxels (>2mm) | Good | Electron range << voxel |
| Tissue-bone interface | Poor | Density discontinuity breaks CPE |
| Tissue-air interface | Poor | Electrons travel far in air |
| Small organs / thin layers | Poor | Sub-millimeter structures |
| High-Z materials (contrast) | Poor | Photoelectron range matters |

---

## 5. Bridging Imaging and Dosimetry

### 5.1 Shared Physics

Both the imaging and dosimetry paths benefit from the same physics engine:

```
┌─────────────────────────────────────────────────────────┐
│                 SHARED TRANSPORT ENGINE                   │
│                                                          │
│  Woodcock tracking ──► Compton (GCOa)                   │
│                    ──► Rayleigh (GRAa)                   │
│                    ──► Photoelectric                     │
│                                                          │
│  Every interaction simultaneously provides:              │
│  • Scattered photon → continues to detector (IMAGING)    │
│  • Deposited energy → tallied to dose map (DOSIMETRY)   │
└─────────────────────────────────────────────────────────┘
```

### 5.2 What Imaging Adds to Dosimetry

PET imaging simulation produces activity maps that drive dosimetry:

1. **Reconstructed images** → Activity concentration per voxel
2. **Time-activity curves** → Cumulated activity (integration over time)
3. **Scatter correction** → More accurate activity quantification
4. **Attenuation correction** → Realistic photon fluence

A validated imaging simulation enables:
- Testing dosimetry protocols with known ground truth
- Evaluating the impact of image reconstruction on dose estimates
- End-to-end simulation from decay to dose

### 5.3 What Dosimetry Adds to Imaging

Dose information enriches the imaging simulation by:
- Validating that the physics engine correctly conserves energy
- Enabling radiation protection assessments for PET scanning
- Providing organ-level dose estimates from the simulation
- Benchmarking against published dose conversion factors

---

## 6. Pathway from KERMA to Full Dosimetry

### 6.1 Level 1: Enhanced KERMA (Near-term)

**Goal:** Improve dose accuracy without fundamentally changing the transport model.

| Enhancement | Effort | Impact |
|---|---|---|
| Dose-to-medium → Dose-to-water | Low | Better biological relevance |
| Mass energy-absorption coefficients | Low | More accurate KERMA factors |
| Density correction at interfaces | Medium | Improved boundary accuracy |
| Multiple scattering dose accumulation | Low | Already implemented; verify |

### 6.2 Level 2: Electron Dose Kernels (Medium-term)

**Goal:** Account for electron transport using pre-computed dose point kernels (DPK).

```
For each Compton/PE interaction:
  1. Determine electron energy and direction
  2. Look up pre-computed dose spread kernel
  3. Distribute dose to neighboring voxels using kernel

  ┌─────────────────┐
  │ Interaction at   │     ┌─────────────────┐
  │ voxel (i,j,k)   │────►│ Dose Point      │
  │ E_electron=300keV│     │ Kernel (DPK)    │
  └─────────────────┘     │ for 300keV in    │
                           │ water           │
                           │                 │
                           │ → spread to 27  │
                           │   neighboring   │
                           │   voxels        │
                           └─────────────────┘
```

**Requirements:**
- Pre-computed DPK library for relevant energies and materials
- GPU-side kernel lookup and application
- Voxel neighbor access pattern (already available via `locate_voxel()`)

### 6.3 Level 3: Full Electron Transport (Long-term)

**Goal:** Track secondary electrons explicitly using condensed-history Monte Carlo.

This is the full dose computation approach, described in detail in the [Photon-Electron Roadmap](06_Photon_Electron_Roadmap.md).

---

## 7. Current Code Integration Points

### 7.1 Dose Tallying Functions

**Voxel dose (`tally_voxel_energy_deposition`):**
```
Input:  voxel_index, deposited_energy
Action: atomicAdd(dose_array[voxel_index], energy)
        atomicAdd(dose_squared_array[voxel_index], energy²)
```

**Material dose (`tally_materials_dose`):**
```
Input:  material_index, deposited_energy
Action: atomicAdd(materials_dose[material], energy)
        atomicAdd(materials_dose_squared[material], energy²)
```

Both functions store the sum and sum-of-squares for computing mean and standard error.

### 7.2 Interface Points for Extension

| Extension Point | Location | Purpose |
|---|---|---|
| After `GCOa()` return | kernel, interaction loop | Add electron transport here |
| After photoelectric | kernel, interaction loop | Add Auger/fluorescence cascade |
| `tally_voxel_energy_deposition()` | kernel device function | Add DPK spreading here |
| Dose ROI bounds | constant memory | Already supports sub-volume tallying |
| `report_voxels_dose()` | host reporting | Add dose-to-water conversion |

---

## 8. Clinical Dosimetry Workflow

### 8.1 Current Workflow (Imaging-Centric)

```
1. Define phantom (voxel file with activity)
2. Run MCGPU-PET simulation
3. Obtain sinogram / PSF
4. Reconstruct images (external)
5. Compare reconstructed vs. true activity
```

### 8.2 Target Workflow (Dosimetry-Centric)

```
1. Define patient CT → voxel phantom
2. Assign radionuclide activity distribution
3. Run MCGPU-PET with dose tallying enabled
4. Obtain:
   a. Sinogram → Reconstruct activity map
   b. 3D dose map → Organ-level absorbed dose
   c. Dose-volume histograms (post-processing)
5. Iterate: time-integrated dose from multi-time-point scans
6. Radiobiological modeling (external)
```

### 8.3 Missing Components for Clinical Dosimetry

| Component | Status | Needed For |
|---|---|---|
| CT-to-material mapping | Not in code | Patient-specific phantoms |
| Positron range | Not modeled | Accurate source position |
| Electron transport | Photon-only | Accurate dose at interfaces |
| Time-activity integration | Single time point | Cumulated activity |
| Dose-volume histograms | Not in code | Clinical reporting |
| S-values comparison | Not in code | MIRD validation |
| Multiple isotopes | Fixed at F-18 lifetime | Lu-177, Y-90, etc. |
| Beta-particle dose | Not modeled | Theranostic isotopes |

---

## 9. Validation Strategy

### 9.1 Imaging Validation

| Test | Method |
|---|---|
| Point source sinogram | Compare with analytic projection |
| Uniform cylinder | Check for artifacts, verify scatter fraction |
| NEMA phantom | Standard PET performance metrics |
| Energy spectrum | Compare with measured detector response |
| Count rate | Verify linear relationship with activity |

### 9.2 Dosimetry Validation

| Test | Method |
|---|---|
| Uniform sphere in water | Compare with MIRD S-values |
| Mono-energetic photon beam | Compare KERMA with NIST μ_en/ρ tables |
| Two-material slab | Check dose at interface vs. EGSnrc |
| Organ-level dose | Compare with OLINDA/EXM |
| Heterogeneous phantom | Cross-validate with GATE/Geant4 |

---

## 10. Summary: Imaging ↔ Dosimetry Synergy

MCGPU-PET's architecture naturally supports both imaging and dosimetry because:

1. **Same transport engine** — No separate simulation needed
2. **Simultaneous tallying** — Imaging and dose computed in one pass
3. **Activity-driven source** — Voxel-level activity enables internal dosimetry
4. **GPU acceleration** — Fast enough for clinical-scale dose computation
5. **Extensible design** — Clear insertion points for electron transport

The path from current KERMA-level dosimetry to full Monte Carlo dose computation requires:
- Short-term: Validation against reference dose codes
- Medium-term: Dose point kernel integration
- Long-term: Coupled photon-electron transport (see companion document)
