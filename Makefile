# ========================================================================================
#                           TOP-LEVEL MAKEFILE MC-GPU-PET
#
#   Delegates to src/cuda/Makefile for CUDA compilation.
#   The binary MCGPU-PET.x is produced in this (project root) directory.
#
# ========================================================================================

.PHONY: default clean

default:
M$(MAKE) -C src/cuda

clean:
M$(MAKE) -C src/cuda clean
