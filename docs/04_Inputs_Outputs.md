# MCGPU-PET Design Document: Inputs & Outputs

**Version:** 1.0  
**Date:** 2026-02-24  
**Status:** Reference Design  
**Codebase:** MCGPU-PET v0.1 (based on MC-GPU v1.3)

---

## 1. Overview

MCGPU-PET uses a text-based configuration system with separate files for simulation parameters, voxelized geometry, and pre-computed material cross-section data. Outputs include phase space files, sinograms, reconstructed images, energy spectra, and dose maps.

---

## 2. Input Files

### 2.1 Simulation Parameter File (.in)

The main configuration file uses a section-based format inherited from penEasy. Each section begins with a header tag:

```
[SECTION <NAME> v.<date>]
```

Lines starting with `#` are comments. Each parameter is followed by an inline comment (separated from the value). The parser reads each line sequentially within a section.

#### 2.1.1 SIMULATION CONFIG (`v.2016-07-05`)

| Parameter | Type | Example | Description |
|---|---|---|---|
| Total histories | long long | `0` | Number of histories (0 = determined by acquisition time) |
| Acquisition time | float | `1.0` | PET scan duration (seconds) |
| Mean isotope life | float | `70000.0` | Decay half-life / ln(2) in seconds |
| Simulation threads/block | int | `32` | CUDA threads per block |
| Random seed 1 | int | `31415986` | First RANECU seed |
| Random seed 2 | int | `27182696` | Second RANECU seed |
| GPU number | int | `0` | CUDA device index |
| MPI threads per GPU | int | `0` | MPI workers (0 = auto) |

#### 2.1.2 SOURCE PET SCAN (`v.2017-03-14`)

| Parameter | Type | Example | Description |
|---|---|---|---|
| Background mode flag | int | `1` | 0=random pair direction, 1=anti-collinear |

> When `background_mode=0`, the second photon is not anti-collinear — used for background estimation.

#### 2.1.3 PHASE SPACE FILE (`v.2016-07-05`)

| Parameter | Type | Example | Description |
|---|---|---|---|
| Output PSF filename | string | `Output_MCGPU-PET` | Base name for output files |
| Tally type | string | `PSF_AND_SINOGRAM` | `PSF`, `SINOGRAM`, `PSF_AND_SINOGRAM`, or `NONE` |
| Output Type | string | `ALL` | `ALL`, `TRUE`, or `SCATTER` |
| Number of detector rows | int | `80` | Axial crystal rings |
| Crystals per ring | int | `336` | Transaxial crystals per ring |
| Detector radius | float | `32.8` | Cylindrical radius (cm) |
| FOVz center | float | `4.5` | Axial center of FOV (cm) |
| FOVz height | float | `12.656` | Axial FOV extent (cm) |
| Max PSF elements | int | `700000000` | PSF buffer size |
| Energy resolution | float | `0.12` | dE/E at 511 keV (FWHM) |
| Lower energy window | float | `350000` | Low threshold (eV) |
| Upper energy window | float | `600000` | High threshold (eV) |

#### 2.1.4 DOSE DEPOSITION (`v.2012-12-12`)

| Parameter | Type | Example | Description |
|---|---|---|---|
| Tally dose flag | string | `YES`/`NO` | Enable voxel dose tallying |
| Dose ROI min corner | float3 | `1.0 1.0 1.0` | ROI lower bound (voxel indices) |
| Dose ROI max corner | float3 | `25.0 25.0 25.0` | ROI upper bound (voxel indices) |
| Print materials dose | string | `YES`/`NO` | Per-material dose summary |

#### 2.1.5 ENERGY PARAMETERS (`v.2016-07-05`)

| Parameter | Type | Example | Description |
|---|---|---|---|
| Max energy bins | int | `100` | Energy spectrum histogram bins |
| Min simulation energy | float | `5000` | Transport cutoff (eV) |
| Max simulation energy | float | `515000` | Maximum energy in tables (eV) |

#### 2.1.6 SINOGRAM PARAMETERS (`v.2016-11-25`)

| Parameter | Type | Example | Description |
|---|---|---|---|
| Sinogram radial bins | int | `280` | Radial sampling |
| Sinogram angular bins | int | `336` | Angular sampling |
| MRD (max ring difference) | int | `79` | Maximum axial ring difference |
| SPAN | int | `11` | Sinogram span (axial compression) |

#### 2.1.7 VOXELIZED GEOMETRY (`v.2012-12-12`)

| Parameter | Type | Example | Description |
|---|---|---|---|
| Voxel geometry file | string | `phantom_9x9x9cm.vox` | Path to .vox file |

