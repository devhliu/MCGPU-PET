# MCGPU-PET Design Document: Software Architecture

**Version:** 1.0  
**Date:** 2026-02-24  
**Status:** Reference Design  
**Codebase:** MCGPU-PET v0.1 (based on MC-GPU v1.3)

---

## 1. Overview

MCGPU-PET is structured as a single-compilation-unit CUDA/C application with a clear separation between host (CPU) orchestration and device (GPU) computation. The codebase consists of three source files totaling ~5,700 lines of code.

---

## 2. File Organization

```
MCGPU-PET/
├── MCGPU-PET.h              (537 lines)  — Header: structs, constants, function declarations
├── MCGPU-PET.cu             (3356 lines) — Host code: main(), I/O, initialization, reporting
├── MCGPU-PET_kernel.cu      (1836 lines) — Device code: GPU kernels and device functions
├── Makefile                              — Build configuration
├── README.md                             — Project documentation
├── docs/                                 — Design documents (this series)
└── sample_simulation/
    ├── MCGPU-PET.in                      — Sample input parameter file
    ├── phantom_9x9x9cm.vox              — Sample voxelized phantom
    ├── materials/                        — Pre-computed material data
    │   ├── air_5-515keV.mcgpu.gz
    │   ├── water_5-515keV.mcgpu.gz
    │   └── creating_material_files.txt
    └── scripts/
        ├── example_phantom_generator.py  — Python phantom generator
        ├── gnuplot_display_geometry.gpl  — Geometry visualization
        └── gnuplot_energy_spectrum.gpl   — Energy spectrum plotting
```

### 2.1 Compilation Model

The kernel file is `#include`d from the main `.cu` file (inferred from the single-target Makefile). This allows `nvcc` to compile all device and host code in a single pass, enabling aggressive inlining of device functions.

```makefile
SRCS = MCGPU-PET.cu    # Compiles everything through includes
$(CC) $(CFLAGS) $(SRCS) -o $(PROG)
```

---

## 3. Major Data Structures

### 3.1 Core Structures

```
┌─────────────────────────────────────────────────────────────┐
│                     struct source_struct                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ acquisition_time_ps : unsigned long long int         │   │
│  │ mean_life          : float                           │   │
│  │ activity[MAX_MATERIALS] : float[15]                  │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                    struct detector_struct                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ PSF_center   : float3  (cylinder center)             │   │
│  │ PSF_radius   : float   (detector radius)             │   │
│  │ PSF_height   : float   (axial extent)                │   │
│  │ PSF_size     : int     (max PSF elements)            │   │
│  │ tally_PSF_SINOGRAM : int  (output mode)              │   │
│  │ tally_TYPE   : int     (True/Scatter filter)         │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                     struct voxel_struct                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ num_voxels    : int3   (Nx, Ny, Nz)                  │   │
│  │ inv_voxel_size: float3 (1/dx, 1/dy, 1/dz)           │   │
│  │ size_bbox     : float3 (Lx, Ly, Lz)                  │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                  struct PSF_element_struct                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ emission_time_ps : unsigned long long int            │   │
│  │ travel_time_ps   : float                             │   │
│  │ emission_absvox  : int                               │   │
│  │ energy           : float                             │   │
│  │ z, phi           : float  (cylindrical coords)       │   │
│  │ vx, vy, vz       : float  (direction cosines)       │   │
│  │ index1, index2   : short int  (scatter flag, aux)    │   │
│  └──────────────────────────────────────────────────────┘   │
│  __attribute__((packed, aligned(4)))  → 40 bytes/element    │
├─────────────────────────────────────────────────────────────┤
│                   struct linear_interp                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ num_values : int    (number of energy bins)          │   │
│  │ e0         : float  (minimum energy)                 │   │
│  │ ide        : float  (inverse bin width)              │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                   struct compton_struct                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ fco[15×30]   : float  (oscillator strengths)         │   │
│  │ uico[15×30]  : float  (ionization energies)          │   │
│  │ fj0[15×30]   : float  (Compton profiles)            │   │
│  │ noscco[15]   : int    (shells per material)          │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                   struct rayleigh_struct                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ xco, pco, aco, bco : float[128×15]                   │   │
│  │ pmax : float[25005×15]                                │   │
│  │ itlco, ituco : unsigned char[128×15]                  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Voxel Data Array

The voxel geometry is stored as a flat `float3` array (`voxel_mat_dens`):

| Component | Meaning | Type |
|---|---|---|
| `.x` | Material number (1-based) | float (cast to int) |
| `.y` | Mass density (g/cm³) | float |
| `.z` | Activity (Bq) | float |

**Indexing:** `voxel_mat_dens[ix + iy*Nx + iz*Nx*Ny]` — X varies fastest.

---

## 4. Execution Flow

```
main()
  │
  ├──► read_input()           — Parse .in file, allocate PSF and dose arrays
  │
  ├──► load_voxels()          — Read .vox file, build voxel_mat_dens array
  │
  ├──► load_material()        — Read .mcgpu.gz files, build MFP tables
  │
  ├──► init_CUDA_device()     — GPU selection, memory allocation, data transfer
  │     ├── cudaSetDevice()
  │     ├── cudaMalloc() for all global arrays
  │     ├── cudaMemcpy() host → device
  │     ├── cudaMemcpyToSymbol() for constant memory
  │     └── cudaFuncSetCacheConfig()
  │
  ├──► track_particles<<<grid,block>>>()     — MAIN GPU KERNEL
  │     │
  │     ├── Thread 0: copy compton_table → shared memory
  │     ├── __syncthreads()
  │     ├── init_PRNG() — leap-frog seed initialization
  │     │
  │     └── for(;;) {   // MAIN HISTORY LOOP
  │           ├── Sample decay time (exponential)
  │           ├── Check acquisition time → break if exceeded
  │           ├── source() — sample position, direction, 511keV pair
  │           │
  │           └── for(;;) { // INTERACTION LOOP
  │                 ├── locate_voxel() — find current voxel
  │                 ├── do { // VIRTUAL INTERACTION (Woodcock)
  │                 │     ├── Sample step length
  │                 │     ├── Move photon
  │                 │     ├── locate_voxel()
  │                 │     ├── Read material data
  │                 │     └── Check delta scattering
  │                 │   } while (virtual)
  │                 │
  │                 ├── Select interaction type
  │                 ├── GCOa() — Compton scattering
  │                 │   or GRAa() — Rayleigh scattering
  │                 │   or Photoelectric (absorbed)
  │                 │
  │                 ├── rotate_double() — update direction
  │                 ├── Tally dose (if interaction deposited energy)
  │                 │   ├── tally_voxel_energy_deposition()
  │                 │   └── tally_materials_dose()
  │                 │
  │                 └── break if absorbed (index < 0)
  │               }
  │           
  │           ├── COINCIDENCE LOGIC:
  │           │   If 1st photon: store state, simulate 2nd
  │           │   If 2nd photon and 1st not absorbed:
  │           │     ├── tally_Sinogram()
  │           │     └── tally_PSF_coincidences()
  │         }
  │
  ├──► cudaDeviceSynchronize()
  │
  ├──► cudaMemcpy() device → host (PSF, sinograms, dose, images, spectrum)
  │
  ├──► report_PSF()           — Write PSF to ASCII + binary files
  │
  ├──► report_voxels_dose()   — Write 3D dose distribution
  │
  ├──► report_materials_dose()— Write per-material dose summary
  │
  └──► Write sinogram, image, and spectrum binary files
