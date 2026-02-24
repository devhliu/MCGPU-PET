# MCGPU-PET Design Document: Photon-to-Electron Transport Roadmap

**Version:** 1.0  
**Date:** 2026-02-24  
**Status:** Technical Roadmap  
**Codebase:** MCGPU-PET v0.1 (based on MC-GPU v1.3)

---

## 1. Motivation

MCGPU-PET currently simulates **photon-only** transport: 511 keV annihilation photons undergo Compton, Rayleigh, and photoelectric interactions, with energy deposited locally at each interaction site (KERMA approximation). Extending to **coupled photon-electron transport** is essential for:

1. **Accurate absorbed dose** — Electrons carry energy away from the photon interaction site; at tissue boundaries, dose can be over- or under-estimated by 10–30% with KERMA alone.
2. **Positron range modeling** — The annihilation occurs at the positron stopping point, not at the decay site; the range in tissue varies from <1 mm (F-18) to >1 cm (Rb-82).
3. **Theranostic dosimetry** — Isotopes such as Lu-177, Y-90, and Ac-225 emit beta particles or alpha particles whose transport dominates the therapeutic dose.
4. **Secondary radiation** — Bremsstrahlung from electrons, characteristic X-rays, and Auger electrons contribute to dose.

---

## 2. Current State: Photon-Only Transport

### 2.1 What Exists

```
Photon born at 511 keV
  │
  ├──► Woodcock sampling → virtual interaction (delta scattering)
  │    └── continue transport
  │
  ├──► Compton scattering (GCOa)
  │    ├── Scattered photon: new energy, direction
  │    ├── Electron KE = E_in - E_out → deposited at interaction site
  │    └── Photon continues
  │
  ├──► Rayleigh scattering (GRAa)
  │    ├── Photon: same energy, new direction
  │    └── No dose deposited
  │
  └──► Photoelectric absorption
       ├── Photon absorbed
       └── Full energy → deposited at interaction site
```

### 2.2 What's Missing

| Physics | Current | Needed |
|---|---|---|
| Positron transport | Not modeled | Condensed-history MC |
| Positron range | Fixed at decay voxel | Material-dependent range |
| Compton electron | Energy deposited locally | Track with dE/dx, scattering |
| Photoelectron | Energy deposited locally | Track to stopping |
| Auger electrons | Not modeled | Cascade + transport |
| Bremsstrahlung | Not generated | Secondary photon creation |
| Characteristic X-rays | Not modeled | Fluorescence yield tables |
| Pair production | Cross-section present, unused | Not relevant at 511 keV |
| Delta rays | Not modeled | High-energy electron collisions |

---

## 3. Electron Transport Physics

### 3.1 Condensed-History Method

Unlike photons, electrons undergo millions of interactions before stopping. Direct simulation of every collision is impractical. The **condensed-history** (CH) method groups many small interactions into a single step:

```
Electron transport step:
  1. Sample step length s (based on mean free path or prescribed step)
  2. Compute energy loss along step: ΔE = s × (dE/dx)
  3. Sample angular deflection: multiple scattering (Molière/GS theory)
  4. Apply sub-step corrections (boundary crossing, energy straggling)
  5. Check for hard interactions:
     a. Hard elastic scattering (>θ_cutoff)
     b. Hard inelastic collision (>E_cutoff) → delta ray
     c. Bremsstrahlung emission (>E_cutoff) → secondary photon
  6. Move electron, deposit energy
  7. Repeat until E < E_absorption
```

### 3.2 PENELOPE Electron Model

PENELOPE (the physics engine underlying MCGPU) provides a complete electron/positron transport package using a **mixed** (Class II) condensed-history algorithm:

| Category | Soft (below cutoff) | Hard (above cutoff) |
|---|---|---|
| Elastic | Continuous angular diffusion | Individual Mott scattering |
| Inelastic | Continuous energy loss (Bethe) | Individual Møller/Bhabha collision |
| Bremsstrahlung | Continuous radiative loss | Individual photon emission |

