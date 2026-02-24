# MCGPU-PET Design Document: Physics Models

**Version:** 1.0  
**Date:** 2026-02-24  
**Status:** Reference Design  
**Codebase:** MCGPU-PET v0.1 (based on MC-GPU v1.3)

---

## 1. Overview

MCGPU-PET is a Monte Carlo (MC) radiation transport code for Positron Emission Tomography (PET) simulation. It models the complete physics chain from positron annihilation through photon transport to detector coincidence detection. The physics engine is derived from the well-validated PENELOPE code (University of Barcelona) and adapted for GPU execution.

### Scope of Current Physics

| Physics Process | Status | Notes |
|---|---|---|
| Positron annihilation (511 keV pair) | Implemented | Fixed energy, no positron range |
| Photon transport (Woodcock tracking) | Implemented | Delta-scattering method |
| Compton scattering | Implemented | PENELOPE GCOa with Doppler broadening |
| Rayleigh scattering | Implemented | PENELOPE GRAa with form factors |
| Photoelectric absorption | Implemented | Full absorption, no fluorescence |
| Pair production | Implicitly handled | Grouped with photoelectric |
| Acollinearity | Implemented | Gaussian model, σ = 0.21276° |
| Time-of-flight | Implemented | Picosecond resolution |
| Electron/positron transport | **Not implemented** | KERMA approximation |
| Positron range | **Not implemented** | Emission at voxel center |

---

## 2. Positron Annihilation Source Model

### 2.1 Emission Geometry

Each voxel in the phantom is assigned a radioactivity concentration (Bq). The annihilation position is sampled **uniformly within the emitting voxel**:

$$\vec{r} = \left(\frac{i_x + U_1}{\Delta x^{-1}},\ \frac{i_y + U_2}{\Delta y^{-1}},\ \frac{i_z + U_3}{\Delta z^{-1}}\right)$$

where $(i_x, i_y, i_z)$ are the voxel indices (mapped 1:1 to CUDA `blockIdx`), $\Delta x^{-1}$ is the inverse voxel size, and $U_k \sim \text{Uniform}(\epsilon, 1-\epsilon)$ with $\epsilon = 0.00015$ to prevent floating-point boundary issues.

**Limitation:** Positron range is not modeled. The positron is assumed to annihilate exactly within its emission voxel. For high-energy positron emitters (e.g., ⁸²Rb, ⁶⁸Ga), this introduces a systematic error on the order of the positron range (1–8 mm in water).

### 2.2 Photon Pair Generation

The annihilation produces two back-to-back 511 keV photons:

$$E_\gamma = 510998.95 \text{ eV}$$

The first photon direction is sampled **isotropically** on the unit sphere:

$$\cos\theta = 1 - 2U_1, \quad \phi = 2\pi U_2$$

$$\hat{d}_1 = (\sin\theta\cos\phi,\ \sin\theta\sin\phi,\ \cos\theta)$$

### 2.3 Acollinearity Model

In reality, the positron-electron annihilation pair is not perfectly back-to-back due to the residual momentum of the positron-electron system. MCGPU-PET models this **non-collinearity** as a Gaussian angular deviation applied to the second photon direction:

$$\theta_{\text{NC}} = \sigma_{\text{NC}} \sqrt{-2\ln U_1} \cos(2\pi U_2)$$

where $\sigma_{\text{NC}} = 2 \times 0.21276° \approx 0.00743$ rad (FWHM ≈ 0.5°, consistent with published measurements).

The second photon direction is obtained by rotating the anti-parallel direction of photon 1 by $(\theta_{\text{NC}}, \phi_{\text{NC}})$ using a full 3D rotation matrix:

$$\hat{d}_2 = R(\theta_{\text{NC}}, \phi_{\text{NC}}) \cdot (-\hat{d}_1)$$

### 2.4 Temporal Sampling (Dynamic Acquisition)

The simulation models a **time-resolved** PET acquisition. The time between successive decays in a voxel follows an exponential distribution:

$$\Delta t = -\frac{1}{A_{\text{thread}}} \ln(U)$$

where $A_{\text{thread}}$ is the portion of the voxel activity assigned to the current GPU thread. The activity decays during the acquisition:

$$A_{\text{thread}}^{-1}(t) = A_{\text{thread}}^{-1}(0) \cdot \exp\left(\frac{t}{\tau}\right)$$

where $\tau$ is the isotope mean life. The simulation proceeds until the total acquisition time is exhausted ($\sum \Delta t > T_{\text{acq}}$).

Time is tracked in **picosecond** resolution using `unsigned long long int`, providing dynamic range up to ~5 hours.

---

## 3. Photon Transport

### 3.1 Woodcock Tracking (Delta Scattering)

MCGPU-PET uses the **Woodcock tracking** method for efficient ray tracing through the heterogeneous voxelized geometry. Instead of stopping at every voxel boundary, the photon steps through the geometry using the **minimum** mean free path (MFP) across all materials at the current energy:

$$\lambda_{\text{Woodcock}}(E) = \min_m \lambda_m(E)$$

The step length is sampled as:

$$s = -\lambda_{\text{Woodcock}} \ln(U)$$

At each interaction point, the true material is looked up and the probability of a **virtual (delta) interaction** is:

$$P_{\text{virtual}} = 1 - \frac{\lambda_{\text{Woodcock}} \cdot \rho}{\lambda_{\text{total}}(E, m)}$$

If $U < P_{\text{virtual}}$, the interaction is virtual (delta scattering) and the photon continues without change. Otherwise, a real interaction is sampled.

**Advantages:**
- Eliminates costly voxel boundary crossing calculations
- Single-step traversal across multiple voxels
- Memory-coherent access patterns on GPU
- No need for ray-box intersection at every voxel

### 3.2 Mean Free Path Interpolation

Material interaction data is pre-computed and stored as **linear interpolation tables**:

$$\sigma(E) = a_i + E \cdot b_i, \quad E \in [E_i, E_{i+1}]$$

Three interaction cross-sections are stored per material per energy bin (as `float3`):
- `.x` → Inverse total MFP (μ/ρ, cm²/g)
- `.y` → Inverse Compton MFP (μ_C/ρ, cm²/g)
- `.z` → Inverse Rayleigh MFP (μ_R/ρ, cm²/g)

The Woodcock MFP table (`float2`) stores the global minimum across all materials.

### 3.3 Interaction Type Selection

After confirming a real interaction, the type is selected by cumulative probability:

```
P_total = ρ * λ_Woodcock * σ_total(E, m)
P_Compton = P_total + ρ * λ_Woodcock * σ_Compton(E, m)
P_Rayleigh = P_Compton + ρ * λ_Woodcock * σ_Rayleigh(E, m)

if (U < P_Compton)  → Compton scattering
else if (U < P_Rayleigh) → Rayleigh scattering
else → Photoelectric absorption (particle terminated)
```

---

## 4. Compton Scattering (GCOa)

The Compton interaction model is a direct translation of PENELOPE's `SUBROUTINE GCOa`. Key features:

### 4.1 Sampling Algorithm

1. **Klein-Nishina angular sampling** with rejection for the reduced energy $\tau = E'/E$:
   - $\tau_{\min} = 1/(1+2\kappa)$ where $\kappa = E/m_e c^2$
   - Mixed sampling: logarithmic for small $\tau$, uniform for large $\tau$

2. **Incoherent scattering function** $S(x,Z)$ evaluated from atomic shell data:
   - Uses the impulse approximation with Compton profiles
   - Shell-by-shell contributions weighted by oscillator strengths (`fco`)

3. **Doppler broadening**: The projected momentum of the target electron (`pzomc`) is sampled to account for the electron binding energy, modifying the final photon energy.

### 4.2 Data Structures

```c
struct compton_struct {
    float fco[MAX_MATERIALS * MAX_SHELLS];     // Oscillator strengths
    float uico[MAX_MATERIALS * MAX_SHELLS];    // Ionization energies (eV)
    float fj0[MAX_MATERIALS * MAX_SHELLS];     // Compton profile parameters
    int   noscco[MAX_MATERIALS];               // Number of oscillator shells
};
```

### 4.3 Energy-Angle Relation

The scattering angle and energy loss are coupled through:

$$\cos\theta = 1 - \frac{1-\tau}{\tau \cdot \kappa}$$

$$E' = E \cdot \tau$$

The deposited energy $E_{\text{dep}} = E - E'$ is tallied for dose computation.

---

## 5. Rayleigh Scattering (GRAa)

The Rayleigh (coherent) scattering model follows PENELOPE's `SUBROUTINE GRAa`:

### 5.1 Sampling Algorithm

1. **RITA (Rational Inverse Transform with Aliasing)** method for efficient sampling of the cumulative distribution
2. Uses pre-computed form factor tables with binary search
3. The maximum momentum transfer is: $x_{\max} = E \times 8.066 \times 10^{-5}$ (natural units)
4. Angular sampling: $\cos\theta = 1 - 2x/x_{\max}^2$
5. Rejection criterion: $(1 + \cos^2\theta)/2$

### 5.2 Data Structures

```c
struct rayleigh_struct {
    float xco[NP_RAYLEIGH * MAX_MATERIALS];    // Momentum transfer values
    float pco[NP_RAYLEIGH * MAX_MATERIALS];    // Cumulative probabilities
    float aco[NP_RAYLEIGH * MAX_MATERIALS];    // RITA 'a' coefficients
    float bco[NP_RAYLEIGH * MAX_MATERIALS];    // RITA 'b' coefficients
    float pmax[MAX_ENERGYBINS_RAYLEIGH * MAX_MATERIALS];  // Maximum P(x)
    unsigned char itlco[...], ituco[...];      // Binary search limits
};
```

### 5.3 Key Property

Rayleigh scattering is **elastic** — the photon energy is unchanged. Only the direction is modified. This is important for PET because Rayleigh-scattered photons retain 511 keV and may pass the energy window, contributing to **mispositioned** coincidences that are difficult to distinguish from true coincidences.

---

## 6. Photoelectric Absorption