```

---

## 5. Coincidence Detection Logic

The coincidence algorithm is the most distinctive architectural feature of MCGPU-PET:

### 5.1 Two-Pass Photon Tracking

Each annihilation produces two photons tracked sequentially within the same thread:

```
Pass 1: source() sets direction1.x = (sampled values)
        Track photon 1 through interaction loop
        If escaped: store energyFirst, positionFirst, directionFirst, scatter_stateFirst
        If absorbed: set energyFirst = -10 (mark as lost)

Pass 2: source() uses direction1 to derive anti-collinear direction
        Track photon 2 through interaction loop
        If escaped AND energyFirst > 0: → COINCIDENCE DETECTED
        → tally_Sinogram() and/or tally_PSF_coincidences()
```

### 5.2 State Machine

The `direction1.x` variable serves as a state flag:
- `direction1.x > 10.0` → Need to sample new photon pair (or second photon just finished)
- `direction1.x ≤ 10.0` → Currently tracking second photon of a pair

After the second photon completes, `direction1.x` is set to `11.1` to trigger pair re-sampling.

---

## 6. Function Catalog

### 6.1 Host Functions (MCGPU-PET.cu)

| Function | Purpose |
|---|---|
| `main()` | Orchestration: init, kernel launch, output |
| `read_input()` | Parse .in file, set all simulation parameters |
| `load_voxels()` | Read .vox phantom file, build material/density array |
| `load_material()` | Read .mcgpu.gz files, compute MFP interpolation tables |
| `init_energy_spectrum()` | Walker aliasing for energy spectrum (legacy, unused in PET mode) |
| `init_CUDA_device()` | GPU initialization, memory management |
| `report_PSF()` | Write phase space file (ASCII + binary) |
| `report_voxels_dose()` | Write 3D dose map and uncertainty |
| `report_materials_dose()` | Write per-material dose summary |
| `find_last_z_active()` | Optimize grid by finding highest active Z layer |
| `trim_name()` | Utility: extract filename from input line |
| `fgets_trimmed()` | Utility: read input line, skip comments |
| `IRND0()` | Walker aliasing initialization (PENELOPE) |
| `update_seed_PRNG()` | Advance PRNG for MPI parallelism |

### 6.2 Device Functions (MCGPU-PET_kernel.cu)

| Function | Qualifier | Purpose |
|---|---|---|
| `track_particles()` | `__global__` | Main simulation kernel |
| `init_image_array_GPU()` | `__global__` | Zero-initialize GPU arrays |
| `source()` | `__device__ inline` | PET positron annihilation sampling |
| `locate_voxel()` | `__device__ inline` | Voxel lookup from position |
| `move_to_bbox()` | `__device__ inline` | Move particle to geometry (unused in PET) |
| `GCOa()` | `__device__ inline` | Compton scattering (PENELOPE) |
| `GRAa()` | `__device__ inline` | Rayleigh scattering (PENELOPE) |
| `rotate_double()` | `__device__ inline` | Direction rotation (double precision) |
| `init_PRNG()` | `__device__ inline` | RANECU seed initialization |
| `ranecu()` | `__device__ inline` | Single-precision PRNG |
| `ranecu_double()` | `__device__ inline` | Double-precision PRNG |
| `abMODm()` | `__device__ __host__ inline` | Modular exponentiation for PRNG |
| `tally_PSF_coincidences()` | `__device__ inline` | Record PSF coincidences |
| `tally_Sinogram()` | `__device__ inline` | Bin coincidences into sinogram |
| `tally_voxel_energy_deposition()` | `__device__` | Dose deposition per voxel |
| `tally_materials_dose()` | `__device__ inline` | Dose deposition per material |

---

## 7. Key Design Patterns

### 7.1 Struct Alignment

GPU-targeted structures use `__align__(16)` for optimal memory transaction alignment:
```c
struct __align__(16) source_struct { ... };
```

The PSF element struct uses `__attribute__((packed, aligned(4)))` to minimize padding and ensure binary output correctness.

### 7.2 Conditional CUDA Compilation

All CUDA-specific features are wrapped in preprocessor guards:
```c
#ifdef USING_CUDA
    __device__
