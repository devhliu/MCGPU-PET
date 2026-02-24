# MCGPU-PET Design Document: Future Development Roadmap

**Version:** 1.0  
**Date:** 2026-02-24  
**Status:** Technical Roadmap  
**Codebase:** MCGPU-PET v0.1 (based on MC-GPU v1.3)

---

## 1. Overview

This document outlines the comprehensive development roadmap for MCGPU-PET, spanning improvements to physics accuracy, detector modeling, imaging capabilities, dosimetry features, computational performance, and software engineering. Items are grouped by domain and prioritized by impact and feasibility.

---

## 2. Physics Enhancements

### 2.1 Positron Range Modeling

**Priority:** High | **Effort:** Low-Medium | **Impact:** Image quality and dose accuracy

| Feature | Details |
|---|---|
| Lookup-table positron range | Pre-computed range CDFs per isotope and material |
| Full positron transport | Condensed-history MC with annihilation physics |
| In-flight annihilation | Positron annihilates before thermalizing |
| Positron-material dependence | Range varies with tissue type (water/bone/lung) |

**Current state:** Annihilation is fixed at the decay voxel center.

### 2.2 Electron Transport

**Priority:** High (for dosimetry) | **Effort:** High | **Impact:** Dose accuracy

See the dedicated [Photon-to-Electron Roadmap](06_Photon_Electron_Roadmap.md) for the full 4-phase plan.

### 2.3 Extended Interaction Physics

**Priority:** Medium | **Effort:** Medium

| Feature | Current | Proposed |
|---|---|---|
| Bound Compton scattering | Impulse approximation (PENELOPE) | Already implemented |
| Doppler broadening | Implemented | Already implemented |
| Rayleigh scattering | Anomalous form factors (PENELOPE) | Already implemented |
| Fluorescence X-rays | Not modeled | Add K/L-shell fluorescence after PE |
| Auger electrons | Not modeled | Add cascade model |
| Pair production | Cross-section loaded, not invoked | Enable for >1.022 MeV photons |
| Nuclear interactions | Not modeled | Low priority for PET energies |

### 2.4 Radioactive Decay Modeling

**Priority:** High (for theranostics) | **Effort:** Medium

| Feature | Details |
|---|---|
| Multiple isotopes | Support F-18, C-11, O-15, N-13, Ga-68, Rb-82, Zr-89, Cu-64 |
| Beta spectrum sampling | Fermi theory or tabulated β⁺ spectra per isotope |
| Prompt gamma emission | Relevant for Ga-68, some therapy isotopes |
| Decay chain simulation | Sequential daughter decays (e.g., Ac-225 chain) |
| Time-dependent activity | Biological washout + physical decay |
| Mixed isotope fields | Different isotopes in different voxels |

---

## 3. Detector Model Extensions

### 3.1 Realistic Crystal Geometry

**Priority:** High | **Effort:** Medium

```
Current:                         Proposed:
┌──────────────────┐             ┌──┬──┬──┬──┬──┐
│  Smooth cylinder │             │  │  │  │  │  │ ← Individual crystals
│  (no gaps, no    │             ├──┼──┼──┼──┼──┤
│   dead zones)    │             │  │  │  │  │  │ ← Inter-crystal gaps
│                  │             ├──┼──┼──┼──┼──┤
└──────────────────┘             │  │  │  │  │  │ ← Block structure
                                 └──┴──┴──┴──┴──┘
```

| Feature | Details |
|---|---|
| Discrete crystals | Finite crystal size with gaps |
| Block detector structure | Groups of crystals sharing readout |
| Crystal depth-of-interaction (DOI) | Photon penetration into crystal |
| Crystal material | LSO, LYSO, BGO with energy-dependent efficiency |
| Dead time | Paralyzable/non-paralyzable models |
| Pile-up | Multiple events in one crystal within dead time |

### 3.2 Advanced Time-of-Flight (TOF)

**Priority:** High | **Effort:** Low-Medium