**Cutoff parameters:**
- `C1`: Average angular deflection per step (typically 0.05)
- `C2`: Maximum fractional energy loss per step (typically 0.05)
- `Wcc`: Cutoff energy for hard inelastic collisions (eV)
- `Wcr`: Cutoff energy for hard bremsstrahlung (eV)

### 3.3 Key Cross-Section Data

PENELOPE material files already contain electron/positron data:

| Data | Used For | Available in .mcgpu.gz? |
|---|---|---|
| Stopping power (dE/dx) | Continuous energy loss | No — must add |
| Elastic MFP | Step length control | No — must add |
| Mott DCS | Hard elastic angular sampling | No — must add |
| Møller/Bhabha DCS | Inelastic knock-on electrons | No — must add |
| Bremsstrahlung DCS | Radiative emission | No — must add |
| Multiple scattering params | Angular distribution per step | No — must add |

**Action required:** Extend the material file format to include electron transport tables, or read the full PENELOPE `.mat` file format.

---

## 4. Implementation Roadmap

### Phase 1: Positron Range (Estimated effort: 2–4 weeks)

**Goal:** Model positron transport from decay to annihilation.

```
Current:   Decay at voxel → Annihilate at same voxel
Proposed:  Decay at voxel → Transport positron → Annihilate at stopping point
```

**Approach: Pre-computed range distributions**

Rather than full positron transport, use pre-tabulated range distributions from PENELOPE or GATE:

1. Build a lookup table: `P(r | E_max, material)` — positron range CDF for each isotope and material
2. At each decay, sample range `r` from the distribution
3. Sample random direction, displace annihilation position by `r`
4. Check that new position is still within geometry

| Isotope | Max β⁺ Energy | Mean Range (water) | Impact on PET |
|---|---|---|---|
| F-18 | 634 keV | 0.6 mm | Minimal |
| C-11 | 961 keV | 1.0 mm | Small |
| O-15 | 1732 keV | 2.5 mm | Moderate |
| Ga-68 | 1899 keV | 2.9 mm | Moderate |
| Rb-82 | 3381 keV | 5.9 mm | Significant |

**Code changes:**
- Add `positron_range_table` to material data structures
- Modify `source()` to displace annihilation position
- Add range table loading in `load_material()`

---

### Phase 2: Electron Dose Kernels (Estimated effort: 4–8 weeks)

**Goal:** Improved dose accuracy using pre-computed dose deposition kernels without full tracking.

**Approach:**

1. Pre-compute dose point kernels (DPK) using PENELOPE for each material at relevant energies (100–511 keV)
2. Store kernels as radially-symmetric functions: `D(r, E, material)`
3. At each photon interaction, apply the kernel to distribute dose to neighboring voxels

```
Compton interaction at voxel (i,j,k):
  E_electron = 300 keV
  material = water

  Dose kernel D(r) at 300 keV in water:
    r=0:   45% of energy
    r=1mm: 30% of energy
    r=2mm: 15% of energy
    r=3mm:  8% of energy
    r>3mm:  2% of energy

  Apply kernel:
    dose[i,j,k]   += 0.45 × E
    dose[i±1,...] += weighted fractions
    ...
```

**Code changes:**
- Add DPK data structure and loading
- Replace `tally_voxel_energy_deposition()` with kernel-spreading version
- Handle voxel boundaries and material interfaces

---

### Phase 3: Simplified Electron Transport (Estimated effort: 8–16 weeks)

**Goal:** Track electrons above a configurable energy threshold using condensed-history steps.

**Approach: CSDA + Multiple Scattering**

The simplest electron transport model uses:
- Continuous Slowing-Down Approximation (CSDA) for energy loss
- Gaussian multiple scattering for angular deflection
- No secondary particle generation