#endif
inline float ranecu(int2* seed) { ... }
```

This enables the same codebase to compile for CPU-only execution (for debugging or portability).

### 7.3 PENELOPE Code Heritage

Physics subroutines (`GCOa`, `GRAa`, `IRND0`) are direct C translations of PENELOPE's Fortran77 routines. The original PENELOPE variable names and algorithm structure are preserved for traceability and validation.

### 7.4 Input File Section Parsing

Input parsing uses section markers with version tags:
```
[SECTION SIMULATION CONFIG v.2016-07-05]
[SECTION SOURCE PET SCAN v.2017-03-14]
[SECTION PHASE SPACE FILE v.2016-07-05]
[SECTION DOSE DEPOSITION v.2012-12-12]
```

The parser skips to the matching section header, enabling forward compatibility and comment tolerance.

---

## 8. Error Handling

| Category | Strategy |
|---|---|
| Input file errors | `exit(-2)` with descriptive message |
| Memory allocation failures | `exit(-2)` with size information |
| CUDA errors | `checkCudaErrors()` macro (CUDA SDK) |
| Kernel execution errors | `getLastCudaError()` after `cudaDeviceSynchronize()` |
| Numerical precision | Warnings printed (e.g., `pzomc` in Compton), forced safe values |
| Overflow protection | Integer counter clamping (PSF), relative error checks (dose) |
| Material validation | Cross-checks energy range vs. annihilation energy |

---

## 9. Legacy Code (MC-GPU CT Features)

Significant portions of the original MC-GPU CT simulation infrastructure remain in the code but are disabled:

- **CT trajectory** (`set_CT_trajectory`): Commented out, not used for PET
- **X-ray source model**: Replaced by PET annihilation source
- **Flat detector model**: Replaced by cylindrical PET detector
- **Projection-based imaging**: Replaced by coincidence-based sinogram
- **Multiple projections loop**: PET uses single kernel launch
- **Energy spectrum sampling** (Walker aliasing): Present but unused for fixed 511 keV

These vestiges provide a foundation for potential future hybrid imaging modes (e.g., PET/CT simulation).

---

## 10. Thread Safety and Synchronization Points

| Synchronization | When | Why |
|---|---|---|
| `__syncthreads()` | After shared memory init | Ensure all threads see Compton data |
| `__syncthreads()` | After history simulation | Ensure all threads done before final tally |
| `atomicAdd()` | Dose deposition | Multiple threads → same voxel |
| `atomicAdd()` | Sinogram binning | Multiple threads → same bin |
| `atomicAdd()` | PSF slot allocation | Global counter for PSF index |
| `atomicAdd()` | Total histories counter | Aggregate across all threads |
| `MPI_Barrier()` | Init and completion | Synchronize multi-GPU processes |

---

## 11. Architectural Constraints

| Constraint | Value | Source |
|---|---|---|
| Max materials | 15 | `MAX_MATERIALS` constant |
| Max shells per material | 30 | `MAX_SHELLS` constant |
| Rayleigh interpolation points | 128 | `NP_RAYLEIGH` constant |
| Rayleigh energy bins | 25,005 | `MAX_ENERGYBINS_RAYLEIGH` |
| Max energy spectrum bins | 1 | `MAX_ENERGY_BINS` (PET: fixed 511 keV) |
| Max PSF elements | User-defined | Limited by GPU memory |
| Max int PSF counter | 2 × 10⁹ | Clamped to prevent int32 overflow |
| Voxel index space | 32-bit int | ~2.1 billion voxels max |
| Time resolution | 1 ps | `unsigned long long int` (~5.1 hours max) |