| Feature | Current | Proposed |
|---|---|---|
| Travel time recording | ✅ In PSF | Already available |
| TOF resolution blurring | Not applied | Add Gaussian timing jitter |
| TOF sinogram binning | Not implemented | Add Δt bins to sinogram |
| Coincidence time window | Not modeled | Add configurable window |
| Prompt-delay random estimation | Background mode only | Add delayed window method |

### 3.3 Scanner Configurations

**Priority:** Medium | **Effort:** Medium

| Feature | Details |
|---|---|
| Multi-ring scanners | Different ring diameters |
| Partial-ring PET | Rotating detector heads |
| Total-body PET | Extended axial FOV (>1 m) |
| PET/CT hybrid | Combined simulation with CT source |
| PET/MR considerations | MR-based attenuation correction input |
| Small-animal PET | High-resolution preclinical geometry |

---

## 4. Imaging Pipeline

### 4.1 Random Coincidences

**Priority:** High | **Effort:** Medium

| Feature | Details |
|---|---|
| Singles rate tracking | Count single detections per crystal per time bin |
| Random coincidence generation | Pair uncorrelated singles within timing window |
| Delayed window method | Estimate randoms from delayed coincidence window |
| Random sinogram | Separate random coincidence sinogram output |

**Current:** Only the `background_mode` flag provides a rough estimate.

### 4.2 Scatter Modeling

**Priority:** Medium | **Effort:** Low (mostly done)

| Feature | Current | Proposed |
|---|---|---|
| Scatter state tracking | ✅ index1 counter | Already implemented |
| Multiple scatter categorization | Single vs. multiple | Add scatter order tracking |
| Scatter sinogram | ✅ Separate tally | Already implemented |
| Single scatter simulation (SSS) | Not implemented | Add for scatter correction |
| Object scatter vs. detector scatter | Not distinguished | Add crystal scatter model |

### 4.3 Image Reconstruction Interface

**Priority:** Medium | **Effort:** Medium

| Feature | Details |
|---|---|
| List-mode output | Event-by-event with TOF, for list-mode reconstruction |
| System matrix generation | Forward projector from MC simulation |
| Normalization data | Detector efficiency variation simulation |
| Attenuation sinogram | μ-map forward projection |
| Sensitivity image | Geometric + attenuation sensitivity per voxel |

### 4.4 Dynamic PET Simulation

**Priority:** Medium | **Effort:** Medium

| Feature | Details |
|---|---|
| Time frames | Multiple acquisition windows |
| Kinetic modeling input | Time-activity curve per tissue type |
| Gating | Respiratory/cardiac motion-gated frames |
| Moving phantoms | XCAT-style 4D voxelized phantoms |

---

## 5. Dosimetry Extensions

### 5.1 Enhanced Dose Reporting

**Priority:** High | **Effort:** Low-Medium

| Feature | Current | Proposed |
|---|---|---|
| Dose units | eV/g per simulation | Convert to Gy (J/kg) |
| Dose-to-water | Not available | Add material → water conversion |
| Organ-level dose | Per-material only | Add organ segmentation labels |
| Dose-volume histogram (DVH) | Not available | Post-processing or in-simulation |
| Cumulative dose | Single time point | Integrate over time-activity curve |
| S-values output | Not available | MIRD-format organ cross-dose |

### 5.2 Variance Reduction

**Priority:** High (for dosimetry efficiency) | **Effort:** Medium-High

| Technique | Description | Applicability |
|---|---|---|
| Forced detection | Force fraction of weight toward detector | Imaging efficiency |
| Splitting/roulette | Clone important photons, kill unimportant | Both |
| Track-length estimator | Score dose along path, not just at interactions | Dose efficiency |
| Correlated sampling | Perturb parameters, reuse trajectories | Sensitivity studies |
| Importance sampling | Bias source direction toward detector | Imaging |

> **Note:** Variance reduction must preserve unbiased dose estimates. Each technique requires careful implementation and validation.

### 5.3 Theranostic Dosimetry

**Priority:** High (emerging clinical need) | **Effort:** High

