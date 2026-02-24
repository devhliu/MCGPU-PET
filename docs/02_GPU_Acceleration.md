# MCGPU-PET Design Document: GPU Acceleration Strategy

**Version:** 1.0  
**Date:** 2026-02-24  
**Status:** Reference Design  
**Codebase:** MCGPU-PET v0.1 (based on MC-GPU v1.3)

---

## 1. Executive Summary

MCGPU-PET achieves real-time PET simulation (up to ~1 million coincidences/second on a single GPU) through a carefully designed parallelization strategy that maps the physics problem directly onto the GPU's SIMT (Single Instruction, Multiple Threads) architecture. The core insight is that **each voxel's emissions are independent**, enabling a natural mapping of voxels to CUDA thread blocks.

---

## 2. CUDA Execution Model

### 2.1 Grid–Block–Thread Mapping

```
Grid:    dim3(Nx, Ny, Nz_active)   — one block per active voxel
Block:   dim3(num_threads, 1, 1)   — threads share the voxel workload
Thread:  simulates successive decays within its assigned voxel
```

| CUDA Dimension | Maps to | Example (9×9×9 phantom) |
|---|---|---|
| `gridDim.x` | `voxel_data.num_voxels.x` | 9 |
| `gridDim.y` | `voxel_data.num_voxels.y` | 9 |
| `gridDim.z` | `last_z_active` (≤ `num_voxels.z`) | 9 (or less) |
| `blockDim.x` | `num_threads_per_block` | 32 |

**Voxel identification** is derived directly from the block index:
```c
int absvox = blockIdx.x + blockIdx.y * gridDim.x + blockIdx.z * gridDim.x * gridDim.y;
```

This design eliminates load balancing concerns at the voxel level — each voxel's work is entirely self-contained within one block.

### 2.2 Optimization: Skipping Inactive Z-Layers

The function `find_last_z_active()` scans the phantom from the top (highest Z) down to find the last voxel layer containing any activity. The grid's Z dimension is truncated accordingly, preventing entire blocks from launching for empty regions. Within each block, voxels with zero activity return immediately:

```c
if (voxel_activity < 1.0e-7f) return;   // No activity → exit kernel
```

### 2.3 Thread Workload Distribution

Within each block, the voxel's activity is distributed equally among threads:

$$A_{\text{thread}} = \frac{A_{\text{voxel}}}{N_{\text{threads}}}$$

Each thread independently samples decay times and simulates photon pairs until its share of the acquisition time is exhausted. There is **no inter-thread synchronization** during the main simulation loop, maximizing throughput.

---

## 3. Memory Architecture

### 3.1 Memory Hierarchy Usage

```
┌──────────────────────────────────────────────────────┐
│  CONSTANT MEMORY (~64 KB, cached, broadcast to all)  │
│  ├── voxel_data_CONST     (geometry dimensions)      │
│  ├── mfp_table_data_CONST (interpolation params)     │
│  ├── source_energy_data_CONST (energy spectrum)      │
│  ├── dose_ROI_*_CONST     (dose region limits)       │
│  └── PETA_DEV             (simulation mode flag)     │
├──────────────────────────────────────────────────────┤
│  SHARED MEMORY (per block, ~48 KB)                   │
│  ├── cgco_SHARED          (Compton data tables)      │
│  ├── acquisition_time_ps_SHARED (block acq. time)    │
│  ├── total_histories_block_SHARED (block counter)    │
│  ├── inv_mean_life_SHARED (isotope decay constant)   │
│  ├── tally_TYPE_SHARED    (True/Scatter mode)        │
│  └── tally_PSF_SINOGRAM_SHARED (output mode)         │
├──────────────────────────────────────────────────────┤
│  GLOBAL MEMORY (device DRAM, GB-scale)               │
│  ├── voxel_mat_dens[]     (material/density/activity)│
│  ├── PSF[]                (phase space file output)  │
│  ├── mfp_Woodcock_table[] (Woodcock MFP data)        │
│  ├── mfp_table_a/b[]      (interaction MFP data)     │
│  ├── rayleigh_table       (Rayleigh scattering data) │
│  ├── voxels_Edep[]        (3D dose deposition)       │
│  ├── materials_dose[]     (per-material dose)        │
│  ├── True_dev[]           (True sinogram)            │
│  ├── Scatter_dev[]        (Scatter sinogram)         │
│  ├── Imagen_T_dev[]       (True image)               │
│  ├── Imagen_SC_dev[]      (Scatter image)            │
│  └── Energy_Spectrum_dev[](detected energy spectrum) │
├──────────────────────────────────────────────────────┤
│  REGISTERS (per thread, ~255 max)                    │
│  ├── position, direction  (float3 = 3 registers)    │
│  ├── energy, step, prob   (float)                    │
│  ├── seed (int2)          (PRNG state)               │
│  ├── scatter_state        (signed char)              │
│  └── travel_distance      (float)                    │
└──────────────────────────────────────────────────────┘
```

