# MCGPU-PET Design Document: Siemens Biograph Vision 600 Scanner Integration

**Version:** 1.0  
**Date:** 2026-02-24  
**Status:** Reference Design  
**Codebase:** MCGPU-PET v0.1 (based on MC-GPU v1.3)

---

## 1. Introduction

This document describes how to configure MCGPU-PET to simulate the **Siemens Biograph Vision 600** PET/CT scanner. It covers the mapping between the physical scanner specifications and the parameters consumed by the MCGPU-PET code, the modeling assumptions made, known limitations, and practical guidance for running simulations.

The Vision 600 is a digital SiPM-based PET/CT scanner with LSO scintillator crystals, offering 9.3% energy resolution (FWHM at 511 keV) and ~210 ps coincidence resolving time (CRT). Its 26.3 cm axial field of view and 80 crystal rings make it a widely deployed clinical system with well-characterized NEMA performance data.

---

## 2. Scanner Specifications Summary

The table below lists the verified physical parameters of the Biograph Vision 600, sourced from peer-reviewed literature:

| Parameter | Value | Unit | Reference |
|---|---|---|---|
| Crystal material | LSO (Lu2SiO5:Ce) | — | Siemens spec |
| Crystal size | 3.2 x 3.2 x 20 | mm3 | van Sluis 2019 |
| Crystal rings (axial) | 80 | — | van Sluis 2019 |
| Crystals per ring | 760 | — | van Sluis 2019 |
| Total crystals | 60,800 | — | Derived |
| Detector ring diameter | 78.0 | cm | van Sluis 2019 |
| Axial FOV | 26.3 | cm | van Sluis 2019 |
| Energy resolution | 9.3% | FWHM | Prenosil 2022 |
| Timing resolution (CRT) | ~210 | ps FWHM | van Sluis 2019 |
| Energy window (clinical) | 435-585 | keV | Clinical default |
| Coincidence window | 4.7 | ns | van Sluis 2019 |
| Sensitivity (center) | ~16.4 | cps/kBq | NEMA NU 2-2018 |

---

## 3. MCGPU-PET Detector Model

### 3.1 Cylindrical Approximation

MCGPU-PET models the PET detector as a single continuous cylinder defined by three parameters in `detector_struct`:

```
PSF_center  : (x, y, z)   — Center of the cylindrical detector
PSF_height  : float        — Axial extent of the detector (cm)
PSF_radius  : float        — Radius of the cylindrical detector surface (cm)
```

The Vision 600's block-based detector geometry (5x5 mini-blocks, 19 blocks per module, 8 modules per ring) is approximated as a smooth cylinder. This is appropriate because:

- MCGPU-PET tracks photon transport through the patient volume and scores detection at the cylindrical surface
- Individual crystal interactions are not modeled (no depth-of-interaction, no inter-crystal scatter)
- The sinogram binning maps photon hit positions on the cylinder to discrete crystal indices using the `NCRYSTALS` and `NROWS` parameters

### 3.2 Parameter Mapping

The following table shows the correspondence between Vision 600 hardware and MCGPU-PET input parameters:

| Scanner Property | MCGPU-PET Parameter | Input Section | Value |
|---|---|---|---|
| Ring radius (39.0 cm) | `PSF_radius` | PHASE SPACE FILE | `-39.0` (negative = auto-center) |
| Axial FOV (26.3 cm) | `PSF_height` | PHASE SPACE FILE | `26.3` |
| Detector center | `PSF_center` | PHASE SPACE FILE | `0.0  0.0  0.0` |
| Energy resolution (9.3%) | `E_resol` | ENERGY PARAMETERS | `0.093` |
| Energy window low (435 keV) | `E_low` | ENERGY PARAMETERS | `435000.0` (eV) |
| Energy window high (585 keV) | `E_high` | ENERGY PARAMETERS | `585000.0` (eV) |
| Axial FOV (26.3 cm) | `FOVZ` | SINOGRAM PARAMETERS | `26.3` |
| Crystal rings (80) | `NROWS` | SINOGRAM PARAMETERS | `80` |
| Crystals/ring (760) | `NCRYSTALS` | SINOGRAM PARAMETERS | `760` |
| Angular bins | `NANGLES` | SINOGRAM PARAMETERS | `380` |
| Radial bins | `NRAD` | SINOGRAM PARAMETERS | `339` |
| Z slices | `NZS` | SINOGRAM PARAMETERS | `159` |
| Max ring difference (79) | `MRD` | SINOGRAM PARAMETERS | `79` |
| Span | `SPAN` | SINOGRAM PARAMETERS | `11` |
| Image matrix | `RES` | SINOGRAM PARAMETERS | `256` |
| Energy bins | `NE` | SINOGRAM PARAMETERS | `700` |