#### 2.1.8 MATERIAL FILE LIST (`v.2012-12-12`)

Up to 15 material files listed in order matching the material indices in the voxel file:

```
materials/air_5-515keV.mcgpu.gz             [Material 1]
materials/water_5-515keV.mcgpu.gz           [Material 2]
...
```

---

### 2.2 Voxelized Phantom File (.vox)

penEasy-format text file describing the 3D voxel geometry.

#### Header

```
[SECTION VOXELS HEADER v.2008-04-13]
 90  90  90               # Nx, Ny, Nz (voxel count per axis)
 0.1  0.1  0.1            # dx, dy, dz (voxel size in cm)
 1                         # Column flag (1 = material-density-activity)
[END OF VXH SECTION]
```

#### Body

```
[SECTION VOXELS DATA v.2008-04-13]
 1  0.001205  0.00        # Material 1 (air), density 0.001205 g/cm³, activity 0 Bq
 1  0.001205  0.00
 2  1.000000  50.00       # Material 2 (water), density 1.0 g/cm³, activity 50 Bq
 ...
[END OF VXD SECTION]
```

**Data columns:**
| Column | Type | Description |
|---|---|---|
| 1 | int | Material index (1-based, matching material file list) |
| 2 | float | Mass density (g/cm³) |
| 3 | float | Radioactivity concentration (Bq per voxel) |

**Ordering:** X varies fastest, Z slowest: `voxel[ix + iy*Nx + iz*Nx*Ny]`

#### Column Mode

When `column_flag = 1`, the 3-column format (material, density, activity) is expected. This is the PET-specific extension; the original MC-GPU format used only 2 columns (material, density).

---

### 2.3 Material Data Files (.mcgpu.gz)

Pre-computed cross-section data files derived from the PENELOPE material database. May be gzip-compressed (read with `zlib`).

#### Format

```
# [MATERIAL NAME]
# [NOMINAL DENSITY] g/cm³
# [NUMBER OF DATA COLUMNS]
# [TABLE OF INTERACTIONS per energy interval]
#   Energy  Rayleigh  Compton  Photoelectric  Pair  Rayleigh_max  MFP_total
0.005000e+06   ...    ...       ...           ...     ...          ...
0.005050e+06   ...    ...       ...           ...     ...          ...
...
# Rayleigh form factor data
# Compton profile data
```

**Key data consumed:**

| Section | Usage |
|---|---|
| MFP interpolation table | Mean free path for Woodcock tracking |
| Rayleigh form factors | Anomalous scattering factors, RITA sampling |
| Compton profiles | Shell-by-shell oscillator strengths, ionization energies |

**Energy range:** Must span at least from the minimum simulation energy to 511 keV. Material files are named by energy range (e.g., `water_5-515keV.mcgpu.gz`).

---

## 3. Output Files

All output files share the base name specified in the input file configuration (e.g., `Output_MCGPU-PET`).

### 3.1 Phase Space File (PSF)

#### ASCII PSF (`_PSF.dat`)

Human-readable listing of the first 5,000 coincidence events:

```
#  em_time(ps) travel_time(ps) abs_voxel energy(eV) z(cm)  phi(rad) vx vy vz index1 index2
   12345678     2345            1234    508123.5    4.23   1.456   0.12 -0.34 0.93  0  1
```

| Field | Type | Description |
|---|---|---|
| `emission_time_ps` | ull | Decay time in picoseconds |
| `travel_time_ps` | float | Photon travel time to detector (ps) |
| `emission_absvox` | int | Voxel index where photon was emitted |
| `energy` | float | Detected energy (eV), includes resolution blur |
| `z` | float | Axial position on detector (cm) |
| `phi` | float | Azimuthal position on detector (rad) |
| `vx, vy, vz` | float | Direction cosines at detection |
| `index1` | short | Scatter flag: 0=primary, 1+=scattered |
| `index2` | short | Auxiliary index |

Each coincidence produces **two consecutive lines** (one per photon).

#### Binary PSF (`_PSF.raw`)

Complete PSF with all coincidence events as `PSF_element_struct` records:

```
Total file size = 2 × N_coincidences × 40 bytes
```

Record layout: 40 bytes packed struct (see struct diagram in Architecture doc).

### 3.2 Sinogram

#### True Sinogram (`_convergence_sinogram_true.raw`)

Binary file of `unsigned long long int` values:

```
Dimensions: [radial_bins × angular_bins × num_sinograms]
Size per element: 8 bytes
```

The number of sinograms depends on the detector geometry, SPAN, and MRD settings.