When neither Compton nor Rayleigh scattering is selected, the photon is **fully absorbed** via the photoelectric effect. The entire photon energy is deposited locally:

$$E_{\text{dep}} = E_\gamma$$

**Simplifications in the current model:**
- No characteristic X-ray fluorescence emission
- No Auger electron emission
- Immediate local energy deposition (KERMA approximation)

---

## 7. Direction Rotation

After each scattering event, the photon direction is rotated using the PENELOPE `DIRECT` subroutine (translated to CUDA). The rotation is performed in **double precision** for numerical stability, even though direction vectors are stored in single precision:

$$\hat{d}' = R(\theta, \phi) \cdot \hat{d}$$

The rotation handles the special case when $\hat{d} \parallel \hat{z}$ (i.e., $u^2 + v^2 \approx 0$) separately to avoid division by zero.

---

## 8. Scatter State Tracking

Each photon carries a `scatter_state` flag:

| Value | Meaning |
|-------|---------|
| 0 | Non-scattered (primary) |
| 1 | Single Compton scatter |
| 2 | Single Rayleigh scatter |
| 3 | Multiple scatter |

This enables separate tallying of **True** and **Scatter** coincidences:
- **True coincidence**: Both photons have `scatter_state == 0`
- **Scatter coincidence**: At least one photon has `scatter_state > 0`

---

## 9. Dose Deposition Model

### 9.1 KERMA Approximation

Since electrons are not transported, the deposited energy equals the kinetic energy released to charged particles (KERMA):

$$D_{\text{voxel}} = \frac{\sum_{i} E_{\text{dep},i}}{m_{\text{voxel}} \cdot N_{\text{hist}}}$$

where $E_{\text{dep},i}$ is the energy deposited in interaction $i$, $m_{\text{voxel}} = \rho \cdot V_{\text{voxel}}$, and $N_{\text{hist}}$ is the number of histories.

### 9.2 Validity Conditions

The KERMA approximation is valid when:
1. **Electronic equilibrium** exists (uniform medium, far from interfaces)
2. **Secondary electron range** is shorter than the voxel size
3. Photon energies are below ~1 MeV (satisfied for 511 keV PET)

### 9.3 Statistical Uncertainty

Both $E_{\text{dep}}$ and $E_{\text{dep}}^2$ are tallied using atomic operations to compute the standard deviation:

$$\sigma = \sqrt{\frac{\langle E^2 \rangle - \langle E \rangle^2}{N}}$$

---

## 10. Energy Spectrum of Detected Photons

Detected photon energies are blurred by the detector energy resolution:

$$E_{\text{measured}} = E_{\text{true}} + \frac{R}{2.35} \cdot E_{\text{true}} \cdot \mathcal{N}(0,1)$$

where $R$ is the fractional energy resolution (FWHM) and $\mathcal{N}(0,1)$ is sampled via Box-Muller transform. The energy window filter then selects events within $[E_{\text{low}}, E_{\text{high}}]$.

---

## 11. Material Data

### 11.1 Format

Material files are generated from PENELOPE material databases and contain pre-computed cross-sections for photon interactions as a function of energy. The `.mcgpu.gz` format stores:
- Total, Compton, and Rayleigh mean free paths
- Compton interaction model parameters (oscillator shells)
- Rayleigh form factor tables

### 11.2 Supported Materials

Up to `MAX_MATERIALS = 15` materials can be used simultaneously. Each voxel references a material number and local density. The interaction probabilities are scaled by the local density relative to the nominal material density.

### 11.3 Energy Range

Material tables currently span 5–515 keV, covering the 511 keV annihilation photon energy with margin for energy loss through multiple Compton scattering.

---

## 12. Physics Limitations and Known Approximations

| Approximation | Impact | Mitigation Path |
|---|---|---|
| No positron range | Overestimates spatial resolution for high-E emitters | Model positron transport or use range kernels |
| No electron transport (KERMA) | Dose inaccurate at interfaces and for small organs | Implement electron tracking |
| No fluorescence X-rays | Minor for PET (photoelectric minority at 511 keV) | Add K/L-shell fluorescence |
| No pair production transport | Negligible at 511 keV | Not needed for standard PET |
| Fixed 511 keV source energy | Cannot model prompt-gamma or other emissions | Add spectrum source model |
| No random coincidences | Missing background contribution | Add delayed window simulation |
| Single-precision transport | Small numerical errors possible | Mitigated by double-precision rotations |

---

## References

1. J.L. Herraiz, A. Lopez-Montes, A. Badal, "MCGPU-PET: An Open-Source Real-Time Monte Carlo PET Simulator", *Computer Physics Communications* 296 (2024) 109008.
2. F. Salvat, J.M. Fernández-Varea, J. Sempau, "PENELOPE-2006: A Code System for Monte Carlo Simulation of Electron and Photon Transport", NEA/OECD (2006).
3. A. Badal, A. Badano, "Accelerating Monte Carlo simulations of photon transport in a voxelized geometry using a massively parallel graphics processing unit", *Medical Physics* 36(11), 2009.