| Feature | Details |
|---|---|
| Beta-particle transport | Lu-177 (β⁻ max 498 keV), Y-90 (β⁻ max 2280 keV) |
| Alpha-particle transport | Ac-225, Ra-223 (short range, high LET) |
| Gamma emission | Lu-177 gammas (113, 208 keV) for imaging |
| Dose-rate effects | Time-dependent dose rate for radiobiology |
| Biological effective dose (BED) | Incorporate linear-quadratic model |
| Tumor control probability (TCP) | Dose-response modeling |

---

## 6. Computational Performance

### 6.1 GPU Optimization

**Priority:** Medium | **Effort:** Medium

| Feature | Details |
|---|---|
| Persistent kernel | Reduce launch overhead, improve load balancing |
| Warp-cooperative tracking | Threads in warp help each other |
| Mixed precision | FP16 for non-critical calculations |
| Tensor cores | Matrix operations for batch scattering |
| Memory coalescing | Restructure voxel access patterns |
| Stream-based overlap | Overlap computation with I/O |
| Dynamic parallelism | Spawn electron kernels from photon kernel |

### 6.2 Multi-GPU Scaling

**Priority:** Medium | **Effort:** Medium

| Feature | Current | Proposed |
|---|---|---|
| MPI multi-GPU | ✅ Basic support | Already available |
| NCCL communication | Not used | Replace MPI for GPU-GPU |
| Domain decomposition | Each GPU simulates all voxels | Spatial partitioning |
| Load balancing | Equal history distribution | Activity-weighted distribution |
| Multi-node scaling | MPI across nodes | Already supported via MPI |

### 6.3 Modern GPU Features

**Priority:** Low-Medium | **Effort:** Medium

| Feature | GPU Arch | Benefit |
|---|---|---|
| Cooperative groups | Volta+ | Flexible synchronization |
| Hardware ray tracing | Ampere+ | Accelerate photon transport |
| Async memory copies | Ampere+ | Overlap compute and transfer |
| Thread block clusters | Hopper+ | Cross-block cooperation |

---

## 7. Software Engineering

### 7.1 Code Modernization

**Priority:** Medium | **Effort:** Medium

| Feature | Current | Proposed |
|---|---|---|
| Build system | Makefile | CMake with CUDA support |
| Testing | None | Unit tests + integration tests |
| CI/CD | None | GitHub Actions for build/test |
| Documentation | README + inline comments | Doxygen + design docs (this series) |
| Code style | Mixed C/C++ | Consistent formatting (clang-format) |
| Version control | Git | Semantic versioning |

### 7.2 Input/Output Modernization

**Priority:** Low-Medium | **Effort:** Medium

| Feature | Current | Proposed |
|---|---|---|
| Input format | Custom text sections | YAML/JSON option |
| Phantom format | penEasy text | NIfTI/DICOM support |
| Output format | Raw binary | HDF5/NIfTI with metadata |
| Progress reporting | printf | Structured logging |
| Checkpoint/restart | None | Save/resume simulation state |
| Parameter validation | Basic | Schema-based validation |

### 7.3 Python Interface

**Priority:** Medium | **Effort:** Medium

| Feature | Details |
|---|---|
| Python bindings | pybind11 or ctypes wrapper |
| Jupyter integration | Run from notebook, plot inline |
| Configuration API | Programmatic parameter setting |
| Result loading | NumPy-based output readers |
| Phantom generation | Python API for complex geometries |
| Batch execution | Multi-simulation parameter sweeps |

### 7.4 Interoperability

**Priority:** Medium | **Effort:** Medium

| Feature | Details |
|---|---|
| GATE compatibility | Read/write GATE macro files |
| DICOM RT | Import/export dose in DICOM format |
| STIR/CASToR | Export sinograms in reconstruction format |
| XCAT phantoms | Read 4D XCAT phantom format |
| ICRP phantoms | Support reference computational phantoms |

---

## 8. Validation and Benchmarking

### 8.1 Physics Validation Suite

| Test | Reference | Priority |
|---|---|---|
| Point source in water | Analytical + GATE | High |
| NEMA IQ phantom | Published measurements | High |
| Jaszczak phantom | Contrast recovery measurement | Medium |
| Derenzo resolution phantom | Spatial resolution measurement | Medium |
| Scatter fraction (NEMA) | Published scanner data | High |
| Sensitivity profile | Published scanner data | Medium |