---

## 4. Detailed Parameter Derivations

### 4.1 Detector Radius (PSF_radius)

The Vision 600 has an inner detector ring diameter of 78.0 cm, giving a radius of **39.0 cm**. In the input file, a negative value (`-39.0`) instructs MCGPU-PET to automatically center the cylindrical detector on the voxelized phantom geometry:

```
 0.0  0.0  0.0  26.3  -39.0     # X, Y, Z, H, RADIUS [cm]
```

This auto-centering is implemented in `main()`:
```c
if (detector_data.PSF_radius < 0.0f) {
    // Center detector on the phantom bounding box
    detector_data.PSF_center.x = voxel_data.size_bbox.x * 0.5f;
    detector_data.PSF_center.y = voxel_data.size_bbox.y * 0.5f;
    detector_data.PSF_radius   = -detector_data.PSF_radius;
}
```

### 4.2 Energy Resolution (E_resol)

The Vision 600 achieves **9.3% FWHM energy resolution** at 511 keV (Prenosil et al. 2022). MCGPU-PET models energy blurring by applying a Gaussian resolution function to the detected photon energy:

```
E_detected = E_true + Gaussian(0, sigma)
where sigma = E_resol * E_true / 2.355
```

Set `E_resol = 0.093` in the input file. Note that the sample input file uses `0.12` (12%), which corresponds to an older PMT-based scanner; the Vision 600's digital SiPM technology provides significantly better energy resolution.

### 4.3 Energy Window

The clinical default window for the Vision 600 is **435-585 keV**. MCGPU-PET requires these in **electron-volts**:

```
435000.0      # ENERGY WINDOW LOW  [eV]
585000.0      # ENERGY WINDOW HIGH [eV]
```

This window is narrower than the sample file's 350-600 keV range, reflecting the Vision 600's tighter clinical configuration enabled by its superior energy resolution. The narrower window improves scatter rejection at the cost of slightly reduced true coincidence sensitivity.

### 4.4 Sinogram Grid

#### Number of Rows (NROWS = 80)

Equals the number of axial crystal rings. The Vision 600 has 8 detector modules, each containing 10 crystal rows (5 axial crystals x 2 sub-rings), totaling 80 rings.

#### Crystals Per Ring (NCRYSTALS = 760)

Total transaxial crystals: 19 blocks/module x 8 modules x 5 crystals/block = 760.

#### Angular Bins (NANGLES = 380)

By convention, `NANGLES = NCRYSTALS / 2 = 380`. Each angular bin represents a unique line-of-response (LOR) angle.

#### Radial Bins (NRAD = 339)

The number of radial bins should adequately sample the transaxial FOV. For the 70 cm bore with 3.2 mm crystal pitch:

```
N_rad ~ FOV_transaxial / crystal_pitch + margin = 700/3.2 + margin ~ 219 + 120 = 339
```

A value of 339 provides sufficient radial sampling with margin for oblique LORs.

#### Z Slices (NZS = 159)

For 80 crystal rings, the number of direct + cross sinogram planes is:

```
NZS = 2 * NROWS - 1 = 2 * 80 - 1 = 159
```

#### Maximum Ring Difference (MRD = 79)

Full 3D acquisition uses `MRD = NROWS - 1 = 79`, accepting all possible ring combinations.

#### Span (SPAN = 11)

Span controls the axial compression of oblique sinograms. Span=11 is the standard Siemens reconstruction setting, grouping oblique sinograms to reduce data size while preserving axial resolution. The number of sinogram segments and total sinograms is computed automatically:

```c
NSEG  = 2 * floor(MRD / SPAN) + 1;
NSINOS = NSEG * NZS;
// Additional corrections applied for segment boundaries
```

---

## 5. Step-by-Step Setup Guide

### 5.1 Using the Pre-Built Input File

The scanner configuration is provided as a ready-to-use MCGPU-PET input file:

```
scanners/Siemens_BiographVision600/BiographVision600.in
```

To run a simulation:

1. **Prepare a voxelized phantom** (`.vox` file) with appropriate dimensions. The phantom should fit within the 70 cm transaxial FOV and 26.3 cm axial FOV.

2. **Edit the input file** to set:
   - The phantom file path in `[SECTION VOXELIZED GEOMETRY FILE]`
   - Material file paths in `[SECTION MATERIAL FILE LIST]`
   - Acquisition time in `[SECTION SOURCE PET SCAN]`
   - Isotope mean life (e.g., 9504 s for F-18, 1221 s for C-11)
   - Output file names as needed