```c
__device__ void track_electron(float3 position, float3 direction, 
                               float energy, int material, ...) {
    while (energy > E_absorption) {
        // Step length (fraction of CSDA range)
        float step = min(MAX_STEP, CSDA_range(energy, material) * STEP_FRACTION);
        
        // Energy loss
        float dE = stopping_power(energy, material) * step;
        
        // Multiple scattering
        float theta = sample_multiple_scattering(energy, step, material);
        float phi = 2.0f * PI * ranecu(seed);
        rotate_double(&direction, theta, phi);
        
        // Move
        position += step * direction;
        energy -= dE;
        
        // Tally
        int voxel = locate_voxel(position);
        tally_voxel_energy_deposition(voxel, dE);
    }
}
```

**Code changes:**
- Add stopping power and scattering tables to material data
- Add `track_electron()` device function
- Call from interaction loop after Compton/photoelectric
- Manage register pressure (electron tracking adds many variables)

---

### Phase 4: Full PENELOPE Electron Transport (Estimated effort: 16–32 weeks)

**Goal:** Complete Class II mixed algorithm with hard interactions and secondary particle generation.

**Components:**

| Component | Description | Complexity |
|---|---|---|
| Hard elastic scattering | Mott DCS sampling with RITA | Medium |
| Hard inelastic | Møller (e⁻) / Bhabha (e⁺) | Medium |
| Bremsstrahlung emission | Secondary photon generation | Medium |
| Inner-shell ionization | Auger/fluorescence cascade | High |
| Positron annihilation | In-flight and at-rest | Low (modify existing) |
| Secondary particle stack | GPU-side particle stack | High |
| Step-length algorithm | Energy-dependent adaptive steps | Medium |
| Boundary crossing | Interface correction (random hinge) | High |

**GPU-Specific Challenges:**

1. **Particle stack management:**
   - Each thread needs a local stack for secondary particles
   - Stack depth varies (Auger cascades can produce many secondaries)
   - Shared memory is limited (~48 KB per block)
   
   ```
   Proposed: Thread-local stack in registers/local memory
   Max depth: ~8 particles (covers most cascades)
   Overflow: Discard lowest-energy secondary (rare)
   ```

2. **Register pressure:**
   - Photon tracking: ~40 registers per thread
   - Adding electrons: ~80+ registers per thread
   - Risk: Reduced occupancy → performance loss
   
   ```
   Mitigation: 
   - Function-level __launch_bounds__ directives
   - Careful variable reuse
   - Split kernel approach (photon kernel + electron kernel)
   ```

3. **Warp divergence:**
   - Electron step count varies drastically (10–1000 steps)
   - Threads in same warp may finish at very different times
   
   ```
   Mitigation:
   - Energy-based grouping (persistent kernel approach)
   - Warp-cooperative scheduling
   - Separate kernel launch for sub-threshold electrons
   ```

---

## 5. Data Structure Extensions

### 5.1 Extended Material Data

```c
struct electron_data_struct {
    // Stopping power table (CSDA)
    float stopping_power[MAX_ENERGY_BINS];    // MeV·cm²/g
    float energy_straggling[MAX_ENERGY_BINS]; // Ω² parameter
    
    // Elastic scattering
    float elastic_mfp[MAX_ENERGY_BINS];       // cm
    float transport_mfp[MAX_ENERGY_BINS];     // λ_tr
    
    // Multiple scattering parameters (Lewis theory)
    float ms_A[MAX_ENERGY_BINS];              // screening parameter
    float ms_B[MAX_ENERGY_BINS];              // angular distribution
    
    // Hard interaction cross-sections
    float inelastic_cs[MAX_ENERGY_BINS];      // cm²/g
    float bremsstrahlung_cs[MAX_ENERGY_BINS]; // cm²/g
    
    // Range table
    float csda_range[MAX_ENERGY_BINS];        // cm
};
```

### 5.2 Particle Stack

```c
struct particle_struct {
    float3 position;
    float3 direction;
    float energy;
    signed char type;     // 0=photon, 1=electron, 2=positron
    signed char material;
    short int scatter_state;
};

// Thread-local stack (max 8 secondaries)
#define MAX_STACK_DEPTH 8
struct {
    particle_struct particles[MAX_STACK_DEPTH];
    int top;
} secondary_stack;
```