### 8.2 Dosimetry Validation Suite

| Test | Reference | Priority |
|---|---|---|
| MIRD S-values (spheres) | OLINDA/EXM | High |
| Heterogeneous phantom dose | EGSnrc/PENELOPE | High |
| Organ dose (ICRP phantom) | Published reference values | Medium |
| Interface dose | Literature benchmarks | High |
| Fano cavity test | Analytical (must yield 1.0) | Critical |

### 8.3 Performance Benchmarks

| Metric | Current Baseline | Target |
|---|---|---|
| Photons/second/GPU | ~10⁸ (estimate) | Measure and optimize |
| Time to 10⁸ coincidences | Minutes | Track across versions |
| GPU utilization | Unknown | >80% target |
| Memory efficiency | Unknown | Profile and optimize |
| Multi-GPU scaling | Linear (ideal) | Measure overhead |

---

## 9. Priority Matrix

```
                        IMPACT
                Low         Medium        High
           ┌───────────┬────────────┬────────────┐
    Low    │ Tensor     │ JSON input │ Prompt     │
           │ cores      │ format     │ gamma      │
           │            │            │            │
  EFFORT   ├───────────┼────────────┼────────────┤
    Med    │ NCCL       │ Python API │ TOF sinos  │
           │ comms      │ CMake      │ Randoms    │
           │            │ Crystal    │ DVH output │
           │            │ geometry   │            │
           ├───────────┼────────────┼────────────┤
    High   │ 4D         │ Full e⁻    │ Positron   │
           │ phantoms   │ transport  │ range      │
           │            │ Theranostic│ DPK dose   │
           │            │            │ Validation │
           └───────────┴────────────┴────────────┘
```

---

## 10. Recommended Development Sequence

### Near-Term (0–6 months)
1. **Positron range** — Lookup-table approach (Phase 1 of electron roadmap)
2. **TOF sinogram binning** — Low effort, high clinical relevance
3. **Random coincidence modeling** — Essential for realistic simulations
4. **Dose unit conversion** — Gy output, dose-to-water
5. **Build system** — Migrate to CMake
6. **Basic validation suite** — Point source + NEMA IQ phantom

### Medium-Term (6–18 months)
7. **Dose point kernels** — Phase 2 of electron roadmap
8. **Crystal geometry** — Discrete crystals with gaps
9. **Python interface** — Configuration and output loading
10. **Dynamic PET** — Multiple time frames
11. **Fluorescence X-rays** — Post-photoelectric cascade
12. **Performance profiling** — Nsight analysis and optimization

### Long-Term (18+ months)
13. **Full electron transport** — Phases 3–4 of electron roadmap
14. **Theranostic isotopes** — Lu-177, Y-90 simulation
15. **Variance reduction** — Forced detection, splitting
16. **Total-body PET** — Extended FOV scanner models
17. **HDF5 output** — Self-describing output files
18. **4D phantom support** — XCAT integration
19. **System matrix generation** — For model-based reconstruction
20. **Comprehensive validation** — Cross-code comparison campaign

---

## 11. Document Index

| # | Document | Description |
|---|---|---|
| 01 | [Physics Models](01_Physics_Models.md) | Photon interaction physics and source model |
| 02 | [GPU Acceleration](02_GPU_Acceleration.md) | CUDA parallelization and memory strategy |
| 03 | [Software Architecture](03_Software_Architecture.md) | Code structure, data flow, and design patterns |
| 04 | [Inputs & Outputs](04_Inputs_Outputs.md) | File formats, parameters, and data conventions |
| 05 | [Imaging to Dosimetry](05_Imaging_to_Dosimetry.md) | Bridging PET imaging and dose computation |
| 06 | [Photon-Electron Roadmap](06_Photon_Electron_Roadmap.md) | Technical plan for electron transport |
| 07 | [Future Development](07_Future_Development.md) | Comprehensive development roadmap (this document) |