#### Scatter Sinogram (`_convergence_sinogram_scatter.raw`)

Same format as True sinogram, containing events where at least one photon scattered.

### 3.3 Images

#### True Image (`_convergence_image_true.raw`)

Binary file of `unsigned long long int` values:

```
Dimensions: [Nx_image × Ny_image × Nz_image]
```

Image dimensions are derived from sinogram parameters. Contains back-projected coincidence counts.

#### Scatter Image (`_convergence_image_scatter.raw`)

Same format, back-projected from scatter events.

### 3.4 Energy Spectrum

#### Energy Spectrum (`_convergence_energy_spectrum.raw`)

Binary file of `unsigned long long int` values:

```
Dimensions: [energy_bins]
```

Histogram of detected photon energies (both accepted and rejected by the energy window).

### 3.5 Dose Files

#### Voxel Dose Map (`_convergence_dose.dat`)

ASCII text file with one line per voxel in the dose ROI:

```
#  ix  iy  iz  dose(eV/g)  relative_error(%)
   1   1   1   0.00000e+00   100.00
   2   1   1   3.45678e+02    15.23
```

The dose is reported as energy deposited per unit mass (eV per gram of material). Relative error is the statistical uncertainty.

#### Materials Dose Summary (`_convergence_materials_dose.dat`)

Per-material dose summary output to the console and/or file:

```
Material  Dose(eV/g/hist)  +/-Error  Num_interactions
   1        0.000000e+00    0.00%         0
   2        1.234567e-03    2.15%     15000
```

---

## 4. Command-Line Interface

```bash
./MCGPU-PET.x <input_file.in> [gpu_number]
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `input_file.in` | Yes | — | Path to simulation parameter file |
| `gpu_number` | No | 0 | Override GPU device index |

With MPI:
```bash
mpirun -np <N> ./MCGPU-PET.x <input_file.in>
```

Each MPI rank operates on the same GPU (or different GPUs if configured).

---

## 5. File Relationships

```
                    ┌────────────────────┐
                    │  MCGPU-PET.in      │
                    │  (parameters)      │
                    └───────┬────────────┘
                            │ references
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
    ┌──────────────┐ ┌───────────┐ ┌────────────────┐
    │ phantom.vox  │ │ mat1.gz   │ │ mat2.gz  ...   │
    │ (geometry)   │ │ (physics) │ │ (physics)      │
    └──────┬───────┘ └─────┬─────┘ └──────┬─────────┘
           │               │              │
           └───────────────┼──────────────┘
                           │
                    ┌──────▼──────┐
                    │ MCGPU-PET.x │
                    │ (simulation)│
                    └──────┬──────┘
                           │ produces
         ┌─────────────────┼──────────────────────┐
         │          │          │           │       │
         ▼          ▼          ▼           ▼       ▼
    ┌─────────┐ ┌────────┐ ┌────────┐ ┌──────┐ ┌──────┐
    │ PSF     │ │ Sino-  │ │ Image  │ │ Dose │ │Energy│
    │.dat/.raw│ │ gram   │ │ .raw   │ │ .dat │ │Spec. │
    └─────────┘ │ .raw   │ └────────┘ └──────┘ │ .raw │
                └────────┘                      └──────┘
```

---

## 6. Data Volume Estimates

| Output | Size Formula | Example (10M coinc, 280×336 sino) |
|---|---|---|
| PSF binary | 2 × N × 40 B | ~800 MB |
| True sinogram | 8 × radial × angular × num_sino B | ~10–100 MB |
| Scatter sinogram | Same as True | ~10–100 MB |
| True image | 8 × Nx_img × Ny_img × Nz_img B | ~10–50 MB |
| Energy spectrum | 8 × energy_bins B | ~800 B |
| Dose map | ~50 B/voxel × ROI_voxels | ~1–100 MB |

> **Note:** PSF files can be very large. For a clinical-scale simulation with hundreds of millions of coincidences, binary PSF can exceed several GB. The ASCII PSF is always limited to the first 5,000 events.

---

## 7. Units Convention

| Quantity | Internal Unit | Notes |
|---|---|---|
| Energy | eV | All transport, tallying |
| Length | cm | Voxel dimensions, positions |
| Density | g/cm³ | Material property |
| Mass | g | Dose denominator |
| Time | ps | Emission and travel times |
| Activity | Bq | Per-voxel activity |
| Acquisition time | s | Input parameter |
| Mean life | s | Decay constant input |
| Dose | eV/g | Energy deposited per mass |
| Angles | radians | Internal; degrees possible in input |