3. **Run MCGPU-PET**:
   ```bash
   ./MCGPU-PET.x scanners/Siemens_BiographVision600/BiographVision600.in
   ```

### 5.2 Adapting an Existing Input File

To convert an existing MCGPU-PET input file (e.g., the sample `MCGPU-PET.in`) to Vision 600 parameters, update the following sections:

#### Phase Space File section — change detector geometry:
```
 0.0  0.0  0.0  26.3  -39.0     # Center, Height=26.3cm, Radius=39.0cm
```

#### Energy Parameters section — change resolution and window:
```
0.093         # ENERGY RESOLUTION (9.3% for Vision 600)
435000.0      # ENERGY WINDOW LOW  [eV] (435 keV)
585000.0      # ENERGY WINDOW HIGH [eV] (585 keV)
```

#### Sinogram Parameters section — replace entire block:
```
26.3   # AXIAL FIELD OF VIEW (FOVz) [cm]
80     # NUMBER OF ROWS
760    # TOTAL NUMBER OF CRYSTALS
380    # NUMBER OF ANGULAR BINS
339    # NUMBER OF RADIAL BINS
159    # NUMBER OF Z SLICES
256    # IMAGE RESOLUTION
700    # NUMBER OF ENERGY BINS
79     # MAXIMUM RING DIFFERENCE
11     # SPAN
```

### 5.3 Memory Considerations

The Vision 600 configuration produces larger sinogram arrays than the sample simulation due to the greater number of crystals and rings:

| Array | Formula | Size (Vision 600) | Size (Sample) |
|---|---|---|---|
| Sinogram bins | NRAD x NANGLES x NSINOS | ~130M bins | ~12M bins |
| True sinogram | NBINS x 4 bytes | ~520 MB | ~48 MB |
| Scatter sinogram | NBINS x 4 bytes | ~520 MB | ~48 MB |
| Image array | RES x RES x NZS x 8 bytes | ~83 MB | ~14 MB |

**GPU memory requirement:** At minimum ~2 GB for sinograms alone. A GPU with >=6 GB is recommended. Modern GPUs (e.g., NVIDIA A100, RTX 3090/4090) are well suited.

To reduce memory usage, consider:
- Reducing `NRAD` (fewer radial bins — slight loss of peripheral sampling)
- Increasing `SPAN` (more axial compression — loss of axial resolution)
- Reducing `MRD` (limits oblique sinograms — reduces sensitivity)

---

## 6. Modeling Assumptions and Limitations

### 6.1 What Is Modeled

| Feature | Status | Notes |
|---|---|---|
| Cylindrical detector geometry | Modeled | Radius + height match Vision 600 |
| Crystal ring / bin structure | Modeled | Via NROWS, NCRYSTALS discretization |
| Energy resolution blurring | Modeled | Gaussian with sigma from E_resol |
| Energy window discrimination | Modeled | Accept/reject based on blurred energy |
| Photon attenuation in patient | Modeled | Full MC transport (Compton, Rayleigh, photoelectric) |
| Scatter estimation | Modeled | Separate True/Scatter sinograms |
| 3D sinogram (oblique LORs) | Modeled | MRD and SPAN parametrize ring combinations |
| Radioactive decay timing | Modeled | Exponential decay with isotope mean life |

### 6.2 What Is NOT Modeled

| Feature | Status | Impact | Potential Workaround |
|---|---|---|---|
| Crystal-level interactions | Not modeled | No depth-of-interaction, no inter-crystal scatter | Apply post-processing PSF |
| Time-of-flight (TOF) | Not modeled | Cannot use TOF for reconstruction | TOF not in current MCGPU-PET |
| SiPM dead time | Not modeled | Count-rate effects at high activity ignored | Limit to clinical count rates |
| Detector block gaps | Not modeled | Sensitivity slightly overestimated at gap locations | Negligible for most studies |
| Random coincidences | Not modeled | Must be added analytically or via delayed window | Use standard randoms estimation |
| Detector normalization | Not modeled | All crystals modeled as identical | Apply measured normalization coefficients |
| Prompt gamma from isotopes | Not modeled | Not modeled for non-pure beta+ emitters | Relevant only for Ga-68, Cu-64, etc. |
| Patient motion | Not modeled | Static phantom only | Use time-gated phantoms for respiratory motion |

### 6.3 Cylindrical vs. Block-Detector Geometry