---

## 6. Memory Budget

Memory estimates for full electron transport on a modern GPU (e.g., RTX 3090 with 24 GB):

| Data | Size Formula | Estimate (15 materials, 500 energy bins) |
|---|---|---|
| Current photon data | ~50 MB | 50 MB |
| Stopping power tables | 15 × 500 × 4 B | 30 KB |
| Elastic MFP tables | 15 × 500 × 4 B | 30 KB |
| Multiple scattering | 15 × 500 × 8 B | 60 KB |
| Hard interaction CS | 15 × 500 × 8 B | 60 KB |
| Mott DCS (angular) | 15 × 500 × 128 × 4 B | 3.8 MB |
| Dose point kernels | 15 × 100 × 50 × 4 B | 300 KB |
| **Total additional** | | **~5 MB** |

Electron cross-section data fits comfortably in constant memory or L2 cache. Memory is not the limiting factor; register pressure and warp divergence are the primary concerns.

---

## 7. Performance Projections

| Phase | Speed vs. Photon-Only | Notes |
|---|---|---|
| Positron range (lookup) | 0.95× | Negligible overhead |
| Dose point kernels | 0.7–0.8× | Extra memory accesses |
| CSDA electron transport | 0.3–0.5× | ~10 extra steps per electron |
| Full PENELOPE electrons | 0.1–0.2× | Significant divergence + stacking |

**Mitigation strategies:**
- Only track electrons above an energy threshold (e.g., 50 keV)
- Use DPK for low-energy electrons, full transport for high-energy
- Separate photon and electron kernel launches
- Spatial subdivision to improve warp coherence

---

## 8. Validation Plan

### 8.1 Phase-by-Phase Benchmarks

| Phase | Benchmark | Reference |
|---|---|---|
| Positron range | Range distributions in water, bone, lung | PENELOPE standalone |
| DPK | Point-source dose kernels | Published DPK tables (Cross 1992) |
| CSDA electrons | Depth-dose curves in water | EGSnrc / PENELOPE standalone |
| Full transport | Fano cavity test | Analytical (must yield unity) |
| Full transport | Slab geometry benchmark | PENELOPE / EGSnrc comparison |
| Full transport | Heterogeneous phantom dose | GATE/Geant4 comparison |

### 8.2 Gold Standard Codes

| Code | Electron Physics | Speed | Use |
|---|---|---|---|
| PENELOPE (standalone) | Full Class II | Slow | Reference physics |
| EGSnrc | Full PRESTA-II | Slow | Dosimetry gold standard |
| Geant4/GATE | Configurable | Slow | PET + dose reference |
| ARCHER | GPU-accelerated | Fast | GPU performance comparison |
| gDPM | GPU dose engine | Fast | Architecture reference |

---

## 9. Recommended Phasing

```
NOW ──────────► 3 months ──────────► 9 months ──────────► 18 months
│                │                    │                     │
│  Phase 1       │  Phase 2           │  Phase 3            │  Phase 4
│  Positron      │  Dose Point        │  CSDA Electron      │  Full PENELOPE
│  Range         │  Kernels           │  Transport           │  Electron
│                │                    │                     │
│  • Lookup      │  • Pre-computed    │  • Stopping power   │  • Hard interactions
│    table       │    DPK library     │  • Multiple scat.   │  • Secondary stack
│  • Source       │  • Neighbor dose  │  • Step control     │  • Bremsstrahlung
│    displacement│    spreading       │  • Boundary cross   │  • Auger cascade
│                │                    │                     │
│  Impact:       │  Impact:           │  Impact:            │  Impact:
│  PET image     │  Dose accuracy     │  Interface dose     │  Full dosimetry
│  quality       │  improved ~10%     │  improved ~20-30%   │  reference-grade
└────────────────┴────────────────────┴─────────────────────┘
```

Each phase builds on the previous one and provides independent value. The simulation remains usable (and faster) at each intermediate stage.