### 3.2 Constant Memory Strategy

Geometry parameters (`voxel_data_CONST`), interpolation constants (`mfp_table_data_CONST`), and source energy data are placed in constant memory because they are:
- Read-only during kernel execution
- Small enough to fit in the ~64 KB limit
- Accessed uniformly by all threads (broadcast access pattern → no serialization)

### 3.3 Shared Memory Strategy

The **Compton scattering data** (`compton_struct`, ~7.5 KB) is copied to shared memory by thread 0 at block initialization:

```c
if (0 == threadIdx.x) {
    cgco_SHARED = *compton_table;
    // ... other shared variable initialization
}
__syncthreads();
```

**Rationale:** Compton sampling accesses shell data in a non-coherent pattern (different threads may access different shells), making the L1/L2 cache ineffective. Shared memory provides guaranteed low-latency access (~5 ns vs ~200+ ns for uncached global).

### 3.4 L1 Cache Configuration

The kernel is configured to prefer L1 cache over shared memory:

```c
cudaFuncSetCacheConfig(track_particles, cudaFuncCachePreferL1);
```

This gives the Woodcock and MFP table lookups (which have good spatial locality) faster cached access in global memory.

### 3.5 Rayleigh Data: Global Memory with Caching

The Rayleigh scattering table (`rayleigh_struct`, ~3.7 MB) is too large for shared memory and is kept in global memory. Accesses are reasonably coherent (nearby energy bins accessed by threads in a warp) and benefit from L1/L2 caching.

---

## 4. Atomic Operations

### 4.1 Thread-Safe Tallying

Multiple threads may deposit energy in the same voxel or sinogram bin simultaneously. CUDA atomic operations prevent race conditions:

```c
// Dose deposition:
atomicAdd(&voxels_Edep[voxel].x, __float2ull_rn(Edep * SCALE_eV));
atomicAdd(&voxels_Edep[voxel].y, __float2ull_rn(Edep * Edep));

// Sinogram binning:
atomicAdd(&True_dev[ibin], 1);
atomicAdd(&Scatter_dev[ibin], 1);

// PSF slot allocation:
int index = atomicAdd(index_PSF, 2);  // Reserve 2 consecutive slots
```

### 4.2 Integer Scaling for Atomic Precision

Energy depositions are stored as `unsigned long long int` (64-bit) scaled by `SCALE_eV`. This is necessary because:
1. CUDA `atomicAdd` for `double` is slow (emulated with CAS loops on older architectures)
2. `float` `atomicAdd` would lose precision when adding small energies to large accumulated values
3. 64-bit integers provide sufficient dynamic range: $2^{64} \approx 1.8 \times 10^{19}$

### 4.3 PSF Overflow Protection

The PSF array has finite allocated size. Overflow is prevented:
```c
int index = atomicAdd(index_PSF, 2);
if (index > 2000000000) *index_PSF = 2000000000;  // Prevent int32 overflow
if (index < detector_data->PSF_size) { /* store data */ }
```

---

## 5. Random Number Generation

### 5.1 RANECU PRNG

The code uses the **RANECU** generator (two multiplicative linear congruential generators combined):

```
MLCG 1: s₁ = (40014 × s₁) mod 2147483563
MLCG 2: s₂ = (40692 × s₂) mod 2147483399
Combined: z = s₁ - s₂  (mod 2147483562)
PRN = z / 2147483563
```

**Period:** ~10¹⁸, sufficient for practical simulations.

### 5.2 Thread-Independent Sequences

Each thread initializes its PRNG seed using the **leap-frog** technique:

```c
init_PRNG(thread_id, max_histories_per_thread, seed_input, &seed);
```

This advances each thread's seed position by `thread_id × max_histories_per_thread × LEAP_DISTANCE` from the base seed, ensuring statistically independent random sequences across all threads.

### 5.3 Seed Persistence

The final seed of the last thread is stored back to global memory for continuation in multi-kernel runs:
```c
if (last_thread) *seed_input_device = seed.x;
```

### 5.4 GPU-Optimized Functions

- `__int2float_rn()` — Hardware-accelerated integer-to-float conversion for PRN output
- `rsqrtf()` — Reciprocal square root (single instruction on GPU, used in Compton)
- `sincosf()` — Simultaneous sine and cosine computation

---

## 6. Warp-Level Considerations

### 6.1 Branch Divergence

The main sources of warp divergence are:

| Source | Frequency | Impact |
|---|---|---|
| Virtual vs. real interaction | Every step | Low (most threads exit together) |
| Compton vs. Rayleigh vs. photoelectric | Every real interaction | Medium |
| Photon absorption termination | Variable | Medium (serializes remaining threads) |
| Energy below cutoff | Rare | Low |
| PSF vs. sinogram tallying | Per coincidence | Low |

The most significant divergence occurs when some threads finish their photon tracks (absorption or escape) before others. The `for(;;)` main loop continues until all threads in a warp have completed.

### 6.2 Memory Coalescence

- **Voxel data reads** (`voxel_mat_dens[absvox]`): Poorly coalesced because different threads track photons in different voxels. This is an inherent challenge of MC transport.
- **MFP table reads**: Reasonably coalesced when threads have similar energies (typical at 511 keV before scattering).
- **Sinogram/image writes**: Scattered addresses → atomic operations needed.

### 6.3 Occupancy

The kernel uses many registers (position, direction, energy, seed, etc.) and shared memory (~8 KB for Compton table). With 32 threads per block and typical register usage, occupancy is moderate. The code accepts non-multiple-of-32 thread counts with a warning:

```c
if ((*num_threads_per_block % 32) != 0)
    printf("WARNING: not a multiple of 32 (warp size)...");
```

---

## 7. Multi-GPU Support (MPI)

MCGPU-PET supports **multi-GPU execution** via MPI:

1. Each MPI process is assigned a different GPU (`gpu_id`)
2. Seeds are offset using `update_seed_PRNG()` to ensure independent random sequences
3. Results are gathered to the master thread after simulation
4. `MPI_Barrier` synchronization is used at initialization and completion

```
MPI Process 0 → GPU 0 → simulates all voxels with seed offset 0
MPI Process 1 → GPU 1 → simulates all voxels with seed offset 1
...
```

**Note:** The current implementation has each MPI process simulate the full geometry. A domain decomposition approach (partitioning voxels across GPUs) would be more efficient for large phantoms.

---

## 8. Build Configuration

### 8.1 Compilation Flags

```makefile
CFLAGS = -DUSING_CUDA -O3 -use_fast_math -m64 \
         -I$(CUDA_PATH) -I$(CUDA_SDK_PATH) \
         -L$(CUDA_LIB_PATH) -lcudart -lm -lz \
         --ptxas-options=-v \
         $(GPU_COMPUTE_CAPABILITY)
```

| Flag | Purpose |
|---|---|
| `-DUSING_CUDA` | Enables CUDA kernel compilation |
| `-O3` | Maximum optimization level |
| `-use_fast_math` | Fast (approximate) transcendental functions |
| `-lz` | zlib for gzip-compressed input files |
| `--ptxas-options=-v` | Verbose PTX assembler (reports register/smem usage) |
| `-gencode=arch=compute_75,code=sm_75` | Target GPU architecture |

### 8.2 Conditional Compilation

The code supports CPU-only compilation without CUDA:
- `#ifdef USING_CUDA` gates all GPU-specific code
- Vector types (`float3`, `int2`) are manually defined for CPU builds
- `__device__`, `__global__`, `__shared__`, and `__constant__` qualifiers are conditionally applied

---

## 9. Performance Characteristics

### 9.1 Benchmarks (from Published Paper)

- **~1 million coincidences/second** on a single modern GPU
- **13 seconds** for a fully-3D scatter sinogram with 10M coincidences (Zubal head phantom)
- **3 orders of magnitude faster** than standard CPU-based MC methods

### 9.2 Performance Bottlenecks

1. **Memory bandwidth**: Uncoalesced global memory accesses for voxel lookups during transport
2. **Atomic contention**: High-activity voxels may cause contention on sinogram bins
3. **Warp divergence**: Photon absorption terminates threads at different times
4. **Register pressure**: Many local variables reduce occupancy

### 9.3 Scaling Behavior

- **Linear scaling** with number of voxels (one block per voxel)
- **Sub-linear scaling** with threads-per-block (diminishing returns above ~64–128 due to register pressure)
- **Activity-proportional** work distribution (high-activity voxels take longer)
- **Near-linear multi-GPU scaling** with MPI (minimal inter-process communication)

---

## 10. Optimization Opportunities

| Opportunity | Estimated Impact | Complexity |
|---|---|---|
| Use texture memory for MFP tables | 10–20% speedup (cached + interpolation HW) | Low |
| Cooperative groups for load balancing | 15–30% for heterogeneous phantoms | Medium |
| Persistent kernel design | Reduced launch overhead for small phantoms | Medium |
| FP16 for direction vectors | Reduced register pressure, higher occupancy | Medium |
| Warp-level primitive for reductions | 5–10% for tally operations | Low |
| Stream-based multi-kernel pipelining | Better GPU utilization | Medium |
| Dynamic parallelism for adaptive refinement | Variable | High |