The most significant approximation is modeling the detector as a continuous cylinder rather than discrete crystal blocks. In practice:

- **LOR endpoints** are mapped to discrete crystal positions during sinogram binning, so the spatial sampling matches the real scanner
- **Gaps between modules** are not modeled, leading to slightly higher sensitivity uniformity than reality
- **Parallax errors** from oblique photon incidence on finite-depth crystals are not modeled, but this effect is small at the ~39 cm radius

For most simulation tasks (scatter estimation, attenuation correction evaluation, image quality studies), the cylindrical approximation is well validated and widely used in the PET Monte Carlo literature.

---

## 7. Validation Strategy

### 7.1 Comparison with NEMA NU 2-2018 Results

The Vision 600 NEMA performance is well characterized (van Sluis et al. 2019). Recommended validation experiments:

1. **Sensitivity**: Simulate a line source at the center of the FOV, compare detected coincidence rate per unit activity with the published value of 16.4 cps/kBq.

2. **Scatter Fraction**: Simulate the NEMA scatter phantom (70 cm long, 20 cm diameter polyethylene cylinder with line source at 4.5 cm offset). Compare scatter fraction with the published value of ~37.9%.

3. **Spatial Resolution**: Simulate a point source at 1 cm and 10 cm radial offsets. Reconstruct and measure FWHM. Compare with published values (~3.6 mm at 1 cm).

### 7.2 Cross-Validation with GATE

GATE (Geant4 Application for Tomographic Emission) has a well-validated Biograph Vision model. Running the same phantom in both MCGPU-PET and GATE provides an independent validation path.

---

## 8. Example Workflow

A complete workflow for a Vision 600 scatter simulation:

```bash
# 1. Generate or obtain a voxelized phantom
python sample_simulation/scripts/example_phantom_generator.py

# 2. Copy the scanner input file template
cp scanners/Siemens_BiographVision600/BiographVision600.in my_simulation.in

# 3. Edit the input file: set phantom path, materials, acquisition time
#    (use any text editor)

# 4. Compile MCGPU-PET (if not already done)
make

# 5. Run the simulation
./MCGPU-PET.x my_simulation.in

# 6. Outputs will include:
#    - *_convergence_sinogram_true.raw.gz
#    - *_convergence_sinogram_scatter.raw.gz
#    - *_convergence_image_true.raw.gz
#    - *_convergence_image_scatter.raw.gz
#    - *_convergence_energy_spectrum.raw.gz
#    - *_PSF.dat / *_PSF.raw  (if PSF tallying enabled)
```

---

## 9. Configuration Quick Reference

For copy-paste into an MCGPU-PET input file:

```ini
# === Siemens Biograph Vision 600 Parameters ===

# PHASE SPACE FILE section:
 0.0  0.0  0.0  26.3  -39.0     # X Y Z Height Radius [cm]

# ENERGY PARAMETERS section:
0.093         # E_resol  (9.3% FWHM at 511 keV)
435000.0      # E_low    (435 keV in eV)
585000.0      # E_high   (585 keV in eV)

# SINOGRAM PARAMETERS section:
26.3   # FOVz [cm]
80     # NROWS
760    # NCRYSTALS
380    # NANGLES
339    # NRAD
159    # NZS
256    # RES
700    # NE
79     # MRD
11     # SPAN
```

---

## 10. References

1. **van Sluis JJ, de Jong J, Schaar J, et al.** "Performance Characteristics of the Digital Biograph Vision PET/CT System." *J Nucl Med.* 2019;60(7):1031-1036. doi:10.2967/jnumed.118.215418

2. **Prenosil GA, Sari H, Furstner M, et al.** "Performance Characteristics of the Biograph Vision Quadra PET/CT System with a Long Axial Field of View Using the NEMA NU 2-2018 Standard." *J Nucl Med.* 2022;63(3):476-484. doi:10.2967/jnumed.121.261972

3. **Siemens Healthineers.** "Biograph Vision Technical Data Sheet." Product specification, 2018.

4. **NEMA Standards Publication NU 2-2018.** "Performance Measurements of Positron Emission Tomographs (PETs)." National Electrical Manufacturers Association, 2018.

5. **van Sluis J, Boellaard R, Dierckx RAJO, et al.** "Image Quality and Activity Optimization in Oncologic 18F-FDG PET Using the Digital Biograph Vision PET/CT System." *J Nucl Med.* 2020;61(5):764-771. doi:10.2967/jnumed.119.234351

---

*This document is part of the MCGPU-PET design documentation series. See the `docs/` directory for related documents on physics models, GPU acceleration, software architecture, and other topics.*
