# io_nifti — NIfTI I/O Module for MCGPU-PET

Placeholder for NIfTI (Neuroimaging Informatics Technology Initiative) file
format I/O routines. This module will provide functions to read/write `.nii`
and `.nii.gz` volumes for use as voxelized phantoms and output dose/image maps.

## Planned Functionality

- Read NIfTI-1/NIfTI-2 headers and volumetric data
- Convert NIfTI volumes to MCGPU-PET `.vox` format (material + density + activity)
- Export MCGPU-PET simulation outputs (dose maps, images) to NIfTI format
- Support for gzip-compressed NIfTI (`.nii.gz`)
- Affine transform preservation for spatial registration
